"""Project-owned character references and feedback. Never writes .studio state."""
from pathlib import Path
import argparse
import base64
import json
import re
import time
import uuid

FILES = {'characters': 'characters.json', 'feedback': 'feedback.json'}
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}')
TAGS = ('기획', '인물', '카메라', '연기', '연속성', '사운드', '프롬프트', '검수', '작업방식')


def inside(folder, relative):
    if not isinstance(relative, str) or not relative or ':' in relative or '\\' in relative or Path(relative).is_absolute():
        raise ValueError('작품 안의 상대 경로를 사용해 주세요.')
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder.resolve()):
        raise ValueError('작품 폴더 밖의 파일은 사용할 수 없습니다.')
    return target


def empty():
    return {'schema_version': 1, 'revision': 0, 'items': []}


def load(folder, kind):
    target = inside(folder, FILES[kind])
    if not target.exists():
        return empty()
    value = json.loads(target.read_text(encoding='utf-8-sig'))
    if value.get('schema_version') != 1 or not isinstance(value.get('items'), list) or not isinstance(value.get('revision'), int):
        raise ValueError(FILES[kind] + ' 형식을 확인해 주세요.')
    return value


def atomic(target, value):
    temp = target.with_name('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(target)


def text(item, field, required=False, limit=6000):
    value = item.get(field, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(field + ': 내용을 확인해 주세요.')
    return value.strip()


def clean(folder, kind, item):
    if not isinstance(item, dict) or not ID.fullmatch(item.get('id', '')):
        raise ValueError('유효한 기록 ID가 필요합니다.')
    row = {'id': item['id']}
    if kind == 'characters':
        for key in ('name', 'role', 'description', 'appearance', 'wardrobe', 'performance', 'continuity', 'source'):
            row[key] = text(item, key, required=key == 'name')
        row['status'] = item.get('status', 'draft')
        if row['status'] not in ('draft', 'reference', 'approved'):
            raise ValueError('인물 상태를 확인해 주세요.')
        images = item.get('images', [])
        if not isinstance(images, list) or len(images) > 24:
            raise ValueError('인물 이미지는 최대 24장입니다.')
        row['images'] = []
        for image in images:
            if not isinstance(image, dict):
                raise ValueError('이미지 항목을 확인해 주세요.')
            f = inside(folder, image.get('path'))
            if not f.is_file() or f.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('존재하는 PNG·JPG·WEBP 이미지를 사용해 주세요.')
            role = image.get('kind', 'reference')
            if role not in ('reference', 'sheet', 'detail'):
                raise ValueError('이미지 종류를 확인해 주세요.')
            row['images'].append({'path': image['path'], 'label': text(image, 'label'), 'kind': role})
    else:
        for key in ('title', 'observation', 'action', 'context', 'evidence', 'source'):
            row[key] = text(item, key, required=key in ('title', 'observation', 'action'))
        row['scope'] = item.get('scope', 'project')
        row['status'] = item.get('status', 'open')
        row['origin'] = item.get('origin', 'user')
        if row['scope'] not in ('project', 'reusable') or row['status'] not in ('open', 'applied', 'archived') or row['origin'] not in ('user', 'review', 'reference'):
            raise ValueError('피드백 분류를 확인해 주세요.')
        tags = item.get('tags', [])
        if not isinstance(tags, list) or any(t not in TAGS for t in tags):
            raise ValueError('피드백 태그를 확인해 주세요.')
        row['tags'] = list(dict.fromkeys(tags))
        if item.get('retrospective') is not None:
            from youtube_analytics import validate_retrospective
            row['retrospective'] = validate_retrospective(folder, item['retrospective'])
    return row


def upsert(folder, kind, item, revision=None):
    current = load(folder, kind)
    if revision is not None and revision != current['revision']:
        raise ValueError('다른 곳에서 기록이 변경됐어요. 입력 내용을 복사해 두고 다시 열어 주세요.')
    prior = next((i for i in current['items'] if i['id'] == item.get('id')), None)
    row = clean(folder, kind, {**(prior or {}), **item})
    row['created_at'] = prior.get('created_at', time.time()) if prior else time.time()
    row['updated_at'] = time.time()
    if prior:
        current['items'][current['items'].index(prior)] = row
    else:
        current['items'].append(row)
    current['revision'] += 1
    atomic(inside(folder, FILES[kind]), current)
    return current


def upload_character(folder, data):
    current = load(folder, 'characters')
    if data.get('revision') != current['revision']:
        raise ValueError('인물 정보가 변경됐어요. 다시 열어 주세요.')
    item = next((x for x in current['items'] if x['id'] == data.get('id')), None)
    if not item:
        raise ValueError('인물 설명을 먼저 저장해 주세요.')
    raw = base64.b64decode(data.get('bytes', ''), validate=True)
    ext = Path(str(data.get('name', ''))).suffix.lower()
    good = (ext == '.png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (ext in ('.jpg', '.jpeg') and raw.startswith(b'\xff\xd8\xff')) or (ext == '.webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP')
    if not good or len(raw) > 20 * 1024 * 1024:
        raise ValueError('PNG·JPG·WEBP, 최대 20MB 이미지를 선택해 주세요.')
    rel = f"references/characters/{item['id']}/images/{uuid.uuid4().hex}{ext}"
    f = inside(folder, rel)
    candidate = {**item, 'images': item['images'] + [{'path': rel, 'label': str(data.get('label', Path(data['name']).name)), 'kind': data.get('kind', 'reference')}]}
    if len(candidate['images']) > 24 or candidate['images'][-1]['kind'] not in ('sheet', 'reference', 'detail'):
        raise ValueError('이미지 종류 또는 개수를 확인해 주세요.')
    f.parent.mkdir(parents=True, exist_ok=True)
    inside(folder, rel).write_bytes(raw)
    return upsert(folder, 'characters', candidate, data['revision'])


def reusable(projects):
    result = []
    for pid, name, folder in projects:
        for row in load(folder, 'feedback')['items']:
            if row.get('scope') == 'reusable' and row.get('status') != 'archived':
                result.append({**row, 'project_id': pid, 'project_name': name})
    return result


def main():
    parser = argparse.ArgumentParser(description='Character sheets and feedback registry')
    parser.add_argument('command', choices=['list', 'upsert', 'lessons'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--kind', choices=FILES)
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    if args.command == 'lessons':
        folders = sorted((args.path / 'productions').glob('*/*/BRIEF.md'))
        records = []
        for brief in folders:
            folder = brief.parent
            info = json.loads((folder / 'project.json').read_text(encoding='utf-8-sig')) if (folder / 'project.json').exists() else {}
            records.append((folder.relative_to(args.path).as_posix(), info.get('title', folder.name), folder))
        result = reusable(records)
    else:
        if not args.kind:
            parser.error('--kind is required')
        if args.command == 'upsert':
            if not args.file:
                parser.error('--file is required')
            result = upsert(args.path, args.kind, json.loads(args.file.read_text(encoding='utf-8-sig')))
        else:
            result = load(args.path, args.kind)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
