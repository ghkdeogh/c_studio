/* Generation ledger, version comparison/adoption, YouTube publication status, channel comparison. Local data only. */
(() => {
  const $$ = s => document.querySelector(s);
  const money = v => v == null ? '—' : '$' + Number(v).toFixed(2);
  const num = v => v == null ? '—' : Number(v).toLocaleString('ko-KR', {maximumFractionDigits: 1});
  const pct = v => v == null ? '—' : num(v) + '%';
  const when = v => { if (!v) return ''; const d = new Date(v); return isNaN(d) ? String(v) : d.toLocaleString('ko-KR', {month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'}); };
  const PUB = {scheduled: '예약됨', published: '공개', public: '공개', private: '비공개', superseded_private: '비공개 보존', unlisted: '일부 공개', deleted: '삭제됨'};
  let compare = null;

  window.statsHtml = (d, generated, saved) => {
    const L = d.ledger || {};
    return `<span><b>${d.cuts.length}</b> 계획 컷</span><span><b>${L.image_cuts ?? 0}</b> 이미지 컷</span><span><b>${generated.length}</b> 영상 컷</span><span><b>${saved.length}</b> 구간 저장</span><span><b>${num(L.credits_used)}</b> H3 크레딧</span><span><b>${money(L.image_cost_usd)}</b> 이미지 비용</span><span class="sync">● 자동 동기화</span>`;
  };

  window.cutBadges = c => {
    const iv = c.image_versions || [], vv = c.video_versions || [];
    const ai = iv.find(v => v.adopted), av = vv.find(v => v.adopted);
    const parts = [];
    if (iv.length) parts.push(`<span class="ver-badge">이미지 ${esc(ai ? ai.label : '미채택')}${iv.length > 1 ? ' · ' + iv.length + '안' : ''}</span>`);
    if (vv.length) parts.push(`<span class="ver-badge ${av ? 'ok' : ''}">영상 ${esc(av ? av.label : '미채택')}${av?.credits ? ' · ' + num(av.credits) + 'cr' : ''}${vv.length > 1 ? ' · 재시도 ' + (vv.length - 1) : ''}</span>`);
    return parts.length ? `<div class="badges">${parts.join('')}</div>` : '';
  };

  function renderLedger() {
    const box = $$('#ledger-panel'), L = data.ledger;
    if (!L) { box.innerHTML = ''; return; }
    const bal = L.balance, need = L.pending_credits;
    const short = bal && L.credits_short > 0;
    const state = !L.pending_video_cuts ? '' : !bal ? '<span class="pill muted">잔액 미기록</span>' : short ? `<span class="pill warn">충전 필요 · ${num(L.credits_short)}크레딧 부족</span>` : '<span class="pill ok">잔액으로 생성 가능</span>';
    box.innerHTML = `<div class="ledger"><div><p class="eyebrow">GENERATION LEDGER</p><p>H3 영상 <b>${L.video_count}건 · ${num(L.credits_used)}크레딧</b> (재시도 ${L.retries}회 · 접수 실패 ${L.failed_submissions}건) · 이미지 콘티 <b>${L.image_count}장 · ${money(L.image_cost_usd)}</b></p><p class="hint">${L.pending_video_cuts ? `영상 없는 컷 ${L.pending_video_cuts}개 → 약 ${num(need)}크레딧 필요(${L.rates.clip_seconds}초 기준)` : '모든 컷에 영상이 있습니다'}${bal ? ` · 힉스필드 잔액 ${num(bal.balance)} (${when(bal.as_of)} 기록)` : ''} · 비용은 요금표 기준 추정치</p></div><div class="ledger-actions">${state}<button id="credits-record">잔액 기록</button></div></div>`;
    $$('#credits-record').onclick = recordCredits;
  }
  async function recordCredits() {
    const v = window.prompt('힉스필드 현재 잔액(크레딧)을 입력하세요. MCP balance 또는 higgsfield.ai 화면에서 확인한 값.', data.ledger?.balance?.balance ?? '');
    if (v == null || v.trim() === '') return;
    const balance = Number(v);
    if (!Number.isFinite(balance) || balance < 0) return error(Error('잔액은 0 이상의 숫자로 입력해 주세요.'));
    try { await api('/api/credits', {service: 'higgsfield', balance}); await refresh(true); message('힉스필드 잔액을 기록했습니다.'); } catch (e) { error(e); }
  }

  function renderPublications() {
    const box = $$('#publication-panel'), rows = data.publications || [];
    box.hidden = !rows.length;
    if (!rows.length) { box.innerHTML = ''; return; }
    const now = Date.now();
    box.innerHTML = `<div class="section-heading"><div><p class="eyebrow">YOUTUBE</p><h2>게시 상태</h2><p class="hint">exports 폴더의 게시 기록(youtube-publication.json)을 그대로 보여줍니다.</p></div></div>` + rows.map(r => {
      const at = r.scheduled_publish_at ? new Date(r.scheduled_publish_at) : null;
      const passed = r.status === 'scheduled' && at && at.getTime() < now;
      const cls = r.status === 'scheduled' ? (passed ? 'warn' : 'wait') : ['published', 'public'].includes(r.status) ? 'ok' : 'muted';
      const live = at && !r.hidden;
      return `<article class="pub-row ${r.hidden ? 'hidden-pub' : ''}"><span class="pill ${cls}">${esc(r.label || '게시 기록')}</span><div><b><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(r.title)} ↗</a></b><p class="hint">${at ? '공개 시각 ' + at.toLocaleString('ko-KR') + ' · ' : ''}${r.uploaded_at ? '업로드 ' + when(r.uploaded_at) + ' · ' : ''}원본 ${esc(r.source || '미기록')}${r.replaces_video_id ? ' · 이전 영상 ' + esc(r.replaces_video_id) + ' 대체' : ''}</p>${passed ? '<p class="warning">예약 시각이 지났습니다. Studio에서 공개를 확인한 뒤 게시 기록의 status를 published로 갱신해 주세요.</p>' : ''}${live ? `<p class="hint">성과 확인 시각 · 24시간 ${when(at.getTime() + 864e5)} · 48시간 ${when(at.getTime() + 2 * 864e5)} · 7일 ${when(at.getTime() + 7 * 864e5)}</p>` : ''}${r.note && !r.hidden ? `<p class="hint">${esc(r.note)}</p>` : ''}</div></article>`;
    }).join('');
  }

  const channelBox = document.createElement('section');
  channelBox.id = 'channel-panel';
  channelBox.setAttribute('aria-label', '채널 성과 비교');
  ($$('#youtube-panel') || $$('.feedback-tools')).before(channelBox);
  function renderChannel() {
    const C = data.channel;
    if (!C) { channelBox.innerHTML = ''; return; }
    channelBox.innerHTML = `<div class="yt-heading"><div><p class="eyebrow">CHANNEL</p><h3>편별 성과 비교 · ${num(C.wall)}회 벽</h3><p class="hint">각 작품의 마지막 성과 기록입니다. 벽을 넘는 편이 나오면 그 기둥의 비중을 올립니다(채널 컨셉 성과 판정).</p></div></div><div class="yt-table-scroll channel-table"><table><thead><tr><th>편</th><th>게시일</th><th>상태</th><th>조회수</th><th>계속 시청</th><th>평균 조회율</th><th>좋아요</th><th>구독 순증</th><th>확인 시각</th></tr></thead><tbody>${C.rows.map(r => `<tr class="${r.over_wall ? 'over' : ''}"><td><a href="/?project=${encodeURIComponent(r.project)}&view=feedback">${esc(r.project_name)}</a></td><td>${esc(r.published_date || (r.scheduled_publish_at ? when(r.scheduled_publish_at) : ''))}</td><td><span class="pill ${r.over_wall ? 'ok' : r.status === 'scheduled' ? 'wait' : 'muted'}">${esc(PUB[r.status] || r.label || '게시 기록')}${r.over_wall ? ' · 벽 넘음' : ''}</span></td><td>${num(r.views)}</td><td>${pct(r.stayed)}</td><td>${pct(r.avg_pct)}</td><td>${num(r.likes)}</td><td>${num(r.subs)}</td><td class="hint">${r.as_of ? when(r.as_of) : '기록 없음'}</td></tr>`).join('') || '<tr><td colspan="9">게시 기록이 없습니다.</td></tr>'}</tbody></table></div>`;
  }

  window.renderStatus = () => { if (!data) return; renderLedger(); renderPublications(); renderChannel(); };

  window.renderCutVersions = c => { compare = null; drawVersions(c); };
  function drawVersions(c) {
    const box = $$('#cut-versions'), iv = c.image_versions || [], vv = c.video_versions || [];
    if (!iv.length && !vv.length) { box.innerHTML = ''; return; }
    const thumb = (v, kind) => `<button type="button" class="ver-thumb ${v.adopted ? 'adopted' : ''} ${compare?.kind === kind && compare.version === v.version ? 'picked' : ''}" data-kind="${kind}" data-version="${esc(v.version)}" aria-pressed="${compare?.kind === kind && compare.version === v.version}">${(kind === 'image' ? v.url : v.first_frame_url) ? `<img loading="lazy" src="${esc(kind === 'image' ? v.url : v.first_frame_url)}" alt="">` : '<span class="empty-frame">미리보기 없음</span>'}<span>${esc(v.label)}${v.adopted ? ' · 채택' : ''}</span><small>${kind === 'image' ? (v.cost_usd != null ? money(v.cost_usd) : esc(v.quality || '')) : (v.duration ? Number(v.duration).toFixed(1) + '초' : '') + (v.credits ? ' · ' + num(v.credits) + 'cr' : '')}</small></button>`;
    box.innerHTML = `<h3>버전 비교 · 채택</h3>${iv.length ? `<p class="hint">이미지 콘티 ${iv.length}안</p><div class="ver-row">${iv.map(v => thumb(v, 'image')).join('')}</div>` : ''}${vv.length ? `<p class="hint">영상 ${vv.length}안</p><div class="ver-row">${vv.map(v => thumb(v, 'video')).join('')}</div>` : ''}<div id="ver-compare"></div>`;
    box.querySelectorAll('.ver-thumb').forEach(b => b.onclick = () => { compare = {kind: b.dataset.kind, version: b.dataset.version}; drawVersions(c); });
    if (!compare) return;
    const list = compare.kind === 'image' ? iv : vv, cand = list.find(v => v.version === compare.version), cur = list.find(v => v.adopted);
    if (!cand) return;
    const media = v => compare.kind === 'image' ? `<img src="${esc(v.url)}" alt="">` : `<video controls playsinline preload="metadata" src="${esc(v.url)}" poster="${esc(v.first_frame_url || '')}"></video>`;
    const meta = v => compare.kind === 'image'
      ? `${esc(v.model)} · ${esc(v.size)} ${esc(v.quality)} · ${money(v.cost_usd)} · ${when(v.generated_at)}${v.reference_roles?.length ? ' · 참조 ' + esc(v.reference_roles.join(', ')) : ''}`
      : `${esc(v.model)} · ${v.duration ? Number(v.duration).toFixed(3) + '초' : '길이 미기록'} · ${v.credits != null ? num(v.credits) + '크레딧' : '크레딧 미기록'} · ${when(v.collected_at)}${v.contact_url ? ` · <a href="${esc(v.contact_url)}" target="_blank" rel="noopener">프레임 시트 ↗</a>` : ''}${v.asr ? `<br>들린 대사 · ${esc(v.asr)}` : ''}`;
    $$('#ver-compare').innerHTML = `<div class="compare"><figure><figcaption>현재 채택${cur ? ' · ' + esc(cur.label) : ' 없음'}</figcaption>${cur ? media(cur) : '<div class="empty-frame">채택된 버전 없음</div>'}${cur ? `<p class="hint">${meta(cur)}</p>` : ''}</figure><figure><figcaption>후보 · ${esc(cand.label)}</figcaption>${media(cand)}<p class="hint">${meta(cand)}</p></figure></div><div class="compare-actions"><button type="button" class="primary" id="adopt-version" ${cand.adopted ? 'disabled' : ''}>${cand.adopted ? '이미 채택된 버전' : '이 버전 채택'}</button><span class="hint">${compare.kind === 'image' ? '채택하면 project.json의 planned_start_image가 이 이미지로 바뀝니다. 영상 입력 확정은 아닙니다.' : '채택하면 컷의 영상·끝 프레임·요청 파일이 이 버전으로 바뀌고, 저장한 사용 구간은 다시 확인해야 합니다.'}</span></div>`;
    $$('#adopt-version').onclick = () => adopt(c, compare.kind, cand.version);
  }
  async function adopt(c, kind, version) {
    if (review?.dirty || noteDirty) return error(Error('저장하지 않은 구간이나 메모가 있어요. 먼저 저장하거나 되돌린 뒤 채택해 주세요.'));
    const id = c.id, project = pid, button = $$('#adopt-version');
    button.disabled = true;
    try {
      await api('/api/adopt', {project, cut: id, kind, version});
      pending = await api('/api/project?id=' + encodeURIComponent(project));
      message(`컷 ${id}의 ${kind === 'image' ? '이미지' : '영상'} ${version}을 채택했습니다.`);
      $$('#editor').close();
      openCut(id);
    } catch (e) { error(e); button.disabled = false; }
  }

  if (data) window.renderStatus();
})();
