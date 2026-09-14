"""Publication links and immutable, source-labelled performance snapshots."""
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from urllib.parse import urlparse, parse_qs
import uuid

import production_assets as assets
import youtube_auth as auth

FILE = 'youtube-analytics.json'
VIDEO = re.compile(r'[A-Za-z0-9_-]{11}')
CHANNEL = re.compile(r'UC[A-Za-z0-9_-]{22}')
METRICS = {
    'views': ('조회수', '회'), 'engagedViews': ('유효 조회수', '회'),
    'averageViewDuration': ('평균 시청 시간', '초'),
    'averageViewPercentage': ('평균 조회율', '%'),
    'estimatedMinutesWatched': ('총 시청 시간', '분'),
    'subscribersGained': ('구독자 증가', '명'), 'subscribersLost': ('구독자 감소', '명'),
    'subscribersNet': ('구독자 순증', '명'), 'likes': ('좋아요', '개'),
    'comments': ('댓글', '개'), 'shares': ('공유', '회'),
    'stayedToWatch': ('계속 시청함', '%'), 'swipedAway': ('이탈함', '%')}
INTEGER = {'views', 'engagedViews', 'subscribersGained', 'subscribersLost', 'subscribersNet', 'likes', 'comments', 'shares'}
API_METRICS = [k for k in METRICS if k not in ('subscribersNet', 'stayedToWatch', 'swipedAway')]


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load(folder):
    path = assets.inside(folder, FILE)
    if not path.exists():
        return {'schema_version': 1, 'revision': 0, 'links': [], 'snapshots': []}
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    if doc.get('schema_version') != 1 or not isinstance(doc.get('revision'), int) or not isinstance(doc.get('links'), list) or not isinstance(doc.get('snapshots'), list):
        raise ValueError('유튜브 성과 기록 형식을 확인해 주세요.')
    return doc


def save(folder, doc):
    doc['revision'] += 1
    assets.atomic(assets.inside(folder, FILE), doc)
    return doc


def check_revision(doc, revision):
    if revision != doc['revision']:
        raise ValueError('성과 기록이 변경되었습니다. 입력을 복사해 두고 다시 열어 주세요.')


def video_id(value):
    if not isinstance(value, str):
        raise ValueError('YouTube 영상 주소 또는 ID를 입력해 주세요.')
    value = value.strip()
    if VIDEO.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('https로 시작하는 YouTube 영상 주소를 입력해 주세요.')
    parts = parsed.path.strip('/').split('/')
    found = ''
    if parsed.hostname == 'youtu.be' and len(parts) == 1:
        found = parts[0]
    elif parsed.hostname in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch': found = parse_qs(parsed.query).get('v', [''])[0]
        elif len(parts) == 2 and parts[0] in ('shorts', 'embed', 'live'): found = parts[1]
    if not VIDEO.fullmatch(found):
        raise ValueError('YouTube 동영상 또는 Shorts 주소를 확인해 주세요.')
    return found


def day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('날짜를 YYYY-MM-DD 형식으로 입력해 주세요.')
    try: return date.fromisoformat(value)
    except ValueError: raise ValueError('날짜를 확인해 주세요.') from None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None: raise ValueError()
        return parsed.isoformat(timespec='seconds')
    except (ValueError, AttributeError, TypeError):
        raise ValueError('확인 시각에는 시간대가 필요합니다.') from None


def clean_link(folder, item):
    ident = video_id(item.get('video_id', item.get('url')))
    channel = item.get('channel_id', '')
    if channel and (not isinstance(channel, str) or not CHANNEL.fullmatch(channel)):
        raise ValueError('채널 ID를 확인해 주세요.')
    published = item.get('published_date', '')
    if published: day(published)
    source = item.get('source', '')
    if source:
        path = assets.inside(folder, source)
        if path.suffix.lower() != '.mp4' or not path.is_file():
            raise ValueError('작품 안에 있는 업로드 원본 MP4를 선택해 주세요.')
    return {'video_id': ident, 'channel_id': channel,
            'url': 'https://www.youtube.com/watch?v=' + ident,
            'title': assets.text(item, 'title', limit=300) or ident,
            'published_date': published, 'source': source,
            'publication_file': assets.text(item, 'publication_file', limit=500)}


def discoveries(folder):
    folder = folder.resolve()
    result = []
    for path in sorted((folder / 'exports').glob('*/youtube-publication.json')):
        try:
            path = assets.inside(folder, path.relative_to(folder).as_posix())
            item = json.loads(path.read_text(encoding='utf-8-sig'))
            if item.get('status') != 'published': continue
            result.append(clean_link(folder, {**item, 'published_date': item.get('date', ''),
                'publication_file': path.relative_to(folder).as_posix()}))
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return result


