/* Extends the existing production notebook; no third-party scripts or remote media. */
(() => {
  const box = document.createElement('section');
  box.id = 'youtube-panel';
  box.setAttribute('aria-label', '유튜브 성과와 회고');
  document.querySelector('.feedback-tools').before(box);
  let currentProject = '', selectedVideo = '', selectedSnapshot = '', dialogContext = null, busy = false, dirty = false;
  const priorDirty = window.assetsDirty;
  window.assetsDirty = () => priorDirty() || dirty || busy;
  const sourceName = source => source === 'youtube_api' ? 'YouTube API' : 'Studio 화면 기록';
  const fmt = value => value == null ? '—' : Number(value).toLocaleString('ko-KR', {maximumFractionDigits: 2});
  const stamp = value => value ? new Date(value).toLocaleString('ko-KR') : '';
  const confidenceNames = {hypothesis:'검증 전 가설', supported:'비교 근거 있음', inconclusive:'판단 보류'};
  const content = id => document.getElementById(id);
  const selected = () => {
    const yt = data?.youtube;
    return {yt, link: yt?.links.find(r=>r.video_id===selectedVideo),
      snapshot: yt?.snapshots.find(r=>r.id===selectedSnapshot)};
  };

  const dialog = document.createElement('dialog');
  dialog.id = 'youtube-dialog';
  dialog.setAttribute('aria-labelledby', 'youtube-dialog-title');
  dialog.innerHTML = '<div class="dialog-head"><h2 id="youtube-dialog-title"></h2><button id="youtube-close" type="button">닫기 ✕</button></div><form id="youtube-form" class="workspace-form"><div id="youtube-fields"></div><p id="youtube-form-status" role="status"></p><button type="submit" class="primary" id="youtube-submit">저장</button></form>';
  document.body.append(dialog);
  function close(){if(busy)return;if(dirty&&!confirm('입력한 내용을 저장하지 않고 닫을까요?'))return;dialog.close();}
  content('youtube-close').onclick=close;
  dialog.addEventListener('cancel', e=>{e.preventDefault();close();});
  dialog.addEventListener('close',()=>{dirty=false;dialogContext=null;content('youtube-fields').replaceChildren();});
  content('youtube-form').oninput=()=>dirty=true;
  function open(mode, title, fields, extra={}) {
    dialogContext={mode, project:pid, revision:data.youtube.revision, video_id:selectedVideo, ...extra};
    content('youtube-dialog-title').textContent=title;
    content('youtube-fields').innerHTML=fields;
    content('youtube-form-status').textContent='';
    content('youtube-submit').textContent=mode==='sync'?'성과 가져오기':mode==='config'?'설정 저장':'저장';
    dirty=false;dialog.showModal();
  }
  function field(label,name,value='',type='text',attrs='') {
    return `<label>${esc(label)}<input type="${type}" name="${name}" value="${esc(value)}" ${attrs}></label>`;
  }
  function periodFields(link){
    // Explicit calendar dates; API uses Pacific Time, manual entries use the Studio selector.
    const end=new Date().toISOString().slice(0,10);
    return `<div class="form-pair">${field('시작일','start_date',link?.published_date||end,'date','required')}${field('종료일','end_date',end,'date','required')}</div>`;
  }
  function linkDialog(row={}) {
    open('link','작품에 유튜브 영상 연결',
      `<p class="hint">이 작품의 업로드 영상과 실제 업로드한 원본을 연결합니다.</p>${field('영상 주소 또는 ID','video_id',row.video_id||'','text','required')}${field('영상 제목','title',row.title||data.name)}<div class="form-pair">${field('게시일','published_date',row.published_date||'','date')}${field('채널 ID · 선택','channel_id',row.channel_id||'')}</div>${field('업로드한 원본 경로 · 작품 내부 MP4, 선택','source',row.source||'')}<p class="hint">예: exports/editorial-v004/edited.mp4</p>`, {publication_file:row.publication_file||''});
  }
  function manualDialog(){
    const {link,yt}=selected();
    open('manual','Studio 화면 지표 기록',
      `<p class="hint">화면에서 확인한 값만 입력하세요. 미집계 항목은 비워 두며 0과 구분해 저장합니다. 같은 선택 기간의 값만 묶으세요.</p>${periodFields(link)}${field('화면 확인 시각','as_of',new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16),'datetime-local','required')}<div class="yt-input-grid">${Object.entries(yt.metric_definitions).map(([key,[label,unit]])=>field(`${label} (${unit})`,key,'','number',`step="${['views','engagedViews','subscribersGained','subscribersLost','subscribersNet','likes','comments','shares'].includes(key)?'1':'any'}" ${key==='subscribersNet'?'':'min="0"'} ${['stayedToWatch','swipedAway'].includes(key)?'max="100"':''}`)).join('')}</div><label>화면·집계 상태 메모<textarea name="note" rows="3" placeholder="예: 게시 이후 / 시청 유지 그래프 처리 중"></textarea></label>`);
  }
  function syncDialog(){
    open('sync','YouTube API 성과 가져오기',`<p class="hint">연결한 채널이 소유한 영상만 조회합니다. 날짜는 YouTube API의 Pacific Time 기준이며 최근 날짜는 집계가 덜 되었을 수 있습니다.</p>${periodFields(selected().link)}<p class="hint">기본 성과·유입 경로·일별 성과·구간별 유지율을 조회합니다. 지금은 버튼을 누를 때만 가져옵니다.</p>`);
  }
  function configDialog(){
    open('config','Google 연결 설정',`<ol class="yt-setup"><li>Google Cloud 프로젝트에서 <b>YouTube Data API v3</b>와 <b>YouTube Analytics API</b>를 사용 설정합니다.</li><li>Google Auth Platform에서 동의 화면을 설정하고, 테스트 중이면 본인 계정을 테스트 사용자에 추가합니다.</li><li>클라이언트 유형을 <b>데스크톱 앱</b>으로 만들고 받은 JSON을 아래에서 선택합니다.</li><li>저장한 뒤 ‘Google 계정 연결’을 누릅니다. 기본 브라우저에서 읽기 권한을 승인합니다.</li></ol><p><a href="https://console.cloud.google.com/apis/dashboard" target="_blank" rel="noopener noreferrer">Google Cloud 열기 ↗</a></p><label>데스크톱 앱 OAuth JSON<input type="file" id="youtube-client-file" accept="application/json,.json"></label><details><summary>파일 없이 직접 입력</summary><p class="hint">Google Cloud에서 만든 데스크톱 앱의 값만 입력하세요.</p><label>데스크톱 클라이언트 ID<input name="oauth_client_id" autocomplete="off" spellcheck="false"></label><label>클라이언트 보안 비밀번호<input type="password" name="oauth_client_secret" autocomplete="off" spellcheck="false"></label></details><p class="hint">JSON과 인증 토큰은 이 PC의 Windows 계정으로 암호화하여 작품 폴더 밖에 저장합니다. 다른 클라이언트로 바꾸면 다시 로그인해야 합니다.</p>`);
  }

  content('youtube-form').onsubmit=async e=>{
    e.preventDefault();if(busy)return;
    busy=true;content('youtube-submit').disabled=true;content('youtube-form-status').textContent=dialogContext.mode==='sync'?'Google에서 지표를 가져오는 중입니다…':'저장 중…';
    const ctx={...dialogContext}, values=Object.fromEntries(new FormData(e.target));
    try {
      let result;
      if(ctx.mode==='config'){
        const file=content('youtube-client-file').files[0];
        let document;
        if(file){
          if(values.oauth_client_id||values.oauth_client_secret)throw Error('JSON 파일과 직접 입력 중 한 가지 방법만 사용해 주세요.');
          if(file.size>32768)throw Error('32KB 이하의 OAuth JSON을 선택해 주세요.');
          try{document=JSON.parse(await file.text());}catch{throw Error('JSON 형식의 파일을 선택해 주세요.');}
        }else{
          if(!values.oauth_client_id?.trim()||!values.oauth_client_secret?.trim())throw Error('OAuth JSON을 선택하거나 데스크톱 클라이언트 ID와 보안 비밀번호를 입력해 주세요.');
          document={installed:{client_id:values.oauth_client_id.trim(),client_secret:values.oauth_client_secret.trim()}};
        }
        result=await api('/api/youtube/configure',{document});
      }else if(ctx.mode==='link'){
        result=await api('/api/youtube/link',{project:ctx.project,revision:ctx.revision,item:{...values,publication_file:ctx.publication_file}});
        selectedVideo=result.links.at(-1).video_id;
      }else if(ctx.mode==='sync'){
        result=await api('/api/youtube/sync',{project:ctx.project,revision:ctx.revision,video_id:ctx.video_id,...values});
        selectedSnapshot=result.snapshots.at(-1)?.id||'';
      }else{
        const metrics=Object.fromEntries(Object.keys(data.youtube.metric_definitions).map(k=>[k,values[k]===''?null:Number(values[k])]));
        result=await api('/api/youtube/snapshot',{project:ctx.project,revision:ctx.revision,item:{video_id:ctx.video_id,start_date:values.start_date,end_date:values.end_date,as_of:new Date(values.as_of).toISOString(),metrics,note:values.note}});
        selectedSnapshot=result.snapshots.at(-1)?.id||'';
      }
      dirty=false;dialog.close();await refresh(true);message(ctx.mode==='config'?'설정을 저장했습니다. Google 계정을 연결해 주세요.':'성과 기록을 저장했습니다. 기록에서 회고를 작성할 수 있습니다.');
    }catch(err){content('youtube-form-status').textContent=err.message;}finally{busy=false;content('youtube-submit').disabled=false;}
  };

  const retro=document.createElement('fieldset');retro.id='youtube-retrospective';retro.hidden=true;
  retro.innerHTML='<legend>성과 회고 · 관찰에서 다음 실험으로</legend><p class="hint">수치만으로 원인을 확정하지 마세요. 아래 초안은 규칙 기반 정리이며 영상을 AI가 시청한 결과가 아닙니다.</p><label>가설<textarea name="retro_hypothesis" rows="2" required></textarea></label><label>다음 작품에서 바꿀 한 가지<textarea name="retro_experiment" rows="2" required></textarea></label><label>비교 조건과 성공 판단 기준<textarea name="retro_success_measure" rows="2" required placeholder="예: 비슷한 길이의 쇼츠, 게시 7일 뒤 초반 유지율 비교"></textarea></label><div class="form-pair"><label>관련 장면 시각 (초, 선택)<input name="retro_scene_seconds" type="number" min="0" max="86400" step="0.001"></label><label>가설 검증 상태<select name="retro_confidence"><option value="hypothesis">검증 전 가설</option><option value="supported">비교 근거 있음</option><option value="inconclusive">판단 보류</option></select></label></div>';
  content('feedback-tags').before(retro);
  const originalOpen=openFeedback;
  openFeedback=function(id,initial={}){
    originalOpen(id,initial);
    const r=feedbackEdit.retrospective;
    retro.hidden=!r;retro.disabled=!r;
    for(const key of ['hypothesis','experiment','success_measure','scene_seconds','confidence']){
      content('feedback-form').elements['retro_'+key].value=r?.[key]??(key==='confidence'?'hypothesis':'');
    }
  };
  window.applyYoutubeRetrospective=item=>{
    if(item.retrospective){
      const r={...item.retrospective};
      for(const key of ['hypothesis','experiment','success_measure','confidence'])r[key]=item['retro_'+key];
      r.scene_seconds=item.retro_scene_seconds===''?null:Number(item.retro_scene_seconds);
      item.retrospective=r;
    }
    Object.keys(item).filter(k=>k.startsWith('retro_')).forEach(k=>delete item[k]);
    return item;
  };
  const originalCard=feedbackCard;
  feedbackCard=function(row,shared=false){
    let card=originalCard(row,shared),r=row.retrospective;
    if(!r)return card;
    const details=`<div class="yt-retro-copy"><span class="yt-badge">${esc(confidenceNames[r.confidence])}</span><p><b>가설</b> ${esc(r.hypothesis)}</p><p><b>다음 실험</b> ${esc(r.experiment)}</p><p><b>비교 기준</b> ${esc(r.success_measure)}</p>${r.scene_seconds!=null?`<p class="hint">관련 장면 · ${fmt(r.scene_seconds)}초</p>`:''}</div>`;
    return card.replace('<div class="note-footer">',details+'<div class="note-footer">');
  };

  function render(){
    if(!data?.youtube){box.innerHTML='<p class="hint">서버를 다시 시작하면 유튜브 성과 연결을 사용할 수 있습니다.</p>';return;}
    if(currentProject!==pid){currentProject=pid;selectedVideo='';selectedSnapshot='';}
    const yt=data.youtube, connection=data.youtube_connection||{};
    if(!yt.links.some(r=>r.video_id===selectedVideo))selectedVideo=yt.links[0]?.video_id||'';
    const snapshots=yt.snapshots.filter(s=>s.video_id===selectedVideo);
    if(!snapshots.some(s=>s.id===selectedSnapshot))selectedSnapshot=snapshots.at(-1)?.id||'';
    const {link,snapshot:s}=selected();
    box.innerHTML=`<div class="yt-heading"><div><p class="eyebrow">PUBLISH / LEARN / CREATE</p><h3>공개한 영상에서 다음 이야기로</h3><p class="hint">성과의 출처를 남기고, 다음 작품에서 시험할 한 가지를 찾습니다.</p></div><span class="yt-badge">${connection.connected?'채널 연결됨':'API 미연결'}</span></div><div class="yt-connect"><span>${connection.connected?esc(connection.channel?.title)+' · 읽기 전용':connection.configured?'연결 설정 준비됨 · Google 인증 필요':'계정 연결 전에도 Studio 화면 지표를 기록할 수 있어요.'}</span><div><button data-yt="config">연결 설정</button>${connection.configured?'<button data-yt="auth">'+(connection.connected?'Google 계정 다시 연결':'Google 계정 연결')+'</button>':''}</div></div>${connection.error?`<p class="warning">${esc(connection.error)}</p>`:''}<div class="yt-toolbar">${yt.links.length?`<label>연결 영상<select id="youtube-video">${yt.links.map(r=>`<option value="${esc(r.video_id)}" ${r.video_id===selectedVideo?'selected':''}>${esc(r.title)}</option>`).join('')}</select></label>`:'<b>이 작품에 영상을 연결해 주세요.</b>'}<button data-yt="link">영상 연결</button></div>${yt.discovered.map((r,i)=>`<div class="yt-discovery"><div><b>게시 기록 발견</b><p>${esc(r.title)}</p></div><button data-discovery="${i}">이 영상 연결</button></div>`).join('')}${link?`<div class="yt-actions"><a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">유튜브 영상 ↗</a><button data-yt="manual">Studio 지표 기록</button><button data-yt="sync" ${connection.connected?'':'disabled'}>API 성과 가져오기</button></div><p class="hint">${connection.connected?'필요할 때 가져오기 버튼을 누르세요. 자동 수집은 꺼져 있습니다.':'API 수집은 Google 계정 연결 후 사용할 수 있습니다.'}</p>`:''}${snapshots.length?`<label class="yt-history">성과 기록<select id="youtube-snapshot">${[...snapshots].reverse().map(x=>`<option value="${x.id}" ${x.id===selectedSnapshot?'selected':''}>${esc(sourceName(x.source))} · ${esc(x.start_date)}~${esc(x.end_date)} · 확인 ${esc(stamp(x.as_of))}</option>`).join('')}</select></label>`:link?'<div class="yt-empty">아직 성과 기록이 없습니다.<br><span>Studio 지표 기록 또는 API 성과 가져오기로 첫 기록을 남겨보세요.</span></div>':''}${s?snapshotHTML(s,yt):''}<p id="youtube-status" role="status"></p>`;
    box.querySelector('[data-yt="config"]').onclick=configDialog;
    box.querySelector('[data-yt="link"]').onclick=()=>linkDialog();
    box.querySelectorAll('[data-discovery]').forEach(b=>b.onclick=()=>linkDialog(yt.discovered[Number(b.dataset.discovery)]));
    const authButton=box.querySelector('[data-yt="auth"]');
    if(authButton)authButton.onclick=async()=>{if(busy)return;busy=true;authButton.disabled=true;try{const result=await api('/api/youtube/oauth/start',{});content('youtube-status').textContent=result.message;}catch(e){content('youtube-status').textContent=e.message;}finally{busy=false;authButton.disabled=false;}};
    if(content('youtube-video'))content('youtube-video').onchange=e=>{selectedVideo=e.target.value;selectedSnapshot='';render();};
    if(content('youtube-snapshot'))content('youtube-snapshot').onchange=e=>{selectedSnapshot=e.target.value;render();};
    if(link){box.querySelector('[data-yt="manual"]').onclick=manualDialog;box.querySelector('[data-yt="sync"]').onclick=syncDialog;}
    if(s){box.querySelector('[data-yt="draft"]').onclick=async()=>{
      const project=pid;
      try{const initial=await api('/api/youtube/draft',{project,video_id:selectedVideo,snapshot_id:s.id});if(pid!==project)return;openFeedback(null,initial);}catch(e){content('youtube-status').textContent=e.message;}
    };}
    if(s?.retention?.length&&s?.source_file_url){
      content('youtube-scene-jump').onchange=e=>{const video=content('youtube-source-video');if(Number.isFinite(video.duration))video.currentTime=Number(e.target.value)*video.duration;};
    }
  }
  function snapshotHTML(s,yt){
    const primary=['views','engagedViews','averageViewDuration','averageViewPercentage','stayedToWatch','subscribersNet'];
    let out=`<div class="yt-snapshot-head"><span class="yt-badge">${esc(sourceName(s.source))}</span><span>${esc(s.start_date)} ~ ${esc(s.end_date)}</span><button class="primary" data-yt="draft">이 기록으로 회고 작성</button></div><p class="hint">확인 ${esc(stamp(s.as_of))} · ${esc(s.period_basis)}${s.available_through?' · 일별 데이터 마지막 날짜 '+esc(s.available_through):''}</p><div class="yt-metrics">${primary.map(k=>`<div><span>${esc(yt.metric_definitions[k][0])}</span><strong>${fmt(s.metrics[k])}<small>${s.metrics[k]==null?'미집계/미기록':esc(yt.metric_definitions[k][1])}</small></strong></div>`).join('')}</div><p class="hint">유효 조회수는 초반 이후 계속 시청한 횟수입니다. 평균 조회율은 완주한 사람의 비율이 아닙니다. —는 0을 뜻하지 않습니다.</p><details><summary>나머지 지표 · 집계 메모</summary><div class="yt-detail-metrics">${Object.entries(yt.metric_definitions).filter(([k])=>!primary.includes(k)).map(([k,[label,unit]])=>`<p>${esc(label)} <b>${fmt(s.metrics[k])}${s.metrics[k]==null?'':esc(unit)}</b></p>`).join('')}</div><p>${esc(s.note)}</p>${s.warnings.map(w=>`<p class="hint">${esc(w)}</p>`).join('')}<a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">Studio에서 확인 ↗</a></details>`;
    if(s.source_warning)out+=`<p class="warning">${esc(s.source_warning)}</p>`;
    if(s.traffic?.length)out+=`<details><summary>유입 경로</summary><div class="yt-detail-metrics">${s.traffic.map(r=>`<p>${esc(({SHORTS:'Shorts 피드',YT_SEARCH:'YouTube 검색',YT_CHANNEL:'채널 페이지',EXT_URL:'외부 사이트',RELATED_VIDEO:'추천 영상',SUBSCRIBER:'탐색 기능'})[r.insightTrafficSourceType]||r.insightTrafficSourceType)} <b>${fmt(r.views)}회</b></p>`).join('')}</div></details>`;
    if(s.daily?.length)out+=`<details><summary>일별 성과 · ${s.daily.length}일</summary><div class="yt-table-scroll"><table><thead><tr><th>날짜</th><th>조회수</th><th>유효 조회수</th><th>평균 시청(초)</th></tr></thead><tbody>${s.daily.map(r=>`<tr><td>${esc(r.day)}</td><td>${fmt(r.views)}</td><td>${fmt(r.engagedViews)}</td><td>${fmt(r.averageViewDuration)}</td></tr>`).join('')}</tbody></table></div></details>`;
    const sourceURL=s.source_file_url;
    if(s.retention?.length){
      const pts=s.retention.filter(r=>Number.isFinite(Number(r.elapsedVideoTimeRatio))&&Number.isFinite(Number(r.audienceWatchRatio))), max=Math.max(1,...pts.map(r=>Number(r.audienceWatchRatio)));
      const points=pts.map(r=>`${20+Number(r.elapsedVideoTimeRatio)*560},${150-Number(r.audienceWatchRatio)/max*130}`).join(' ');
      out+=`<details open><summary>영상 구간과 시청 유지율</summary><p class="hint">가로: 영상 진행률 0~100% · 세로: 시청 유지 비율, 최대 ${fmt(max*100)}%. 반복 시청으로 100%를 넘을 수 있습니다.</p><svg class="yt-retention" viewBox="0 0 600 170" role="img" aria-label="영상 진행률별 시청 유지율. 아래 표에서 정확한 값을 확인할 수 있습니다."><path d="M20 15V150H580" fill="none" stroke="currentColor" opacity=".25"/><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg>${sourceURL?`<video id="youtube-source-video" controls preload="metadata" src="${esc(sourceURL)}"></video><label>등록한 업로드 원본에서 구간 찾기<select id="youtube-scene-jump">${pts.map(r=>`<option value="${Number(r.elapsedVideoTimeRatio)}">영상 ${fmt(Number(r.elapsedVideoTimeRatio)*100)}% 지점 · 유지율 ${fmt(Number(r.audienceWatchRatio)*100)}%</option>`).join('')}</select></label>`:''}<details><summary>유지율 수치 표</summary><div class="yt-table-scroll"><table><thead><tr><th>진행률</th><th>유지율</th></tr></thead><tbody>${pts.map(r=>`<tr><td>${fmt(Number(r.elapsedVideoTimeRatio)*100)}%</td><td>${fmt(Number(r.audienceWatchRatio)*100)}%</td></tr>`).join('')}</tbody></table></div></details></details>`;
    }else out+='<p class="yt-pending">구간별 유지율이 아직 없습니다. API 수집 후 데이터가 제공되면 원본 영상과 함께 확인할 수 있습니다.</p>';
    return out;
  }
  const previousRender=window.renderProductionAssets;
  window.renderProductionAssets=()=>{previousRender();render();};
  render();
})();
