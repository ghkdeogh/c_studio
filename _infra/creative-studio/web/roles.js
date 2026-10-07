/* Role checklist: craft/roles/checklist.json merged with <project>/role-review.json. Saves on change. */
(() => {
  const anchor = document.querySelector('#feedback .notebook-layout');
  if (!anchor) return;
  const STATUS = [['pending', '대기'], ['pass', '통과'], ['fail', '문제'], ['na', '해당 없음']];
  const LABEL = Object.fromEntries(STATUS);
  const GATE = ['review', 'publish'];
  anchor.insertAdjacentHTML('afterend', `<section id="role-panel" class="role-panel" aria-labelledby="role-title"><div class="role-heading"><div><p class="eyebrow">ROLE CHECK · BEFORE UPLOAD</p><h3 id="role-title">역할 점검</h3><p class="hint">기획부터 게시까지 역할별로 확인해요. 상태와 메모는 바꾸는 즉시 이 작품의 role-review.json에 저장됩니다. 업로드 전에는 편집·검수와 게시 항목이 모두 통과 또는 해당 없음이어야 해요.</p></div><label class="role-by">확인자<input id="role-by" maxlength="80" placeholder="예: 편집자"></label></div><p id="role-summary" class="hint"></p><div id="role-tabs" class="role-tabs" role="tablist" aria-label="점검 단계"></div><div id="role-list" class="role-list" role="tabpanel" aria-labelledby="role-title"></div><p id="role-save-status" role="status" class="hint"></p></section>`);
  let view = null, shown = '', stage = null, serial = 0, busy = 0, stale = false, queue = Promise.resolve();
  try { $('#role-by').value = localStorage.getItem('studio-role-reviewer') || ''; } catch {}
  $('#role-by').onchange = () => { try { localStorage.setItem('studio-role-reviewer', $('#role-by').value.trim()); } catch {} };
  const previousDirty = window.assetsDirty;
  window.assetsDirty = () => previousDirty?.() || busy > 0;
  const when = at => at ? new Date(at * 1000).toLocaleString('ko-KR', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : '';
  const typing = () => document.activeElement?.classList?.contains('role-note') && $('#role-list').contains(document.activeElement);
  const count = (items, s) => items.filter(i => i.status === s).length;
  const say = text => { $('#role-save-status').textContent = text; };

  function draw() {
    if (!view) return;
    if (typing()) { stale = true; return; }  // keep the note being typed; redraw on blur
    stale = false;
    const focus = document.activeElement, keepRadio = focus?.type === 'radio' && $('#role-list').contains(focus) ? [focus.name, focus.value] : null, keepTab = $('#role-tabs').contains(focus) ? focus.dataset.roleStage : null;
    const roles = Object.fromEntries(view.roles.map(r => [r.id, r.label]));
    const byStage = Object.fromEntries(view.stages.map(s => [s.id, view.items.filter(i => i.stage === s.id)]));
    if (!byStage[stage]) stage = (view.stages.find(s => byStage[s.id].some(i => !['pass', 'na'].includes(i.status))) || view.stages[view.stages.length - 1]).id;
    const all = view.items, left = all.filter(i => GATE.includes(i.stage) && !['pass', 'na'].includes(i.status)).length;
    $('#role-summary').innerHTML = `전체 ${all.length}개 · 통과 ${count(all, 'pass')} · <span class="${count(all, 'fail') ? 'warning' : ''}">문제 ${count(all, 'fail')}</span> · 해당 없음 ${count(all, 'na')} · 대기 ${count(all, 'pending')}<br>${left ? `업로드 전 점검(편집·검수 · 게시) 남은 항목 ${left}개` : '업로드 전 점검(편집·검수 · 게시)을 모두 마쳤어요.'}`;
    $('#role-tabs').innerHTML = view.stages.map(s => {
      const items = byStage[s.id], fails = count(items, 'fail');
      return `<button type="button" role="tab" data-role-stage="${esc(s.id)}" aria-selected="${s.id === stage}">${esc(s.label)} ${count(items, 'pass')}/${items.length} 통과${fails ? ` <span class="pill warn">문제 ${fails}</span>` : ''}</button>`;
    }).join('');
    $('#role-tabs').querySelectorAll('[data-role-stage]').forEach(b => b.onclick = () => { stage = b.dataset.roleStage; draw(); });
    $('#role-list').innerHTML = byStage[stage].map(i => `<article class="role-item ${esc(i.status)}" data-role-item="${esc(i.id)}"><div class="role-item-head"><span class="role-chip">${esc(roles[i.role] || i.role)}</span><span class="hint">${i.at ? `${esc(LABEL[i.status])}${i.by ? ' · ' + esc(i.by) : ''} · ${when(i.at)}` : '아직 확인 전'}</span></div><p class="role-text">${esc(i.text)}</p><div class="role-status" role="radiogroup" aria-label="점검 상태">${STATUS.map(([v, l]) => `<label class="${v}"><input type="radio" name="role-${esc(i.id)}" value="${v}" ${i.status === v ? 'checked' : ''}><span>${l}</span></label>`).join('')}</div><input class="role-note" maxlength="2000" value="${esc(i.note)}" placeholder="메모 · 근거 (예: 3.25초 손가락 6개)" aria-label="메모 · ${esc(i.text)}"></article>`).join('') || '<p class="hint">이 단계의 점검 항목이 없어요.</p>';
    if (keepRadio) $('#role-list').querySelector(`input[name="${CSS.escape(keepRadio[0])}"][value="${CSS.escape(keepRadio[1])}"]`)?.focus();
    if (keepTab) $('#role-tabs').querySelector(`[data-role-stage="${CSS.escape(keepTab)}"]`)?.focus();
  }

  async function load() {
    const mine = ++serial, project = pid;
    if (!project || busy) return;
    try {
      const next = await api('/api/role-review?project=' + encodeURIComponent(project));
      if (mine !== serial || pid !== project || busy) return;
      view = next; draw();
    } catch (e) {
      if (mine === serial && pid === project) { $('#role-summary').textContent = '역할 점검 조회 실패 · ' + e.message; $('#role-tabs').innerHTML = ''; $('#role-list').innerHTML = ''; }
    }
  }

  function save(item, status, note) {
    const project = pid, text = view?.items.find(i => i.id === item)?.text || item;
    busy++;
    queue = queue.then(async () => {
      let failed = null;
      try {
        if (!view || pid !== project) return;
        const next = await api('/api/role-review', {project, item, status, note, by: $('#role-by').value.trim(), revision: view.revision});
        if (pid === project) { view = next; draw(); say(`저장했어요 · ${LABEL[status]} · ${text.slice(0, 40)}`); }
      } catch (e) { failed = e; } finally { busy--; }
      if (failed && pid === project) { say(failed.message + ' 최신 점검표를 다시 불러왔어요.'); message(failed.message); await load(); }
    });
  }

  $('#role-list').addEventListener('change', e => {
    const card = e.target.closest('[data-role-item]');
    if (!card) return;
    const status = card.querySelector('input[type=radio]:checked')?.value || 'pending';
    save(card.dataset.roleItem, status, card.querySelector('.role-note').value.trim());
  });
  $('#role-list').addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.classList.contains('role-note')) e.target.blur(); });
  $('#role-list').addEventListener('focusout', () => setTimeout(() => { if (stale && !busy && !typing()) draw(); }));

  window.resetRoleReview = () => { ++serial; shown = pid; view = null; stage = null; stale = false; $('#role-summary').textContent = '점검표를 불러오는 중…'; $('#role-tabs').innerHTML = ''; $('#role-list').innerHTML = ''; say(''); };
  window.renderRoleReview = () => {
    if (!data) return;
    if (shown !== pid) window.resetRoleReview();
    if (!('role_review_revision' in data)) { $('#role-summary').textContent = '역할 점검은 제작실 서버를 다시 시작하면 사용할 수 있어요.'; return; }
    if (!view || data.role_review_revision !== view.revision) load();
  };
  if (data) window.renderRoleReview();
})();