def public(folder):
    doc = load(folder)
    return {**doc, 'discovered': [r for r in discoveries(folder) if r['video_id'] not in {x['video_id'] for x in doc['links']}],
            'metric_definitions': METRICS}


def link(folder, item, revision):
    doc = load(folder); check_revision(doc, revision)
    row = clean_link(folder, item)
    prior = next((r for r in doc['links'] if r['video_id'] == row['video_id']), None)
    if prior: doc['links'][doc['links'].index(prior)] = row
    else: doc['links'].append(row)
    return save(folder, doc)


def clean_metrics(values):
    if not isinstance(values, dict) or set(values) - set(METRICS):
        raise ValueError('지원하지 않는 성과 항목입니다.')
    result = {}
    for key in METRICS:
        value = values.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or abs(value) > 1e15:
                raise ValueError(METRICS[key][0] + ': 숫자를 확인해 주세요.')
            if (key != 'subscribersNet' and value < 0) or (key in INTEGER and int(value) != value):
                raise ValueError(METRICS[key][0] + ': 범위를 확인해 주세요.')
            if key in ('stayedToWatch', 'swipedAway') and value > 100:
                raise ValueError('계속 시청·이탈 비율은 0~100입니다.')
        result[key] = value
    a, b = result['stayedToWatch'], result['swipedAway']
    if a is not None and b is not None and abs(a + b - 100) > .2:
        raise ValueError('계속 시청·이탈 비율의 합계를 확인해 주세요.')
    return result


def add_snapshot(folder, item, revision, api=False):
    doc = load(folder); check_revision(doc, revision)
    ident = video_id(item.get('video_id'))
    publication = next((r for r in doc['links'] if r['video_id'] == ident), None)
    if not publication:
        raise ValueError('작품에 영상을 먼저 연결해 주세요.')
    start, end = day(item.get('start_date')), day(item.get('end_date'))
    if end < start: raise ValueError('종료일은 시작일 이후여야 합니다.')
    metrics = clean_metrics(item.get('metrics'))
    if not any(v is not None for v in metrics.values()):
        raise ValueError('확인한 지표를 하나 이상 입력해 주세요. 미집계 값은 비워 두세요.')
    source_path = assets.inside(folder, publication['source']) if publication.get('source') else None
    if source_path and not source_path.is_file():
        raise ValueError('연결한 업로드 원본을 찾을 수 없습니다. 영상 연결을 확인해 주세요.')
    source_stamp = [source_path.stat().st_size, source_path.stat().st_mtime_ns] if source_path else None
    row = {'video_id': ident, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
           'as_of': timestamp(item.get('as_of', now())), 'source': 'youtube_api' if api else 'studio_manual',
           'source_url': f'https://studio.youtube.com/video/{ident}/analytics',
           'period_basis': 'YouTube API 날짜(Pacific Time)' if api else 'Studio 화면 선택 기간',
           'source_file': publication.get('source', ''), 'published_date': publication.get('published_date', ''),
           'source_stamp': source_stamp,
           'note': assets.text(item, 'note', limit=3000), 'metrics': metrics,
           'traffic': item.get('traffic', []) if api else [],
           'retention': item.get('retention', []) if api else [],
           'daily': item.get('daily', []) if api else [],
           'warnings': item.get('warnings', []) if api else [],
           'available_through': item.get('available_through') if api else None}
    fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if any(r.get('fingerprint') == fingerprint for r in doc['snapshots']): return doc
    row.update(id=uuid.uuid4().hex, recorded_at=now(), fingerprint=fingerprint)
    doc['snapshots'].append(row)
    return save(folder, doc)


def rows(response):
    columns = [c['name'] for c in response.get('columnHeaders', [])]
    return [dict(zip(columns, r)) for r in response.get('rows', [])]


