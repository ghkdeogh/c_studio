/* Bounded recommendations and evidence-backed application history. */
(() => {
  const column = document.querySelector('.lesson-column');
  if (!column) return;
  column.querySelectorAll(':scope > h3, :scope > p.hint').forEach(el => el.remove());
  column.insertAdjacentHTML('afterbegin', `<div class="lesson-heading"><p class="eyebrow">LEARN · APPLY · REVIEW</p><h3>이번 작품에 가져올 경험</h3><p class="hint">관련된 원칙부터 6개씩 확인해요. 같은 내용은 묶고, 적용 조건이 다른 기록은 따로 비교해요.</p></div>
    <form id="lesson-filter" class="lesson-filter"><label>제작 단계<select name="stage"><option value="planning">기획 · 콘티</option><option value="generation">영상 생성</option><option value="review">결과 검수</option></select></label><label>이번 작업<input name="query" placeholder="예: 음식 소개, 카메라 이동" maxlength="2000"></label><label>생성 모델<input name="model" placeholder="필요할 때 입력" maxlength="160"></label><label>보기<select name="browse"><option value="0">추천 원칙</option><option value="1">조건 확인할 후보까지</option></select></label><button type="submit">후보 찾기</button></form>
    <p id="lesson-summary" role="status" class="hint"></p>`);
  $('#lesson-list').insertAdjacentHTML('afterend', `<div class="lesson-pages"><button id="lesson-prev">이전 후보</button><span id="lesson-page" class="hint"></span><button id="lesson-next">다음 후보</button></div><section class="lesson-plan"><h3>이번 작품의 적용과 검수</h3><p class="hint">계획·파일 반영·영상 검수를 구분해 기록해요. 현재 요청과 작품의 필수 조건은 별도로 유지됩니다.</p><div id="lesson-plan-list"></div><details><summary>최근 변경 · 되돌리기</summary><div id="lesson-history"></div></details></section>`);
  document.body.insertAdjacentHTML('beforeend', `<dialog id="lesson-dialog" aria-labelledby="lesson-dialog-title"><div class="dialog-head"><h2 id="lesson-dialog-title">경험 적용하기</h2><button id="lesson-close">닫기 ✕</button></div><p id="lesson-source-action" class="hint"></p><form id="lesson-form" class="workspace-form"><label>적용 단계<select name="stage"><option value="planned">적용 계획</option><option value="applied">대본 · 입력 파일 반영</option><option value="reviewed">영상 검수 완료</option><option value="skipped">이번 작품에서 제외</option></select></label><label>어느 컷에 어떻게 적용했나요?<textarea name="application" rows="4" required maxlength="6000" placeholder="예: 02의 이동 동작을 생략하고 음식 근접샷으로 바로 전환. 제외했다면 이유를 적어 주세요."></textarea></label><label>관련 컷 ID<input name="cuts" placeholder="예: 01, 02"></label><label>반영 근거 파일<textarea name="evidence" rows="3" placeholder="작품 내부 상대 경로를 한 줄에 하나씩 입력&#10;shooting-script.md"></textarea></label><p class="hint">파일 반영에는 실제 변경 파일, 영상 검수에는 영상 경로와 renders.md가 필요해요. 검수한 컷·시각은 위 설명에 함께 적어 주세요.</p><label>영상에서 확인한 결과<select name="outcome"><option value="">검수 전</option><option value="helpful">도움이 됨</option><option value="ineffective">효과 없음 · 다시 검토</option><option value="uncertain">판단 보류</option></select></label><p id="lesson-form-status" role="status" class="warning"></p><button type="submit" class="primary">적용 기록 저장</button></form></dialog>`);
  let selection = null, selectedProject = '', offset = 0, serial = 0, edit = null, dirty = false, busy = false, lastRevision = '';
  const stages = {planned:'적용 계획', applied:'파일 반영 · 영상 검수 전', reviewed:'영상 검수 기록', skipped:'이번 작품에서 제외'};
  const outcomes = {helpful:'도움이 됨', ineffective:'효과 없음', uncertain:'판단 보류'};
  const previousDirty = window.assetsDirty;
  window.assetsDirty = () => previousDirty?.() || dirty || busy;
  $('#feedback-tags').insertAdjacentHTML('beforebegin', `<details class="lesson-metadata"><summary>재사용 원칙 정리 · 조건과 방침</summary><p class="hint">확실한 조건만 적어 주세요. 비워두면 원문의 단어로 후보를 찾습니다.</p><div class="form-pair"><label>원칙 상태<select name="learning_state"><option value="candidate">검토 후보</option><option value="active">사용할 원칙</option><option value="retired">기본 추천에서 제외</option></select></label><label>원칙 주제<input name="learning_topic" placeholder="예: 발화 중 화면 구성"></label><label>이 주제의 방침<input name="learning_stance" placeholder="예: 얼굴 유지 / 화면 밖 설명 허용"></label><label>적용할 주제·장르<input name="learning_keywords" placeholder="쉼표로 구분: 요리, 인터뷰"></label><label>제외할 주제·장르<input name="learning_exclude_keywords" placeholder="쉼표로 구분"></label><label>적용 모델<input name="learning_models" placeholder="정확한 모델명, 쉼표로 구분"></label></div><fieldset id="lesson-stages"><legend>적용 단계 · 선택하지 않으면 모든 단계</legend><label><input type="checkbox" value="planning"> 기획</label><label><input type="checkbox" value="generation"> 생성</label><label><input type="checkbox" value="review"> 검수</label></fieldset></details>`);
  window.fillLessonMetadata=row=>{
    const m=row.learning||{};
    for(const k of ['topic','stance','keywords','exclude_keywords','models','state'])$('#feedback-form [name=learning_'+k+']').value=Array.isArray(m[k])?m[k].join(', '):(m[k]||(k==='state'?'candidate':''));
    $('#lesson-stages').querySelectorAll('input').forEach(e=>e.checked=m.stages?.includes(e.value)||false);
  };
  window.readLessonMetadata=item=>{
    const val=k=>$('#feedback-form [name=learning_'+k+']').value.trim(), list=k=>val(k).split(',').map(x=>x.trim()).filter(Boolean);
    const m={...(item.learning||{}),topic:val('topic'),stance:val('stance'),keywords:list('keywords'),exclude_keywords:list('exclude_keywords'),models:list('models'),state:val('state'),stages:[...document.querySelectorAll('#lesson-stages input:checked')].map(e=>e.value)};
    if(item.learning||m.topic||m.stance||m.keywords.length||m.exclude_keywords.length||m.models.length||m.stages.length||m.state!=='candidate')item.learning=m;
    for(const k of Object.keys(item))if(k.startsWith('learning_'))delete item[k];
  };
  const sourceLink = ref => '/?project=' + encodeURIComponent(ref.split('/feedback.json#')[0]) + '&view=feedback';
  function draw() {
    if (!selection) return;
    $('#lesson-summary').textContent = `${selection.source_count}개 원본 → ${selection.group_count}개 묶음 · 중복 ${selection.duplicate_count}개 정리 · 조건 확인 ${selection.review_count}개`;
    $('#lesson-list').innerHTML = selection.items.map(r => `<article class="feedback-card lesson-card"><div class="note-meta"><span>${esc(r.project_name)}</span><span>${r.ref_count > 1 ? `${r.ref_count}개 출처를 한 원칙으로` : '전작 경험'}</span></div><h4>${esc(r.title)}</h4><p>${esc(r.action)}</p>${r.context ? `<p class="hint"><b>적용 조건</b> ${esc(r.context)}</p>` : ''}<p class="hint">${esc(r.reasons.join(' · '))}</p>${[...r.warnings, ...r.excluded].map(w=>`<p class="lesson-caution">${esc(w)}</p>`).join('')}<p class="hint">영상 검수 기록 · 도움 ${r.outcomes.helpful}작품 / 효과 없음 ${r.outcomes.ineffective}작품 / 보류 ${r.outcomes.uncertain}작품</p>${r.improvement_candidate ? '<p class="lesson-caution">제작 원칙 갱신 후보 · 근거를 비교한 뒤 정리해 주세요.</p>' : ''}<div class="note-footer"><a href="${sourceLink(r.ref)}">원작품 기록 ↗</a><button data-lesson-use="${esc(r.ref)}">적용 · 제외 기록</button></div>${r.ref_count>1?`<details><summary>묶인 원본 ${r.ref_count}개 · 최대 20개 표시</summary>${r.refs.map(x=>`<p class="hint">${esc(x.ref)}</p>`).join('')}</details>`:''}</article>`).join('') || '<div class="empty-state">조건에 맞는 추천이 없어요.<br>검색을 바꾸거나 “조건 확인할 후보까지”에서 살펴보세요.</div>';
    $('#lesson-list').querySelectorAll('[data-lesson-use]').forEach(b=>b.onclick=()=>openRecord(selection.items.find(r=>r.ref===b.dataset.lessonUse)));
    $('#lesson-prev').disabled = offset === 0; $('#lesson-next').disabled = !selection.has_more;
    $('#lesson-page').textContent = selection.total ? `${offset+1}–${offset+selection.items.length} / ${selection.total}` : '0개';
    const plan = selection.plan;
    $('#lesson-plan-list').innerHTML = (plan?.items || []).map(r=>`<article class="feedback-card"><div class="note-meta"><span>${esc(stages[r.stage])}</span><span>${esc(outcomes[r.outcome]||'')}</span></div><h4>${esc(r.title)}</h4><p>${esc(r.application)}</p><p class="hint">${r.cuts.length?'컷 '+esc(r.cuts.join(', ')):'작품 전체'}${r.evidence.length?' · '+esc(r.evidence.map(e=>e.path).join(', ')):''}</p>${r.stale.map(w=>`<p class="lesson-caution">재확인 필요 · ${esc(w)}</p>`).join('')}<button data-lesson-edit="${esc(r.ref)}">적용 기록 수정</button></article>`).join('') || '<p class="hint">아직 선택한 전작 경험이 없어요. 위 후보에서 적용할 항목을 골라 주세요.</p>';
    $('#lesson-plan-list').querySelectorAll('[data-lesson-edit]').forEach(b=>b.onclick=()=>{const r=plan.items.find(i=>i.ref===b.dataset.lessonEdit);openRecord({ref:r.ref,source_hash:r.current_source_hash,title:r.title,action:r.current_action});});
    $('#lesson-history').innerHTML = [...(plan?.history||[])].reverse().map(h=>`<p class="lesson-history-row"><span>변경 ${h.revision} · ${esc(h.ref.split('#')[1])}</span><button data-lesson-revert="${h.revision}" data-ref="${esc(h.ref)}">이 변경 전으로 복원</button></p>`).join('') || '<p class="hint">저장하면 변경 이력이 남아요.</p>';
    $('#lesson-history').querySelectorAll('[data-lesson-revert]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/lesson-plan',{project:pid,operation:'revert',ref:b.dataset.ref,revision:plan.revision,history_revision:Number(b.dataset.lessonRevert)});await load();message('이전 적용 기록을 복원했습니다. 변경된 원본과 근거는 재확인 표시가 유지됩니다.');}catch(e){error(e);}finally{b.disabled=false;}});
  }
  async function load() {
    const mine=++serial, project=pid;
    if (!project || !data?.lesson_selection) { $('#lesson-summary').textContent='새 피드백 선별 기능은 제작실 서버를 다시 시작하면 사용할 수 있어요.'; return; }
    const fields=new FormData($('#lesson-filter'));
    const params=new URLSearchParams({project,stage:fields.get('stage'),query:fields.get('query'),model:fields.get('model'),browse:fields.get('browse'),limit:'6',offset:String(offset)});
    try { const result=await api('/api/lessons?'+params); if(mine!==serial||pid!==project)return; selection=result; draw(); }
    catch(e) {if(mine===serial){$('#lesson-summary').textContent='피드백 조회 실패 · '+e.message;$('#lesson-list').innerHTML='';}}
  }
  window.resetLessonMemory=()=>{++serial;selectedProject=pid;offset=0;lastRevision='';selection=null;$('#lesson-list').innerHTML='<p class="hint">작품에 맞는 경험을 불러오는 중…</p>';$('#lesson-plan-list').innerHTML='';$('#lesson-history').innerHTML='';$('#lesson-prev').disabled=true;$('#lesson-next').disabled=true;};
  window.renderLessonMemory=()=>{if(selectedProject!==pid)window.resetLessonMemory();if(lastRevision!==data?.revision){lastRevision=data?.revision;load();}};
  $('#lesson-filter').onsubmit=e=>{e.preventDefault();offset=0;load();};
  $('#lesson-filter [name=stage]').onchange=()=>{offset=0;load();};
  $('#lesson-filter [name=browse]').onchange=()=>{offset=0;load();};
  $('#lesson-prev').onclick=()=>{offset=Math.max(0,offset-6);load();};
  $('#lesson-next').onclick=()=>{offset+=6;load();};
  function openRecord(source) {
    const prior=selection.plan?.items.find(i=>i.ref===source.ref);
    edit={...source,project:pid,revision:selection.plan?.revision||0};
    putForm($('#lesson-form'),{stage:prior?.stage||'planned',application:prior?.application||'',cuts:(prior?.cuts||[]).join(', '),evidence:(prior?.evidence||[]).map(e=>e.path).join('\n'),outcome:prior?.outcome||''});
    $('#lesson-dialog-title').textContent=source.title;$('#lesson-source-action').textContent=source.action;$('#lesson-form-status').textContent='';dirty=false;$('#lesson-dialog').showModal();
  }
  const close=()=>{if(busy)return;if(dirty&&!confirm('저장하지 않은 적용 기록이 있어요. 닫을까요?'))return;$('#lesson-dialog').close();dirty=false;};
  $('#lesson-close').onclick=close;$('#lesson-dialog').addEventListener('cancel',e=>{e.preventDefault();close();});
  $('#lesson-form').oninput=()=>{dirty=true;};
  $('#lesson-form').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;e.submitter.disabled=true;const f=readForm(e.target);try{await api('/api/lesson-plan',{project:edit.project,revision:edit.revision,ref:edit.ref,source_hash:edit.source_hash,...f,cuts:f.cuts.split(/[,\s]+/).filter(Boolean),evidence:f.evidence.split('\n').map(s=>s.trim()).filter(Boolean)});dirty=false;$('#lesson-dialog').close();await load();message('적용 단계와 근거를 저장했습니다. 원본 피드백은 보존됩니다.');}catch(err){$('#lesson-form-status').textContent=err.message;}finally{busy=false;e.submitter.disabled=false;}};
  if(data)window.renderLessonMemory();
})();
