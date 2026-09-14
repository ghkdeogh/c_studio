"""Local-only production browser. Originals are read-only; edits live in .studio."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import argparse, json, mimetypes, secrets, threading, uuid, base64, re, hashlib, os
from project_store import validate
from story_view import load_story
import media_engine
import production_assets
import youtube_analytics
import youtube_auth
import html

HERE = Path(__file__).resolve().parent
LOCK = threading.RLock()
TOKEN = secrets.token_urlsafe(32)
ROOT = HERE.parents[1]
IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}

def read_json(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8-sig'))

def within(root, relative):
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()): raise ValueError('연결 폴더 밖의 파일은 열 수 없습니다.')
    return p

def projects():
    candidates = [ROOT] if (ROOT / 'BRIEF.md').is_file() else [p.parent for p in (ROOT / 'productions').glob('*/*/BRIEF.md')]
    return [{'id': str(p.relative_to(ROOT)).replace('\\','/'), 'name': read_json(p / 'project.json', {}).get('title', p.name)} for p in sorted(candidates) if p.resolve().is_relative_to(ROOT.resolve())]

def project(pid):
    if pid not in {x['id'] for x in projects()}: raise ValueError('작품을 다시 선택해 주세요.')
    return within(ROOT, pid)

def url(pid, path):
    f=within(within(ROOT,pid),str(path));version=str(f.stat().st_mtime_ns) if f.is_file() else '0'
    return '/media?project=' + quote(pid, safe='') + '&path=' + quote(str(path).replace('\\','/'), safe='')+'&v='+version

def state(p): return read_json(within(p, '.studio/state.json'), {'schema': 1, 'cuts': {}})

def save_state(p, data):
    d = p / '.studio'; d.mkdir(exist_ok=True)
    # Resolve after mkdir to reject a substituted .studio junction.
    within(p, '.studio/state.json')
    tmp = d / (uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(d / 'state.json')

def catalog(pid):
    p = project(pid)
    contract = read_json(p / 'project.json', {})
    if contract:
        errors = validate(p, contract)
        if errors: raise ValueError('project.json 확인 필요: ' + '; '.join(errors[:5]))
    report = read_json(p / 'shots/full-pass-h3-v1/assembly-report.json', {})
    rows = report.get('timeline', [])
    if contract:
        rows = [dict(c, local_path=c.get('video')) for c in contract['cuts']]
    elif not rows:
        rows = [{'id': x.parent.name, 'name': x.parent.name, 'local_path': str(x.relative_to(p)), 'duration': None, 'start': None} for x in sorted((p/'shots').glob('**/result.mp4'))]
    story = load_story(p,contract)
    st = state(p); cuts = []
    manifest = read_json(p / 'shots/full-pass-h3-v1/manifest.json', {})
    jobs = {s['id']: s for s in manifest.get('shots', [])}
    for row in rows:
        video = within(p, row['local_path']) if row.get('local_path') else None; cid = row['id']; entry = st['cuts'].get(cid, {})
        req = p / 'shots/full-pass-h3-v1' / (cid + '-request.json')
        if contract: req = within(p,row['request_file']) if row.get('request_file') else None
        request = read_json(req, {}) if req and req.is_file() else {}
        versions = entry.get('versions', [])
        selected = entry.get('selected')
        versions = [dict(v, url=url(pid,v['path'])) for v in versions]
        end = video.parent / 'actual-end.png' if video else None
        if contract: end = within(p,row['end_image']) if row.get('end_image') else None
        original_image = url(pid,row['input_image']) if row.get('input_image') else None
        planned_start=url(pid,row['planned_start_image']) if row.get('planned_start_image') else None
        planned_end=url(pid,row['planned_end_image']) if row.get('planned_end_image') else None
        cuts.append({'id':cid, 'name':row['name'], 'duration':row.get('duration'), 'start':row.get('start'),
                     'video':url(pid,row['local_path']) if video and video.is_file() else None, 'status':row.get('status','review'), 'original_image':original_image,
                     'end':url(pid,end.relative_to(p)) if end and end.is_file() else None,
                     'prompt':request.get('params',request).get('prompt',''), 'model':request.get('params',request).get('model',''), 'cost':row.get('cost',jobs.get(cid,{}).get('cost')),
                     'story':[dict(story['rows'][i],id=i) for i in row.get('script_ids',[cid]) if i in story['rows']],
                     'versions':versions,'selected':selected,'note':entry.get('note',''),
                     'planned_start':planned_start,'planned_end':planned_end,
                     'trim':entry.get('trim'),'trim_revision':entry.get('trim_revision',0),
                     'trim_stale':bool(entry.get('trim') and video and entry.get('trim_source_stamp')!=[video.stat().st_size,video.stat().st_mtime_ns]),
                     'source_path':row.get('local_path'),
                     'image':next((v['url'] for v in versions if v['id']==selected),planned_start or original_image)})
    library=[]
    for x in sorted(x for base in ('shots','references','assets/storyboard') for x in (p/base).glob('**/*')):
        if x.suffix.lower() in IMAGES and x.is_file() and x.resolve().is_relative_to(p.resolve()):
            rel=str(x.relative_to(p)).replace('\\','/')
            library.append({'path':rel,'url':url(pid,rel),'name':x.name})
    full=p/'assets/hwarim-full-rough-v1.mp4'
    if contract: full = within(p,contract['full_video']) if contract.get('full_video') else None
    jobs=[]
    for job in media_engine.history(p):
        jobs.append({**{k:v for k,v in job.items() if k not in ('sources','processing')},'outputs':{mode:dict(output,url=url(pid,output['path'])) for mode,output in job.get('outputs',{}).items()}})
    result={'name':contract.get('title',p.name),'format':'project.json' if contract else 'legacy','story':story,'cuts':cuts,'library':library,'full':url(pid,full.relative_to(p)) if full and full.exists() else None,
            'timeline':st.get('timeline'),'timeline_revision':st.get('timeline_revision',0),'jobs':jobs,
            'full_path':full.relative_to(p).as_posix() if full and full.is_file() else None,
            'seconds':contract.get('total_seconds',report.get('total_seconds')), 'budget':contract.get('budget',manifest.get('budget',{})),
            'docs':[{'name':n,'url':url(pid,n)} for n in ['BRIEF.md','생성상태.md','renders.md'] if (p/n).is_file()]}
    characters=production_assets.load(p,'characters')
    result['characters']={**characters,'items':[{**c,'images':[{**im,'url':url(pid,im['path'])} for im in c.get('images',[])]} for c in characters['items']]}
    result['feedback']=production_assets.load(p,'feedback')
    result['youtube']=youtube_analytics.public(p)
    for publication in result['youtube']['links'] + result['youtube']['discovered']:
        publication['source_url']=url(pid,publication['source']) if publication.get('source') else None
    for snapshot in result['youtube']['snapshots']:
        source=snapshot.get('source_file')
        source_file=within(p,source) if source else None
        unchanged=bool(source_file and source_file.is_file() and snapshot.get('source_stamp')==[source_file.stat().st_size,source_file.stat().st_mtime_ns])
        snapshot['source_file_url']=url(pid,source) if unchanged else None
        snapshot['source_warning']='등록한 원본이 없거나 변경되었습니다. 구간과 영상을 연결하기 전에 원본을 확인해 주세요.' if source and not unchanged else ''
    result['youtube_connection']=youtube_auth.status()
    result['lessons']=production_assets.reusable([(r['id'],r['name'],project(r['id'])) for r in projects()])
    guide=HERE.parents[1]/'library/prompts/scene-planning.md'
    result['prompt_guide']=guide.read_text(encoding='utf-8-sig') if guide.is_file() else ''
    result['revision']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result

def source_file(pid,cid):
    p=project(pid);c=next((c for c in catalog(pid)['cuts'] if c['id']==cid),None)
    if not c or not c['video']:raise ValueError('생성된 영상이 없는 컷입니다.')
    return p,c,within(p,c['source_path'])

def save_trim(data):
    p,c,f=source_file(data['project'],data['cut']);info=media_engine.probe(f)
    a,b=media_engine.valid_trim(info,data)
    st=state(p);entry=st['cuts'].setdefault(c['id'],{})
    if data.get('revision')!=entry.get('trim_revision',0):raise ValueError('다른 창에서 구간이 변경되었습니다. 컷을 다시 열어 확인해 주세요.')
    entry['trim']={k:data[k] for k in ('source_sha256','in_frame','out_frame')}
    entry['trim_source_stamp']=[f.stat().st_size,f.stat().st_mtime_ns]
    entry['trim_revision']=entry.get('trim_revision',0)+1
    save_state(p,st);return {'ok':True,'revision':entry['trim_revision']}

def save_timeline(data):
    p=project(data['project']);st=state(p);ids=data.get('cuts')
    available={c['id'] for c in catalog(data['project'])['cuts'] if c['video']}
    if not isinstance(ids,list) or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)) or not set(ids)<=available:raise ValueError('생성된 컷을 중복 없이 선택해 주세요.')
    if data.get('revision')!=st.get('timeline_revision',0):raise ValueError('다른 창에서 편집 순서가 변경되었습니다. 새로고침해 주세요.')
    st['timeline']=ids;st['timeline_revision']=st.get('timeline_revision',0)+1
    save_state(p,st);return {'ok':True}

def export_project(data):
    p=project(data['project']);st=state(p);catalogue=catalog(data['project']);ids=st.get('timeline')
    if not ids:raise ValueError('편집 목록에서 포함할 컷과 순서를 저장해 주세요.')
    rows={c['id']:c for c in catalogue['cuts']};sources=[]
    for cid in ids:
        c=rows.get(cid)
        if not c or not c['video']:raise ValueError('편집 목록의 원본이 사라졌습니다. 목록을 다시 확인해 주세요.')
        sources.append(dict(cut=cid,source=c['source_path'],trim=st['cuts'].get(cid,{}).get('trim')))
    job=media_engine.start_export(p,sources)
    return {'ok':True,'id':job['id']}

def mutate(data):
    p=project(data['project']); cid=data['cut']
    if cid not in {x['id'] for x in catalog(data['project'])['cuts']}: raise ValueError('없는 컷입니다.')
    within(p,'.studio')
    st=state(p); entry=st['cuts'].setdefault(cid, {'versions':[], 'selected':None, 'note':''})
    action=data['action']
    if 'note' in data: entry['note']=str(data['note'])[:20000]
    if action=='note': entry['note']=str(data.get('note',''))[:20000]
    elif action=='select':
        selected=data.get('version')
        if selected is not None and selected not in {v['id'] for v in entry.get('versions',[])}: raise ValueError('없는 이미지 버전입니다.')
        entry['selected']=selected
    elif action in ('upload','existing'):
        vid=uuid.uuid4().hex
        if action=='existing':
            f=within(p,data['path'])
            if f.suffix.lower() not in IMAGES or not f.is_file(): raise ValueError('이미지 파일을 선택해 주세요.')
            rel=str(f.relative_to(p)).replace('\\','/'); name=f.name
        else:
            name=Path(data['name']).name; ext=Path(name).suffix.lower()
            if ext not in IMAGES: raise ValueError('PNG, JPG, WEBP 파일만 지원합니다.')
            raw=base64.b64decode(data['bytes'],validate=True)
            if len(raw)>20*1024*1024: raise ValueError('이미지는 20MB 이하로 선택해 주세요.')
            valid=(ext=='.png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (ext in ('.jpg','.jpeg') and raw.startswith(b'\xff\xd8\xff')) or (ext=='.webp' and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP')
            if not valid: raise ValueError('확장자와 이미지 형식이 맞지 않습니다.')
            rel=f'.studio/images/{vid}{ext}'; f=within(p,rel);f.parent.mkdir(parents=True,exist_ok=True); f.write_bytes(raw)
        entry.setdefault('versions',[]).append({'id':vid,'path':rel,'name':name}); entry['selected']=vid
    else: raise ValueError('지원하지 않는 변경입니다.')
    save_state(p,st)
    return {'ok':True}

def open_output_folder(data):
    p=project(data['project'])
    relative=data['path']
    contract=read_json(p/'project.json',{})
    allowed={contract.get('full_video')}
    for job in media_engine.history(p):
        allowed.update(o.get('path') for o in job.get('outputs',{}).values())
    if not isinstance(relative,str) or relative not in allowed:
        raise ValueError('등록된 출력 영상만 열 수 있습니다.')
    target=within(p,relative)
    if not target.is_file() or target.suffix.lower()!='.mp4':
        raise ValueError('출력 영상 파일을 찾을 수 없습니다.')
    if os.name!='nt':raise ValueError('폴더 열기는 Windows 제작실에서 지원합니다.')
    os.startfile(str(target.parent))
    return {'ok':True}

class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try: super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
    def log_message(self, *args): pass
    def json(self, data, status=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def trusted(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.trusted(): return self.json({'error':'Invalid host'},403)
        q=urlparse(self.path); params=parse_qs(q.query)
        try:
            if q.path=='/api/youtube/oauth/callback':
                try:
                    youtube_auth.finish(params,self.server.server_port)
                    notice='YouTube 연결이 완료되었습니다. 제작실로 돌아가 성과 가져오기를 눌러 주세요.'
                except (ValueError,OSError):
                    notice='YouTube 연결을 완료하지 못했습니다. 요청 만료·취소 또는 권한 설정을 확인하고 제작실에서 다시 연결해 주세요.'
                raw=('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>YouTube 연결</title><h1>'+html.escape(notice)+'</h1><p><a href="/?view=feedback">제작실로 돌아가기</a></p></html>').encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'none'; base-uri 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(raw);return
            if q.path=='/api/youtube/status':return self.json(youtube_auth.status())
            if q.path=='/api/bootstrap': return self.json({'root':str(ROOT),'projects':projects(),'token':TOKEN})
            if q.path=='/api/project':
                with LOCK: result=catalog(params['id'][0])
                return self.json(result)
            if q.path in ('/api/frames','/api/frame-image'):
                p=project(params['project'][0]);f=within(p,params['path'][0])
                if f.suffix.lower()!='.mp4':raise ValueError('MP4 영상을 선택해 주세요.')
                if q.path=='/api/frames':return self.json(media_engine.probe(f))
                return self.file(media_engine.thumbnail(p,f,int(params['frame'][0])))
            if q.path=='/media':
                with LOCK: f=within(project(params['project'][0]),params['path'][0])
                if f.suffix.lower() not in IMAGES|{'.mp4','.md','.mp3','.wav','.json'}: raise ValueError('지원하지 않는 파일 형식입니다.')
                return self.file(f)
            if q.path in ('/','/app.js','/story.js','/review.js','/youtube.js','/style.css'): return self.file(HERE/'web'/('index.html' if q.path=='/' else q.path[1:]))
            self.json({'error':'Not found'},404)
        except (ValueError,KeyError,OSError) as e: self.json({'error':str(e)},400)
    def do_POST(self):
        global ROOT
        if not self.trusted() or self.headers.get('X-Studio-Token')!=TOKEN: return self.json({'error':'새로고침 후 다시 시도해 주세요.'},403)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>29*1024*1024: raise ValueError('파일이 너무 큽니다.')
            data=json.loads(self.rfile.read(n))
            if self.path=='/api/youtube/sync':
                with LOCK:
                    folder=project(data['project']);youtube_analytics.check_revision(youtube_analytics.load(folder),data.get('revision'))
                snapshot=youtube_analytics.collect(folder,data['video_id'],data['start_date'],data['end_date'])
                with LOCK:result=youtube_analytics.add_snapshot(folder,snapshot,data.get('revision'),api=True)
                return self.json(result)
            with LOCK:
                if self.path=='/api/connect':
                    target=Path(data['path']).expanduser().resolve()
                    if not target.is_dir() or not ((target/'productions').is_dir() or (target/'BRIEF.md').is_file()): raise ValueError('productions 폴더 또는 BRIEF.md가 있는 폴더를 지정해 주세요.')
                    ROOT=target; result={'ok':True}
                elif self.path=='/api/edit':result=mutate(data)
                elif self.path=='/api/trim':result=save_trim(data)
                elif self.path=='/api/timeline':result=save_timeline(data)
                elif self.path=='/api/export':result=export_project(data)
                elif self.path=='/api/open-output-folder':result=open_output_folder(data)
                elif self.path=='/api/youtube/configure':result=youtube_auth.configure(data.get('document'))
                elif self.path=='/api/youtube/oauth/start':result=youtube_auth.start(self.server.server_port)
                elif self.path=='/api/youtube/link':result=youtube_analytics.link(project(data['project']),data['item'],data.get('revision'))
                elif self.path=='/api/youtube/snapshot':result=youtube_analytics.add_snapshot(project(data['project']),data['item'],data.get('revision'))
                elif self.path=='/api/youtube/draft':result=youtube_analytics.draft(project(data['project']),data['video_id'],data['snapshot_id'])
                elif self.path in ('/api/characters','/api/feedback'):
                    kind=self.path.rsplit('/',1)[1];folder=project(data['project'])
                    if kind=='characters' and data.get('action')=='upload':
                        result=production_assets.upload_character(folder,data)
                    else:
                        if 'revision' not in data:raise ValueError('다시 열어 최신 기록을 불러와 주세요.')
                        result=production_assets.upsert(folder,kind,data['item'],data['revision'])
                else: return self.json({'error':'Not found'},404)
            self.json(result)
        except (ValueError,KeyError,OSError) as e:self.json({'error':str(e)},400)
    def file(self,p):
        if not p.is_file(): return self.json({'error':'파일을 찾을 수 없습니다.'},404)
        size=p.stat().st_size;start=0;end=size-1;code=200
        header=self.headers.get('Range')
        if header:
            m=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
            if not m or not any(m.groups()): return self.json({'error':'Invalid range'},416)
            a,b=m.groups();start=int(a) if a else max(0,size-int(b));end=min(int(b),size-1) if a and b else size-1
            if start>end or start>=size:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
            code=206
        self.send_response(code);self.send_header('Content-Type',mimetypes.guess_type(p)[0] or 'application/octet-stream');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1));self.send_header('Cache-Control','no-cache')
        if code==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with p.open('rb') as f:
                f.seek(start);left=end-start+1
                while left:
                    chunk=f.read(min(256*1024,left))
                    if not chunk:break
                    self.wfile.write(chunk);left-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default=str(ROOT));parser.add_argument('--port',type=int,default=8765);args=parser.parse_args();ROOT=Path(args.root).resolve()
    http=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Creative Studio: http://127.0.0.1:{http.server_port}',flush=True)
    http.serve_forever()
