"""Generation ledger for the Studio: per-cut image/video versions, cost estimates, publication status, channel comparison.

Read-only over shots/, exports/ and youtube-analytics.json. The only writes are adopt() (through project_store.upsert_cut)
and save_credits() (root/.studio/credits.json). Prices and credit rates are the values recorded in docs/runbooks/paid-generation.md
on 2026-09-15; confirmed billing lives in the provider dashboards, so every figure here is an estimate.
"""
from datetime import datetime, timezone
from pathlib import Path
import json, re, uuid
import project_store

GPT_IMAGE_USD_PER_M = {'image_input': 8.0, 'text_input': 5.0, 'output': 30.0}
H3_CREDITS_PER_SECOND = 2          # 9:16 · 2K: 5s = 10, 6s = 12
DEFAULT_CLIP_SECONDS = 6
VIEWS_WALL = 1300                  # concept.md 성과 판정: 1차 배포 벽
VERSION = re.compile(r'^([a-z0-9]+)-v(\d{3})$')
CREDIT_SERVICES = ('higgsfield', 'openai')
STATUS_LABEL = {'scheduled': '예약됨', 'published': '공개', 'public': '공개', 'private': '비공개', 'superseded_private': '비공개 보존',
                'unlisted': '일부 공개', 'deleted': '삭제됨', None: '게시 기록'}
HIDDEN_STATUSES = {'private', 'superseded_private', 'deleted'}


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def image_cost(usage):
    if not isinstance(usage, dict):
        return None
    detail = usage.get('input_tokens_details') or {}
    tokens = (detail.get('image_tokens') or 0, detail.get('text_tokens') or 0, usage.get('output_tokens') or 0)
    if not all(isinstance(t, (int, float)) for t in tokens):
        return None
    image_in, text_in, out = tokens
    return round((image_in * GPT_IMAGE_USD_PER_M['image_input'] + text_in * GPT_IMAGE_USD_PER_M['text_input'] + out * GPT_IMAGE_USD_PER_M['output']) / 1e6, 4)


def cut_versions(folder, cut_id):
    """Every shots/<cut>/<kind>-vNNN folder: images carry planned-start.png, videos carry result.mp4."""
    images, videos = [], []
    base = folder / 'shots' / cut_id
    if not base.is_dir() or not base.resolve().is_relative_to(folder.resolve()):
        return images, videos
    for d in sorted(base.iterdir()):
        m = VERSION.match(d.name)
        if not d.is_dir() or not m:
            continue
        rel = lambda name: (d / name).relative_to(folder).as_posix()
        exists = lambda name: (d / name).is_file()
        req = read_json(d / 'request.json', {}) or {}
        if not isinstance(req, dict):
            req = {}
        if exists('planned-start.png'):
            images.append({'version': d.name, 'label': 'v' + m.group(2), 'path': rel('planned-start.png'), 'model': req.get('model', ''),
                           'size': req.get('size', ''), 'quality': req.get('quality', ''), 'generated_at': req.get('generated_at'),
                           'cost_usd': image_cost(req.get('usage')), 'review': req.get('review'), 'reference_roles': req.get('reference_roles') or []})
        if exists('result.mp4'):
            res = read_json(d / 'result.json', {}) or {}
            if not isinstance(res, dict):
                res = {}
            duration = res.get('duration') if isinstance(res.get('duration'), (int, float)) else req.get('duration')
            credits = res.get('credits_est')
            if not isinstance(credits, (int, float)) and isinstance(req.get('duration'), (int, float)):
                credits = req['duration'] * H3_CREDITS_PER_SECOND
            asr = read_json(d / 'asr.json', {}) or {}
            videos.append({'version': d.name, 'label': 'v' + m.group(2), 'path': rel('result.mp4'), 'model': req.get('model', ''),
                           'job_id': req.get('job_id'), 'status': res.get('status', 'completed'), 'duration': duration,
                           'credits': credits if isinstance(credits, (int, float)) else None, 'collected_at': res.get('collected_at'), 'review': res.get('review'),
                           'first_frame': rel('first-frame.png') if exists('first-frame.png') else None,
                           'end_frame': rel('actual-end.png') if exists('actual-end.png') else None,
                           'contact_sheet': rel('frames-contact.jpg') if exists('frames-contact.jpg') else None,
                           'asr': asr.get('text') if isinstance(asr, dict) and isinstance(asr.get('text'), str) else None})
    return images, videos


def failed_submissions(folder):
    count = 0
    for f in folder.glob('assets/production/*/submitted-jobs-*.json'):
        doc = read_json(f, {}) or {}
        if isinstance(doc, dict) and isinstance(doc.get('failed_submissions'), list):
            count += len(doc['failed_submissions'])
    return count


