"""Frame-indexed local review and asynchronous, non-destructive assembly."""
from pathlib import Path
import hashlib, json, subprocess, threading, uuid, time
from fractions import Fraction

CACHE = {}
CACHE_LOCK = threading.Lock()
JOBS_LOCK = threading.Lock()
ACTIVE = set()

def run(args, timeout=120):
    try:
        return subprocess.check_output(args, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError as e:
        raise ValueError('FFmpeg/ffprobe를 설치한 뒤 서버를 다시 실행해 주세요.') from e
    except subprocess.CalledProcessError as e:
        raise ValueError('미디어 처리 실패: '+e.stderr.decode('utf-8',errors='replace')[-1200:]) from e
    except subprocess.TimeoutExpired as e:
        raise ValueError('미디어 처리 시간이 초과되었습니다. 파일을 확인해 주세요.') from e

def probe(path):
    path=Path(path).resolve(); stat=path.stat(); key=(str(path),stat.st_size,stat.st_mtime_ns)
    with CACHE_LOCK:
        if key in CACHE:return CACHE[key]
    meta=json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
    video=next((s for s in meta['streams'] if s['codec_type']=='video'),None)
    if not video:raise ValueError('영상 스트림이 없습니다.')
    frames=json.loads(run(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time,pkt_duration_time,duration_time','-of','json',str(path)]))['frames']
    pts=[float(f['best_effort_timestamp_time']) for f in frames if 'best_effort_timestamp_time' in f]
    if not pts or any(a>=b for a,b in zip(pts,pts[1:])):raise ValueError('영상 프레임 시각을 읽을 수 없습니다.')
    fps=float(Fraction(video.get('avg_frame_rate') or '24/1'))
    if fps<=0:fps=24
    start=pts[0]
    duration=float(video.get('duration') or (pts[-1]-start+1/fps))
    end=max(start+duration,pts[-1]+float(frames[-1].get('duration_time') or frames[-1].get('pkt_duration_time') or 1/fps))
    result=dict(frames=pts,end=end,duration=end-start,start=start,fps=fps,
                count=len(pts),width=video['width'],height=video['height'],
                audio=any(s['codec_type']=='audio' for s in meta['streams']),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with CACHE_LOCK:CACHE[key]=result
    return result

def valid_trim(info, value):
    if not isinstance(value,dict) or value.get('source_sha256')!=info['sha256']:
        raise ValueError('영상 원본이 변경되었습니다. 새 원본에서 구간을 다시 확인해 주세요.')
    a,b=value.get('in_frame'),value.get('out_frame')
    if type(a) is not int or type(b) is not int or not 0<=a<b<=info['count']:
        raise ValueError('시작 프레임보다 뒤의 끝 프레임을 선택해 주세요. 끝점 프레임은 제외됩니다.')
    return a,b

def thumbnail(project,path,index):
    info=probe(path)
    if not 0<=index<info['count']:raise ValueError('프레임 범위를 벗어났습니다.')
    folder=(project/'.studio/cache/frames').resolve()
    if not folder.is_relative_to(project.resolve()):raise ValueError('캐시 경로가 작품 밖입니다.')
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{info["sha256"]}-{index}.jpg'
    if not target.exists():
        temp=folder/f'{uuid.uuid4().hex}.jpg'
        run(['ffmpeg','-v','error','-i',str(path),'-vf',f'select=eq(n\\,{index}),scale=640:-2','-frames:v','1','-q:v','3',str(temp)])
        temp.replace(target)
    return target

def save(path,data):
    tmp=path.with_name(uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Windows readers may briefly hold the destination without delete sharing.
    for attempt in range(25):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==24:raise
            time.sleep(.02)

def history(project):
    result=[]
    for path in sorted((project/'exports').glob('studio-*/job.json'),reverse=True):
        if not path.resolve().is_relative_to(project.resolve()):continue
        try:
            job=json.loads(path.read_text(encoding='utf-8'))
            if job['status'] in ('queued','running') and str(project.resolve()) not in ACTIVE:
                job=dict(job,status='error',error='서버가 종료되어 출력이 중단되었습니다. 다시 이어붙이기를 실행해 주세요.')
            result.append(job)
        except (OSError,ValueError,KeyError):continue
    return result[:30]

def start_export(project, sources):
    key=str(project.resolve())
    with JOBS_LOCK:
        if key in ACTIVE:raise ValueError('이 작품의 출력이 진행 중입니다.')
        if not sources:raise ValueError('이어 붙일 영상을 선택해 주세요.')
        if len(sources)>80:raise ValueError('한 번에 최대 80개 컷을 연결할 수 있습니다.')
        # Validate the whole frozen selection before creating any render output.
        frozen=[]
        for source in sources:
            path=(project/source['source']).resolve()
            if not path.is_relative_to(project.resolve()):raise ValueError('작품 밖 원본입니다.')
            info=probe(path);a,b=valid_trim(info,source['trim'])
            frozen.append(dict(source,info=info,in_frame=a,out_frame=b))
        jid='studio-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        folder=(project/'exports'/jid).resolve()
        if not folder.is_relative_to(project.resolve()):raise ValueError('출력 경로가 작품 밖입니다.')
        folder.mkdir(parents=True)
        job=dict(id=jid,status='queued',stage='준비',created_at=time.time(),sources=frozen,outputs={},
                 processing='Same sources/order. Frame-index trims, no speed/volume/music/effects. H264/AAC re-encoding; scale/pad/fps normalized to first source; audio bounded/padded to picture interval. Originals unchanged.')
        save(folder/'job.json',job);ACTIVE.add(key)
    threading.Thread(target=render_job,args=(project,folder,job),daemon=True).start()
    return job

def render_job(project,folder,job):
    try:
        job.update(status='running')
        first=job['sources'][0]['info'];w=first['width']//2*2;h=first['height']//2*2
        fps=Fraction(str(first['fps'])).limit_denominator(1001)
        for mode in ('raw','edited'):
            job['stage']='원본 연결 중' if mode=='raw' else '편집본 연결 중';save(folder/'job.json',job)
            args=['ffmpeg','-hide_banner','-v','error','-nostdin'];filters=[];pins=[];timeline=[];position=0
            for i,source in enumerate(job['sources']):
                path=(project/source['source']).resolve();info=probe(path)
                if info['sha256']!=source['info']['sha256']:raise ValueError('출력 중 원본이 변경되었습니다. 다시 검수해 주세요.')
                args+=['-i',str(path)]
                a,b=(0,info['count']) if mode=='raw' else (source['in_frame'],source['out_frame'])
                begin=info['frames'][a];end=info['frames'][b] if b<info['count'] else info['end'];length=end-begin
                filters.append(f'[{i}:v]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]')
                if info['audio']:
                    filters.append(f'[{i}:a]atrim=start={begin:.9f}:end={end:.9f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={length:.9f}[a{i}]')
                else:filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length:.9f}[a{i}]')
                pins.extend([f'[v{i}]',f'[a{i}]'])
                timeline.append(dict(cut=source['cut'],source=source['source'],source_sha256=info['sha256'],in_frame=a,out_frame=b,source_in=begin,source_out_exclusive=end,timeline_in=position,timeline_out=position+length));position+=length
            filters.append(''.join(pins)+f'concat=n={len(job["sources"])}:v=1:a=1[v][a]')
            target=folder/f'{mode}.mp4'
            args+=['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-video_track_timescale','24000','-movie_timescale','24000','-n',str(target)]
            run(args,timeout=1800)
            result=probe(target)
            run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],timeout=300)
            job['outputs'][mode]=dict(path=target.relative_to(project).as_posix(),duration=result['duration'],frames=result['count'],sha256=result['sha256'],timeline=timeline)
            save(folder/'job.json',job)
        job.update(status='complete',stage='출력 완료')
    except Exception as e:job.update(status='error',stage='출력 실패',error=str(e))
    finally:
        try:save(folder/'job.json',job)
        finally:
            with JOBS_LOCK:ACTIVE.discard(str(project.resolve()))
