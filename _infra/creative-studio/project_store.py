"""Portable project contract and Codex CLI. No generation or paid API calls."""
from pathlib import Path
import argparse, json, re, uuid

SCHEMA = 1

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))

def save(path, data):
    tmp=path.with_name('.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def validate(folder, data):
    errors=[];seen=set()
    if data.get('schema_version')!=SCHEMA:errors.append('schema_version must be 1')
    if not isinstance(data.get('title'),str) or not data['title'].strip():errors.append('title is required')
    cuts=data.get('cuts')
    if not isinstance(cuts,list):return errors+['cuts must be an array']
    def path(value,where):
        if value is None:return
        if not isinstance(value,str) or not value or '\\' in value or ':' in value or Path(value).is_absolute():
            errors.append(where+': use a project-relative forward-slash path');return
        p=(folder/value).resolve()
        if not p.is_relative_to(folder.resolve()):errors.append(where+': path escapes project')
        elif not p.is_file():errors.append(where+': file does not exist: '+value)
    for i,c in enumerate(cuts):
        if not isinstance(c,dict):errors.append(f'cuts[{i}] must be object');continue
        cid=c.get('id')
        if not isinstance(cid,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',cid):errors.append(f'cuts[{i}]: invalid id')
        elif cid in seen:errors.append('duplicate cut id: '+cid)
        else:seen.add(cid)
        if not isinstance(c.get('name'),str):errors.append(f'cuts[{i}]: name required')
        if c.get('status') not in ('planned','ready','generating','review','approved','rejected'):errors.append(f'cuts[{i}]: invalid status')
        for k in ('video','input_image','end_image','request_file','planned_start_image','planned_end_image'):path(c.get(k),f'cuts[{i}].{k}')
        for k in ('duration','start'):
            if c.get(k) is not None and (not isinstance(c[k],(int,float)) or isinstance(c[k],bool) or c[k]<0):errors.append(f'cuts[{i}].{k}: nonnegative number required')
    path(data.get('full_video'),'full_video')
    path(data.get('script_file'),'script_file')
    return errors

def create(root,slug,title):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',slug):raise ValueError('작품 ID는 영문 소문자·숫자·하이픈, 최대64자입니다.')
    folder=root/'productions/video'/slug
    if not folder.resolve().is_relative_to(root.resolve()):raise ValueError('작품 경로가 저장소 밖입니다.')
    folder.mkdir(parents=True,exist_ok=False)
    for n in ('references/characters','references/locations','shots','assets','exports','.studio'):(folder/n).mkdir(parents=True)
    files={
      'AGENTS.md':'# 작품 작업 지침\n\n상위 `productions/AGENTS.md`와 저장소 `docs/studio/project-contract.md`를 먼저 읽는다. 이 작품의 이야기는 BRIEF.md, 현재 진행은 생성상태.md, 결과 판정은 renders.md가 소유한다. 웹 연결 기록은 project.json이다.\n',
      'BRIEF.md':f'# {title}\n\n## 목표\n미정. 사용자와 확정 후 기록한다.\n\n## 등장인물·세계관\n미정.\n\n## 승인 범위\n유료 생성·외부 업로드 승인 없음.\n',
      '생성상태.md':'# 생성상태\n\n기획 시작 전. 생성 작업 없음. 다음 단계: 사용자와 BRIEF 확정 및 컷 계획 수립.\n',
      'renders.md':'# 결과 기록\n\n생성 결과 없음. 완료·비용은 실제 도구 결과로 확인 후 기록한다.\n',
      'shooting-script.md':'# 촬영 대본\n\n컷 ID / 대사 / 길이 / 카메라 / 인물 동선 / 시작·종료 상태를 기록한다.\n\n| 컷 | 목표 | 대사·말투 | 시간 안의 사건 | 카메라·소리·끝 연결 |\n|---|---|---|---|---|\n'}
    for name,content in files.items():(folder/name).write_text(content,encoding='utf-8')
    for name in ('characters.json','feedback.json'):
        save(folder/name,{'schema_version':1,'revision':0,'items':[]})
    save(folder/'project.json',{'schema_version':1,'id':slug,'title':title,'kind':'video','script_file':'shooting-script.md','cuts':[],'full_video':None})
    return folder

def upsert_cut(folder,patch):
    """Conversation-to-site handoff: merge one cut; never write user .studio state."""
    if not isinstance(patch,dict) or not patch.get('id'):raise ValueError('컷 ID가 필요합니다.')
    data=read(folder/'project.json')
    existing=next((c for c in data['cuts'] if c['id']==patch['id']),None)
    if existing is None:
        existing=dict(id=patch['id'],name=patch.get('name',patch['id']),status='planned',video=None,input_image=None,end_image=None,request_file=None,duration=None,start=None)
        data['cuts'].append(existing)
    existing.update(patch)
    errors=validate(folder,data)
    if errors:raise ValueError('\n'.join(errors))
    save(folder/'project.json',data);return existing

def adopt(folder):
    """One-time legacy adapter. Existing media is referenced, never renamed."""
    if (folder/'project.json').exists():raise ValueError('project.json already exists; refusing overwrite')
    report=folder/'shots/full-pass-h3-v1/assembly-report.json'
    manifest=folder/'shots/full-pass-h3-v1/manifest.json'
    r=read(report) if report.exists() else {}
    m=read(manifest) if manifest.exists() else {}
    jobs={x['id']:x for x in m.get('shots',[])}
    rows=r.get('timeline') or [{'id':f.parent.name,'name':f.parent.name,'local_path':f.relative_to(folder).as_posix()} for f in sorted((folder/'shots').glob('**/result.mp4'))]
    cuts=[]
    for row in rows:
        video=row['local_path'].replace('\\','/'); cid=row['id'];d=(folder/video).parent
        req=folder/'shots/full-pass-h3-v1'/f'{cid}-request.json';end=d/'actual-end.png'
        cuts.append({'id':cid,'name':row['name'],'status':'review','video':video,'input_image':None,
          'end_image':end.relative_to(folder).as_posix() if end.exists() else None,
          'request_file':req.relative_to(folder).as_posix() if req.exists() else None,
          'duration':row.get('duration'),'start':row.get('start'),'job_id':jobs.get(cid,{}).get('job_id'),'cost':jobs.get(cid,{}).get('cost')})
    full=folder/'assets/hwarim-full-rough-v1.mp4'
    data={'schema_version':1,'id':folder.name,'title':folder.name,'kind':'video','cuts':cuts,'full_video':full.relative_to(folder).as_posix() if full.exists() else None,'total_seconds':r.get('total_seconds'),'budget':m.get('budget',{})}
    errors=validate(folder,data)
    if errors:raise ValueError('\n'.join(errors))
    save(folder/'project.json',data)
    return data

def main():
    p=argparse.ArgumentParser(description='Creative Studio project workspace CLI')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('create');c.add_argument('slug');c.add_argument('--title',required=True)
    v=sub.add_parser('validate');v.add_argument('project',type=Path)
    a=sub.add_parser('adopt');a.add_argument('project',type=Path)
    u=sub.add_parser('upsert-cut');u.add_argument('project',type=Path);u.add_argument('--file',type=Path,required=True)
    args=p.parse_args()
    if args.command=='create':print(create(args.root.resolve(),args.slug,args.title))
    elif args.command=='adopt':adopt(args.project.resolve());print('Imported existing project records')
    elif args.command=='upsert-cut':upsert_cut(args.project.resolve(),read(args.file));print('Cut registered; the Studio discovers it automatically')
    else:
        folder=args.project.resolve();errors=validate(folder,read(folder/'project.json'))
        if errors:print('\n'.join(errors));raise SystemExit(1)
        print('OK: project.json paths, cut IDs and states')

if __name__=='__main__':main()