def summary(folder, cuts, versions, balance=None):
    """cuts: contract rows (dicts with id/video); versions: {cut_id: (images, videos)}."""
    image_count = video_count = retries = 0
    image_cost_usd = 0.0
    credits_used = 0
    image_cuts = 0
    for cid, (images, videos) in versions.items():
        image_count += len(images)
        image_cuts += bool(images)
        image_cost_usd += sum(v['cost_usd'] or 0 for v in images)
        video_count += len(videos)
        retries += max(0, len(videos) - 1)
        credits_used += sum(v['credits'] or 0 for v in videos)
    pending = [c['id'] for c in cuts if not c.get('video')]
    pending_credits = len(pending) * DEFAULT_CLIP_SECONDS * H3_CREDITS_PER_SECOND
    out = {'image_count': image_count, 'image_cuts': image_cuts, 'image_cost_usd': round(image_cost_usd, 2),
           'video_count': video_count, 'retries': retries, 'credits_used': credits_used, 'failed_submissions': failed_submissions(folder),
           'pending_video_cuts': len(pending), 'pending_credits': pending_credits, 'balance': balance,
           'credits_short': None, 'rates': {'h3_credits_per_second': H3_CREDITS_PER_SECOND, 'clip_seconds': DEFAULT_CLIP_SECONDS, 'gpt_image_usd_per_m': GPT_IMAGE_USD_PER_M}}
    if balance and isinstance(balance.get('balance'), (int, float)):
        out['credits_short'] = round(max(0, pending_credits - balance['balance']), 1)
    return out


def credits_path(root):
    return root / '.studio' / 'credits.json'


def credits(root):
    doc = read_json(credits_path(root), {}) or {}
    return doc if isinstance(doc, dict) else {}


def save_credits(root, data):
    service = data.get('service')
    if service not in CREDIT_SERVICES:
        raise ValueError('잔액을 기록할 서비스를 확인해 주세요.')
    balance = data.get('balance')
    if isinstance(balance, bool) or not isinstance(balance, (int, float)) or balance < 0 or balance > 1e9:
        raise ValueError('잔액은 0 이상의 숫자로 입력해 주세요.')
    note = str(data.get('note') or '')[:300]
    doc = credits(root)
    doc[service] = {'balance': balance, 'as_of': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'), 'note': note, 'source': 'studio_manual'}
    path = credits_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)
    return {'ok': True, 'credits': doc}


def publications(folder):
    rows = []
    for f in sorted(folder.glob('exports/*/youtube-publication.json')):
        doc = read_json(f, {}) or {}
        if not isinstance(doc, dict) or not doc.get('video_id'):
            continue
        status = doc.get('status') or doc.get('privacy') or None
        rows.append({'file': f.relative_to(folder).as_posix(), 'video_id': doc.get('video_id'), 'url': doc.get('url') or f"https://www.youtube.com/watch?v={doc['video_id']}",
                     'title': doc.get('title') or doc['video_id'], 'status': status, 'label': STATUS_LABEL.get(status, status),
                     'hidden': status in HIDDEN_STATUSES, 'date': doc.get('date'), 'scheduled_publish_at': doc.get('scheduled_publish_at'),
                     'uploaded_at': doc.get('uploaded_at'), 'published_at': doc.get('published_at'), 'source': doc.get('source'),
                     'replaces_video_id': doc.get('replaces_video_id'), 'note': doc.get('note') or '', 'channel_id': doc.get('channel_id'),
                     'history_count': len(doc.get('history') or []) + len(doc.get('schedule_history') or [])})
    rows.sort(key=lambda r: (r['hidden'], -(datetime.fromisoformat(r['uploaded_at']).timestamp() if isinstance(r.get('uploaded_at'), str) and _iso(r['uploaded_at']) else 0), r['file']))
    return rows


def _iso(value):
    try:
        datetime.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def project_channel(folder):
    """Channel id recorded in this project's publication or analytics files (None when the project never published)."""
    for pub in folder.glob('exports/*/youtube-publication.json'):
        doc = read_json(pub, {}) or {}
        if isinstance(doc, dict) and isinstance(doc.get('channel_id'), str):
            return doc['channel_id']
    doc = read_json(folder / 'youtube-analytics.json', {}) or {}
    for link in (doc.get('links') if isinstance(doc, dict) and isinstance(doc.get('links'), list) else []):
        if isinstance(link, dict) and isinstance(link.get('channel_id'), str):
            return link['channel_id']
    return None


