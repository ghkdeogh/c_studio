"""Bounded, source-backed lesson retrieval and project-owned application history.

No model calls, automatic rewriting of feedback, or global copies of source text.
Similarity and conflict notices are review candidates, not semantic verdicts.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import re
import time
import unicodedata

import production_assets as assets

STAGES = ('planning', 'generation', 'review')
STATES = ('candidate', 'active', 'retired')
REF = re.compile(r'^productions/[^/\\:#]+/[^/\\:#]+/feedback\.json#[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
TOPICS = {
    'hook': ('후킹', '도입', 'hook', '첫 장면'),
    'pacing': ('템포', '전환', '생략', '길이', 'pacing'),
    'continuity': ('시작 상태', '연속성', '소품', '중간 동작', 'continuity'),
    'sound': ('음성', '음량', '목소리', '소리', '현장음', '사운드', 'audio'),
    'identity': ('인물', '얼굴', '시트', '복장', 'character'),
    'camera': ('카메라', '드론', '무빙', 'camera'),
    'input': ('입력 역할', '업로드', '제출', '참조', 'endframe'),
    'research': ('역사', '문헌', '자료', '조사'),
}
STAGE_TOPICS = {
    'planning': {'hook', 'pacing', 'identity', 'research'},
    'generation': {'continuity', 'sound', 'identity', 'camera', 'input'},
    'review': set(TOPICS),
}
# Conservative applicability hints for legacy free-text conditions. These are
# disclosed filters; explicit curated keywords take precedence over the hints.
CONTEXT_GATES = (
    ('프리비즈·임시 음향', r'blender|프리비즈|임시 효과음', ('blender', '프리비즈', '임시 효과음', '임시 소리')),
    ('드론·추적 장면', r'드론|추적 장면|역동적인 추적', ('드론', '추적', '추격', '달리', '질주')),
    ('바람·빠른 이동', r'빠른 이동이나 바람', ('바람', '달리', '질주', '추격')),
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def norm(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).lower().split())


def strings(value, name, limit=20):
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(x, str) or not x.strip() or len(x) > 160 for x in value):
        raise ValueError(name + ': 짧은 문자열 목록을 사용해 주세요.')
    return list(dict.fromkeys(x.strip() for x in value))


def reference(value):
    if not isinstance(value, str) or not REF.fullmatch(value) or any(x in ('.', '..') for x in value.split('/')):
        raise ValueError('피드백 출처는 productions/종류/작품/feedback.json#기록ID 형식입니다.')
    return value


def clean_learning(value):
    if not isinstance(value, dict):
        raise ValueError('learning은 객체여야 합니다.')
    allowed = {'topic', 'stance', 'keywords', 'exclude_keywords', 'stages', 'models', 'state', 'canonical_ref', 'supersedes'}
    if set(value) - allowed:
        raise ValueError('지원하지 않는 learning 필드입니다.')
    out = {k: assets.text(value, k, limit=160) for k in ('topic', 'stance', 'canonical_ref')}
    for key in ('keywords', 'exclude_keywords', 'stages', 'models', 'supersedes'):
        out[key] = strings(value.get(key, []), key)
    if not set(out['stages']) <= set(STAGES):
        raise ValueError('제작 단계는 planning/generation/review입니다.')
    out['state'] = value.get('state', 'candidate')
    if out['state'] not in STATES:
        raise ValueError('원칙 상태는 candidate/active/retired입니다.')
    for ref in out['supersedes'] + ([out['canonical_ref']] if out['canonical_ref'] else []):
        reference(ref)
    return out


def project_folders(root):
    root = root.resolve()
    folders = sorted(p.parent for p in (root / 'productions').glob('*/*/BRIEF.md'))
    return [p for p in folders if p.resolve().is_relative_to(root)]


def project_folder(root, pid):
    folder = assets.inside(root, pid)
    if folder not in [p.resolve() for p in project_folders(root)]:
        raise ValueError('저장소 안의 작품을 선택해 주세요.')
    return folder


def source_rows(root):
    rows = []
    for folder in project_folders(root):
        pid = folder.relative_to(root.resolve()).as_posix()
        info = json.loads(assets.inside(folder, 'project.json').read_text(encoding='utf-8-sig')) if (folder / 'project.json').is_file() else {}
        for row in assets.load(folder, 'feedback')['items']:
            ref = reference(f'{pid}/feedback.json#{row["id"]}')
            semantic = {k: v for k, v in row.items() if k not in ('created_at', 'updated_at')}
            rows.append({**row, 'project_id': pid, 'project_name': info.get('title', folder.name),
                         'ref': ref, 'source_hash': digest(semantic)})
    return rows


def load_plan(folder):
    p = assets.inside(folder, 'lesson-plan.json')
    if not p.exists():
        return {'schema_version': 1, 'revision': 0, 'items': [], 'history': []}
    data = json.loads(p.read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1 or type(data.get('revision')) is not int or not isinstance(data.get('items'), list) or not isinstance(data.get('history'), list):
        raise ValueError('lesson-plan.json 형식을 확인해 주세요.')
    return data


def stamp(path):
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def stale_reasons(folder, item, by_ref):
    problems = []
    src = by_ref.get(item['ref'])
    if not src or src['source_hash'] != item.get('source_hash'):
        problems.append('원본 피드백이 변경되었거나 없습니다.')
    elif src.get('status') == 'archived' or src.get('learning', {}).get('state') == 'retired':
        problems.append('원본 피드백이 보관되거나 은퇴했습니다.')
    for proof in item.get('evidence', []):
        f = assets.inside(folder, proof['path'])
        if not f.is_file() or stamp(f) != proof.get('stamp'):
            problems.append('반영 근거가 변경되었거나 없습니다: ' + proof['path'])
    return problems


def plan_view(folder, by_ref):
    plan = load_plan(folder)
    return {**{k: plan[k] for k in ('schema_version', 'revision')},
            'items': [{**i, 'title': by_ref.get(i['ref'], {}).get('title', i['ref']),
                       'current_action': by_ref.get(i['ref'], {}).get('action', ''),
                       'current_source_hash': by_ref.get(i['ref'], {}).get('source_hash'),
                       'stale': stale_reasons(folder, i, by_ref)} for i in plan['items']],
            'history': [{'revision': h['revision'], 'ref': h['ref'], 'operation': h['operation'], 'at': h['at']}
                        for h in plan['history'][-20:]]}


def outcomes(root, by_ref):
    result = {}
    for folder in project_folders(root):
        for item in load_plan(folder)['items']:
            if item['stage'] != 'reviewed' or stale_reasons(folder, item, by_ref):
                continue
            counts = result.setdefault(item['ref'], {'helpful': set(), 'ineffective': set(), 'uncertain': set()})
            counts[item['outcome']].add(folder.as_posix())
    return result


def select(root, pid=None, query='', stage='planning', model='', limit=6, offset=0, browse=False):
    root = root.resolve()
    if stage not in STAGES or type(limit) is not int or not 1 <= limit <= 20 or type(offset) is not int or offset < 0:
        raise ValueError('제작 단계와 조회 범위(1~20개)를 확인해 주세요.')
    if not isinstance(query, str) or len(query) > 2000 or not isinstance(model, str) or len(model) > 160:
        raise ValueError('검색어 또는 모델 이름이 너무 깁니다.')
    folder = project_folder(root, pid) if pid else None
    rows = source_rows(root)
    by_ref = {r['ref']: r for r in rows}
    context = query
    if folder:
        context += '\n' + assets.inside(folder, 'BRIEF.md').read_text(encoding='utf-8-sig')[:16000]
    context = norm(context)
    history = outcomes(root, by_ref)
    candidates = [r for r in rows if r.get('scope') == 'reusable' and r.get('status') != 'archived'
                  and r.get('learning', {}).get('state') != 'retired' and r['project_id'] != pid]
    grouped = {}
    for row in candidates:
        meta = row.get('learning', {})
        text = norm(' '.join(str(row.get(k) or '') for k in ('title', 'action', 'context')))
        topics = {k for k, words in TOPICS.items() if any(w in text for w in words)}
        if meta.get('topic'):
            topics.add(meta['topic'])
        warnings, excluded, reasons = [], [], []
        if not meta.get('keywords'):
            for label, pattern, terms in CONTEXT_GATES:
                if re.search(pattern, norm(row.get('context') or '')) and not any(term in context for term in terms):
                    excluded.append(label + ' 조건 확인 필요')
        if meta.get('stages') and stage not in meta['stages']:
            excluded.append('다른 제작 단계에 적용')
        if meta.get('models') and norm(model) not in {norm(m) for m in meta['models']}:
            excluded.append('모델 조건 확인 필요')
        if any(norm(w) in context for w in meta.get('exclude_keywords', [])):
            excluded.append('제외 조건에 해당')
        if meta.get('keywords') and not any(norm(w) in context for w in meta['keywords']):
            excluded.append('적용 조건과 일치하는 주제 없음')
        specific = bool(re.search(r'(이번|현재).{0,35}(편|작품)|\b\d+\s*초.{0,15}(유지|고정)', str(row.get('context') or '') + ' ' + str(row.get('action') or '')))
        if specific and not meta.get('keywords') and meta.get('state') != 'active':
            warnings.append('특정 작품의 조건이 섞여 있을 수 있어요.')
        score = 1 + 2 * len(topics & STAGE_TOPICS[stage])
        if topics & STAGE_TOPICS[stage]:
            reasons.append('이번 제작 단계 관련')
        matched = [w for words in TOPICS.values() for w in words if w in context and w in text]
        query_terms = [w for w in norm(query).split() if len(w) > 1 and w in text]
        if matched or query_terms:
            score += min(12, len(set(matched + query_terms)) * 2)
            reasons.append('작품·검색어 관련: ' + ', '.join(dict.fromkeys(matched + query_terms))[:120])
        if query and not query_terms and not any(w in norm(query) and w in text for words in TOPICS.values() for w in words):
            excluded.append('검색어와 일치하지 않음')
        if meta.get('state') == 'active':
            score += 2
        if warnings:
            score -= 3
        # Only identical actions AND conditions are merged automatically.
        key = digest([norm(row.get('action', '')), norm(row.get('context', '')), meta])
        entry = grouped.setdefault(key, {**row, 'group_id': key[:20], 'refs': [], 'topics': sorted(topics),
                                         'warnings': warnings, 'excluded': excluded, 'reasons': reasons or ['적용 조건 직접 확인'],
                                         'score': score, 'related': []})
        entry['refs'].append({'ref': row['ref'], 'source_hash': row['source_hash']})
    groups = list(grouped.values())
    active = {r['ref']: g for g in groups if not g['excluded'] and g.get('learning', {}).get('state') == 'active' for r in g['refs']}
    graph = {ref: g.get('learning', {}).get('supersedes', []) for ref, g in active.items()}
    cyclic = set()
    for start in graph:
        pending, seen = list(graph[start]), set()
        while pending:
            ref = pending.pop()
            if ref == start:
                cyclic.add(start)
                break
            if ref not in seen:
                seen.add(ref)
                pending.extend(graph.get(ref, []))
    for group in groups:
        if any(r['ref'] in cyclic for r in group['refs']):
            group['warnings'].append('대체 관계가 순환합니다. 원칙을 확인해 주세요.')
            continue
        for ref, replacement in active.items():
            if ref in cyclic:
                continue
            if any(r['ref'] in replacement.get('learning', {}).get('supersedes', []) for r in group['refs']):
                if ref in group.get('learning', {}).get('supersedes', []) or replacement is group:
                    group['warnings'].append('대체 관계가 순환합니다. 원칙을 확인해 주세요.')
                else:
                    group['excluded'].append('새 원칙으로 대체됨')
    # Curated canonical links can consolidate paraphrases, but never hide conflicts
    # in applicability or retired/missing sources.
    ref_groups = {r['ref']: g for g in groups for r in g['refs']}
    for group in list(groups):
        canonical = group.get('learning', {}).get('canonical_ref')
        if canonical:
            other = ref_groups.get(canonical)
            if other and other is not group and not other.get('learning', {}).get('canonical_ref') and group.get('learning', {}).get('state') == 'active':
                comparable = ('stages', 'models', 'keywords', 'exclude_keywords', 'stance')
                if all(group['learning'].get(k, []) == other.get('learning', {}).get(k, []) for k in comparable):
                    other['refs'].extend(group['refs'])
                    groups.remove(group)
                    continue
            group['warnings'].append('대표 원칙과 적용 조건을 다시 확인해 주세요.')
    topic_stances, titles = {}, {}
    for g in groups:
        m = g.get('learning', {})
        if not g['excluded'] and m.get('topic') and m.get('stance'):
            topic_stances.setdefault(m['topic'], set()).add(m['stance'])
        titles.setdefault(g['title'], []).append(g['ref'])
    for group in groups:
        # Count distinct projects once even when the same lesson was copied.
        related_refs = {r['ref'] for r in group['refs']}
        counts = {k: set() for k in ('helpful', 'ineffective', 'uncertain')}
        for ref in related_refs:
            for outcome, projects in history.get(ref, {}).items():
                counts[outcome].update(projects)
        group['outcomes'] = {k: len(v) for k, v in counts.items()}
        group['improvement_candidate'] = len(counts['helpful']) >= 2 and not counts['ineffective']
        group['score'] += min(2, len(counts['helpful'])) - min(3, len(counts['ineffective']))
        if counts['ineffective']:
            group['warnings'].append('효과가 없었다는 검수 기록이 있어요.')
        meta = group.get('learning', {})
        if not group['excluded'] and meta.get('stance') and len(topic_stances.get(meta.get('topic'), set())) > 1:
            group['warnings'].append('같은 주제의 다른 방침이 있어요. 적용 조건을 비교해 주세요.')
        group['related'] = [ref for ref in titles[group['title']] if ref != group['ref']][:3]
        if group['related']:
            group['warnings'].append('같은 제목의 별도 기록이 있어요. 자동으로 합치지 않았어요.')
        group['warnings'] = list(dict.fromkeys(group['warnings']))
    eligible = [g for g in groups if not g['excluded'] and not g['warnings']]
    pool = [g for g in groups if '검색어와 일치하지 않음' not in g['excluded']] if browse else eligible
    pool.sort(key=lambda g: (-g['score'], g['ref']))
    page = pool[offset:offset + limit]
    items = [{k: g[k] for k in ('id', 'title', 'action', 'context', 'project_id', 'project_name', 'ref', 'source_hash',
                                'group_id', 'refs', 'topics', 'warnings', 'excluded', 'reasons', 'related', 'outcomes', 'improvement_candidate')}
             for g in page]
    for item, group in zip(items, page):
        item['ref_count'] = len(item['refs'])
        item['refs'] = item['refs'][:20]
        if 'retrospective' in group:
            item['retrospective'] = group['retrospective']
    return {'items': items, 'total': len(pool), 'source_count': len(candidates), 'group_count': len(groups),
            'review_count': len(groups) - len(eligible), 'duplicate_count': len(candidates) - len(groups),
            'offset': offset, 'limit': limit, 'has_more': offset + limit < len(pool), 'stage': stage,
            'plan': plan_view(folder, by_ref) if folder else None,
            'constraints_source': f'{pid}/BRIEF.md' if pid else None,
            'notice': '조건·단어 기반 추천입니다. 현재 요청과 BRIEF의 필수 조건은 개수 제한 없이 별도로 확인하세요.'}


@contextmanager
def plan_lock(folder):
    p = assets.inside(folder, '.lesson-plan.lock')
    try:
        stream = p.open('x', encoding='utf-8')
    except FileExistsError:
        raise ValueError('다른 작업이 적용 기록을 저장 중입니다. 잠시 후 다시 시도해 주세요.') from None
    try:
        yield
    finally:
        stream.close()
        p.unlink()


def save_plan(root, pid, payload):
    folder = project_folder(root.resolve(), pid)
    with plan_lock(folder):
        doc = load_plan(folder)
        if type(payload.get('revision')) is not int or payload['revision'] != doc['revision']:
            raise ValueError('다른 곳에서 적용 기록이 변경됐어요. 새로고침 후 다시 저장해 주세요.')
        operation = payload.get('operation', 'upsert')
        ref = reference(payload.get('ref'))
        prior = next((i for i in doc['items'] if i['ref'] == ref), None)
        by_ref = {r['ref']: r for r in source_rows(root)}
        source = by_ref.get(ref)
        if operation == 'revert':
            event = next((h for h in doc['history'] if h['revision'] == payload.get('history_revision') and h['ref'] == ref), None)
            if not event:
                raise ValueError('복원할 기록을 찾을 수 없습니다.')
            item = event['before']
        elif operation == 'upsert':
            if not source or source['project_id'] == pid or source.get('scope') != 'reusable' or source.get('status') == 'archived' or source.get('learning', {}).get('state') == 'retired':
                raise ValueError('사용 가능한 전작 재사용 피드백을 선택해 주세요.')
            if payload.get('source_hash') != source['source_hash']:
                raise ValueError('원본 피드백이 변경됐어요. 새 내용을 읽고 다시 선택해 주세요.')
            stage = payload.get('stage', 'planned')
            if stage not in ('planned', 'applied', 'reviewed', 'skipped'):
                raise ValueError('적용 단계를 확인해 주세요.')
            cuts = strings(payload.get('cuts', []), 'cuts', 80)
            contract = json.loads(assets.inside(folder, 'project.json').read_text(encoding='utf-8-sig'))
            valid_cuts = {c['id'] for c in contract.get('cuts', [])}
            if not set(cuts) <= valid_cuts:
                raise ValueError('작품에 없는 컷 ID입니다.')
            application = assets.text(payload, 'application', required=True)
            evidence = []
            for rel in strings(payload.get('evidence', []), 'evidence'):
                f = assets.inside(folder, rel)
                if not f.is_file() or rel == 'lesson-plan.json' or rel.startswith('.studio/'):
                    raise ValueError('실제 대본·입력·영상·검수 파일을 근거로 지정해 주세요.')
                evidence.append({'path': rel, 'stamp': stamp(f)})
            if stage in ('applied', 'reviewed') and not evidence:
                raise ValueError('반영한 파일 근거가 필요합니다.')
            outcome = payload.get('outcome', '') if stage == 'reviewed' else ''
            if stage == 'reviewed':
                if outcome not in ('helpful', 'ineffective', 'uncertain'):
                    raise ValueError('영상 검수 결과를 선택해 주세요.')
                videos = {c.get('video') for c in contract.get('cuts', []) if not cuts or c['id'] in cuts}
                videos.add(contract.get('full_video'))
                if not any(e['path'] == 'renders.md' for e in evidence) or not any(e['path'] in videos and Path(e['path']).suffix.lower() in ('.mp4', '.mov', '.webm') for e in evidence):
                    raise ValueError('영상 검수에는 해당 컷 또는 전체본에 등록된 영상과 renders.md 근거가 모두 필요합니다.')
            item = {'ref': ref, 'source_hash': source['source_hash'], 'stage': stage, 'cuts': cuts,
                    'application': application, 'evidence': evidence, 'outcome': outcome}
        else:
            raise ValueError('지원하지 않는 적용 기록 작업입니다.')
        doc['revision'] += 1
        doc['history'].append({'revision': doc['revision'], 'ref': ref, 'operation': operation,
                               'at': time.time(), 'before': prior, 'after': item})
        doc['items'] = [i for i in doc['items'] if i['ref'] != ref] + ([item] if item else [])
        assets.atomic(assets.inside(folder, 'lesson-plan.json'), doc)
        return plan_view(folder, by_ref)