def collect(folder, ident, start_date, end_date):
    doc = load(folder)
    item = next((r for r in doc['links'] if r['video_id'] == video_id(ident)), None)
    if not item: raise ValueError('작품에 영상을 먼저 연결해 주세요.')
    start, end = day(start_date), day(end_date)
    if end < start or (end - start).days > 3660:
        raise ValueError('조회 기간은 10년 이내로 설정해 주세요.')
    token, channel = auth.access()
    metadata = auth.request_json('https://www.googleapis.com/youtube/v3/videos',
        {'part': 'snippet,contentDetails', 'id': ident}, bearer=token).get('items', [])
    if not metadata or metadata[0]['snippet']['channelId'] != channel['id'] or (item['channel_id'] and item['channel_id'] != channel['id']):
        raise ValueError('이 영상의 소유 채널로 Google 계정을 연결해 주세요.')
    def query(metrics, dimensions=None):
        params = {'ids': 'channel==' + channel['id'], 'startDate': start.isoformat(), 'endDate': end.isoformat(),
                  'filters': 'video==' + ident, 'metrics': metrics}
        if dimensions: params['dimensions'] = dimensions
        if dimensions == 'day': params['sort'] = 'day'
        return rows(auth.request_json('https://youtubeanalytics.googleapis.com/v2/reports', params, bearer=token))
    summary = query(','.join(API_METRICS))
    if not summary:
        raise ValueError('선택한 기간의 API 데이터가 아직 없습니다. 0으로 저장하지 않았습니다. 날짜를 바꾸거나 나중에 다시 가져오세요.')
    metrics = {k: summary[0].get(k) for k in API_METRICS}
    a, b = metrics.get('subscribersGained'), metrics.get('subscribersLost')
    if a is not None and b is not None: metrics['subscribersNet'] = a - b
    warnings = ['계속 시청함·이탈함은 이 API 연결에서 수집하지 않습니다. Studio 화면 기록으로 보완할 수 있습니다.',
                '최근 데이터는 처리 중일 수 있습니다. 요청 종료일과 실제 집계 범위를 구분해 주세요.']
    extra = {}
    for key, metric, dimension in [('traffic', 'views', 'insightTrafficSourceType'),
                                   ('retention', 'audienceWatchRatio', 'elapsedVideoTimeRatio'),
                                   ('daily', ','.join(API_METRICS), 'day')]:
        try:
            extra[key] = query(metric, dimension)
            if not extra[key]: warnings.append({'retention':'구간별 유지율', 'traffic':'유입 경로', 'daily':'일별 성과'}[key] + ': 아직 제공되는 데이터가 없습니다.')
        except auth.GoogleError as error:
            extra[key] = []
            warnings.append({'retention':'구간별 유지율', 'traffic':'유입 경로', 'daily':'일별 성과'}[key] + ': ' + str(error))
    return {'video_id': ident, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'as_of': now(), 'metrics': metrics, **extra, 'warnings': warnings,
            'available_through': max((r['day'] for r in extra['daily']), default=None),
            'note': 'YouTube Analytics API에서 가져온 값. 해석과 제작 가설은 별도 회고에 기록합니다.'}


def draft(folder, ident, snapshot_id):
    doc = load(folder)
    snapshot = next((r for r in doc['snapshots'] if r['id'] == snapshot_id and r['video_id'] == ident), None)
    if not snapshot: raise ValueError('회고에 사용할 성과 기록을 선택해 주세요.')
    facts = [f'{METRICS[k][0]} {v:g}{METRICS[k][1]}' for k, v in snapshot['metrics'].items() if v is not None]
    return {'title': '유튜브 성과 회고 · 검증 전', 'observation': '확인한 사실: ' + ', '.join(facts),
            'action': '다음 실험: 변경할 장면이나 표현 한 가지와 비교할 지표를 작성하세요.',
            'context': '검증 전 가설입니다. 영상 길이·주제·게시 후 경과 기간과 유입 경로가 비슷한 작품끼리 비교합니다.',
            'evidence': f"{FILE} / snapshot {snapshot['id']} / {ident}",
            'source': f"{'YouTube API' if snapshot['source']=='youtube_api' else 'Studio 화면 기록'} · {snapshot['start_date']}~{snapshot['end_date']} · 확인 {snapshot['as_of']}",
            'origin': 'review', 'scope': 'project', 'status': 'open', 'tags': ['기획', '검수'],
            'retrospective': {'video_id': ident, 'snapshot_id': snapshot['id'],
                              'hypothesis': '', 'experiment': '', 'success_measure': '', 'scene_seconds': None,
                              'confidence': 'hypothesis'}}


def validate_retrospective(folder, value):
    if not isinstance(value, dict): raise ValueError('회고 형식을 확인해 주세요.')
    ident = video_id(value.get('video_id'))
    sid = value.get('snapshot_id')
    if not any(s['id'] == sid and s['video_id'] == ident for s in load(folder)['snapshots']):
        raise ValueError('이 작품의 성과 기록을 근거로 선택해 주세요.')
    result = {'video_id': ident, 'snapshot_id': sid}
    for key in ('hypothesis', 'experiment', 'success_measure'):
        result[key] = assets.text(value, key, required=True, limit=3000)
    result['confidence'] = value.get('confidence', 'hypothesis')
    if result['confidence'] not in ('hypothesis', 'supported', 'inconclusive'):
        raise ValueError('가설 검증 상태를 확인해 주세요.')
    seconds = value.get('scene_seconds')
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not 0 <= seconds <= 86400):
        raise ValueError('장면 시각은 초 단위로 입력해 주세요.')
    result['scene_seconds'] = seconds
    return result
