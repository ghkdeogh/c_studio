"""Role-based checklist state per project (craft/roles/checklist.json) and pre-upload review material.

State file: <project>/role-review.json
  {"schema_version": 1, "revision": n, "checks": {item_id: {"status": "pending|pass|fail|na", "note": str, "by": str, "at": epoch}}}
CLI (repo root):
  python -B _infra/creative-studio/role_review.py status  productions/video/<p>
  python -B _infra/creative-studio/role_review.py set     productions/video/<p> --item rev-anatomy --status pass --note "..." --by editor
  python -B _infra/creative-studio/role_review.py prepare productions/video/<p> --video exports/<final>/final.mp4
     -> exports/<final>/role-review/: frames-NN.jpg (0.25 s, 540 px wide, timestamped), loudness.txt, sound-windows.txt
  python -B _infra/creative-studio/role_review.py gate    productions/video/<p> [--stages review,publish]
     -> exit 1 and list items that are not pass/na (upload gate)
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = ROOT / 'craft/roles/checklist.json'
STATUSES = ('pending', 'pass', 'fail', 'na')


class ReviewError(ValueError):
    pass


def checklist():
    return json.loads(CHECKLIST.read_text(encoding='utf-8'))


def state_path(folder):
    return Path(folder) / 'role-review.json'


def load(folder):
    p = state_path(folder)
    if not p.exists():
        return {'schema_version': 1, 'revision': 0, 'checks': {}}
    value = json.loads(p.read_text(encoding='utf-8'))
    if value.get('schema_version') != 1 or not isinstance(value.get('checks'), dict):
        raise ReviewError('role-review.json 형식이 올바르지 않습니다.')
    return value


def view(folder):
    """Checklist merged with the project's state, for the studio panel."""
    spec, state = checklist(), load(folder)
    items = []
    for it in spec['items']:
        c = state['checks'].get(it['id'], {})
        items.append({**it, 'status': c.get('status', 'pending'), 'note': c.get('note', ''), 'by': c.get('by', ''), 'at': c.get('at')})
    return {'roles': spec['roles'], 'stages': spec['stages'], 'items': items, 'revision': state['revision']}


def set_check(folder, item, status, note='', by='', revision=None):
    ids = {it['id'] for it in checklist()['items']}
    if item not in ids:
        raise ReviewError(f'알 수 없는 점검 항목: {item}')
    if status not in STATUSES:
        raise ReviewError(f'상태는 {", ".join(STATUSES)} 중 하나여야 합니다.')
    if len(note) > 2000 or len(by) > 80:
        raise ReviewError('메모가 너무 깁니다.')
    state = load(folder)
    if revision is not None and int(revision) != state['revision']:
        raise ReviewError('다른 곳에서 먼저 바뀌었습니다. 새로고침 후 다시 저장해 주세요.')
    state['checks'][item] = {'status': status, 'note': note, 'by': by, 'at': time.time()}
    state['revision'] += 1
    p = state_path(folder)
    tmp = p.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(p)
    return view(folder)


def gate(folder, stages=('review', 'publish')):
    return [it for it in view(folder)['items'] if it['stage'] in stages and it['status'] not in ('pass', 'na')]


def prepare(folder, video):
    folder = Path(folder); src = folder / video
    if not src.exists():
        raise ReviewError(f'영상이 없습니다: {video}')
    out = src.parent / 'role-review'; out.mkdir(exist_ok=True)
    # label with frame time t: pts-based labels read +2.0 s on these exports (found 2026-10-06)
    dt = "drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='%{eif\\:t\\:d}.%{eif\\:mod(t*100\\,100)\\:d\\:2}':x=8:y=8:fontsize=30:fontcolor=yellow:box=1:boxcolor=black"
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', f'fps=4,scale=540:-1,{dt},tile=6x2', str(out / 'frames-%02d.jpg')], check=True)
    loud = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(src), '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    (out / 'loudness.txt').write_text(loud[loud.rfind('Summary'):], encoding='utf-8')
    err = subprocess.run(['ffmpeg', '-i', str(src), '-af', 'silencedetect=noise=-35dB:d=0.25', '-f', 'null', '-'], capture_output=True, text=True).stderr
    (out / 'sound-windows.txt').write_text('\n'.join(l for l in err.splitlines() if 'silence_' in l), encoding='utf-8')
    return sorted(p.name for p in out.iterdir())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['status', 'set', 'prepare', 'gate']); ap.add_argument('project')
    ap.add_argument('--item'); ap.add_argument('--status'); ap.add_argument('--note', default=''); ap.add_argument('--by', default='')
    ap.add_argument('--video'); ap.add_argument('--stages', default='review,publish'); a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    folder = ROOT / a.project
    if a.cmd == 'status':
        for it in view(folder)['items']:
            print(f"{it['stage']:<10} {it['status']:<7} {it['id']:<24} {it['note'][:60]}")
    elif a.cmd == 'set':
        set_check(folder, a.item, a.status, a.note, a.by); print('ok', a.item, a.status)
    elif a.cmd == 'prepare':
        print('\n'.join(prepare(folder, a.video)))
    else:
        left = gate(folder, tuple(a.stages.split(',')))
        for it in left:
            print('미통과', it['stage'], it['id'], it['status'], it['note'][:60])
        sys.exit(1 if left else 0)


if __name__ == '__main__':
    main()