def channel(root, project_rows, channel_id):
    """One row per publicly visible video of the given channel across projects, with its most complete performance snapshot.
    Other channels (e.g. 낯선 30초, 반야) are never listed; without a channel id nothing is compared."""
    rows = []
    if not isinstance(channel_id, str) or not channel_id:
        return {'wall': VIEWS_WALL, 'channel_id': None, 'rows': rows}
    for pr in project_rows:
        folder = root / pr['id']
        if project_channel(folder) != channel_id:
            continue
        folder = root / pr['id']
        if not folder.resolve().is_relative_to(root.resolve()):
            continue
        doc = read_json(folder / 'youtube-analytics.json', {}) or {}
        links = doc.get('links') if isinstance(doc, dict) and isinstance(doc.get('links'), list) else []
        snaps = doc.get('snapshots') if isinstance(doc, dict) and isinstance(doc.get('snapshots'), list) else []
        pubs = publications(folder)
        seen = set()
        for pub in pubs + [dict(video_id=l.get('video_id'), status=None, label=STATUS_LABEL[None], hidden=False, title=l.get('title'), url=l.get('url'), date=l.get('published_date'), scheduled_publish_at=None) for l in links if isinstance(l, dict)]:
            vid = pub.get('video_id')
            if not vid or vid in seen:
                continue
            seen.add(vid)
            if pub.get('hidden'):
                continue
            link = next((l for l in links if isinstance(l, dict) and l.get('video_id') == vid), {})
            # Lifetime views only grow, so the snapshot with the most views is the most complete one (a partial API window can trail a Studio reading).
            latest = max((s for s in snaps if isinstance(s, dict) and s.get('video_id') == vid), key=lambda s: (s.get('metrics', {}).get('views') or 0, s.get('as_of') or ''), default=None)
            m = latest.get('metrics', {}) if latest else {}
            views = m.get('views')
            rows.append({'project': pr['id'], 'project_name': pr['name'], 'video_id': vid, 'title': pub.get('title') or link.get('title') or vid,
                         'url': pub.get('url') or link.get('url'), 'published_date': link.get('published_date') or pub.get('date'),
                         'status': pub.get('status'), 'label': pub.get('label'), 'scheduled_publish_at': pub.get('scheduled_publish_at'),
                         'as_of': latest.get('as_of') if latest else None, 'source': latest.get('source') if latest else None,
                         'views': views, 'stayed': m.get('stayedToWatch'), 'avg_pct': m.get('averageViewPercentage'),
                         'likes': m.get('likes'), 'subs': m.get('subscribersNet'),
                         'over_wall': isinstance(views, (int, float)) and views >= VIEWS_WALL})
    rows.sort(key=lambda r: (r.get('published_date') or '', r.get('scheduled_publish_at') or ''), reverse=True)
    return {'wall': VIEWS_WALL, 'channel_id': channel_id, 'rows': rows}


def adopt(folder, cut_id, kind, version):
    """Point project.json at another generated version. Never deletes or renames media."""
    if kind not in ('image', 'video'):
        raise ValueError('채택할 종류를 확인해 주세요.')
    if not isinstance(version, str) or not VERSION.match(version) or not isinstance(cut_id, str):
        raise ValueError('버전 이름을 확인해 주세요.')
    d = folder / 'shots' / cut_id / version
    if not d.resolve().is_relative_to(folder.resolve()) or not d.is_dir():
        raise ValueError('없는 버전입니다.')
    rel = lambda name: (d / name).relative_to(folder).as_posix()
    if kind == 'image':
        if not (d / 'planned-start.png').is_file():
            raise ValueError('계획 이미지가 없는 버전입니다.')
        patch = {'id': cut_id, 'planned_start_image': rel('planned-start.png')}
    else:
        if not (d / 'result.mp4').is_file():
            raise ValueError('영상이 없는 버전입니다.')
        res = read_json(d / 'result.json', {}) or {}
        patch = {'id': cut_id, 'status': 'review', 'video': rel('result.mp4'),
                 'end_image': rel('actual-end.png') if (d / 'actual-end.png').is_file() else None,
                 'request_file': rel('request.json') if (d / 'request.json').is_file() else None,
                 'duration': res.get('duration') if isinstance(res, dict) and isinstance(res.get('duration'), (int, float)) else None}
        reg = read_json(d / 'registration.json', {}) or {}
        if isinstance(reg, dict) and reg.get('id') == cut_id:
            patch.update({k: v for k, v in reg.items() if k in ('video', 'input_image', 'end_image', 'request_file', 'duration', 'status')})
    return project_store.upsert_cut(folder, patch)
