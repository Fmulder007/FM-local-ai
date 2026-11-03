const TOKEN = document.querySelector('meta[name=token]').content;
const $ = (s) => document.querySelector(s);
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; /* хранилище недоступно или переполнено */ } },
};
const api = (path, body, signal) => fetch(path, {
  method: body === undefined ? 'GET' : 'POST', signal,
  headers: { 'X-Token': TOKEN, 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});
const getJSON = async (p) => (await api(p)).json();

// Анимация появления (.pop) — только у сообщений с индексом ≥ popFrom; полная перерисовка чата не должна «мигать» всеми сообщениями.
let popFrom = Infinity;
const S = {
  lang: store.get('lang', (navigator.language || 'ru').toLowerCase().startsWith('ru') ? 'ru' : 'en'),
  theme: store.get('theme', matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'),
  view: 'scan', st: null, sel: null, model: store.get('model', null),
  chats: store.get('chats', []), chat: store.get('chat', null), think: store.get('think', false),
  streaming: null, job: null, poll: null, jobTried: null,
  upd: null, updBusy: false, pending: [], pendingFiles: [],
  stat: null, statFor: null, speed: store.get('speed', {}), pcBusy: false,
  pathEdit: null, pathErr: '', pathBusy: false,
};

const t = (k, v = {}) => (I18N[S.lang][k] ?? I18N.ru[k] ?? k).replace(/\{(\w+)\}/g, (_, n) => v[n] ?? '');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtGB = (n) => (n >= 10 ? n.toFixed(0) : n.toFixed(1)).replace('.', S.lang === 'ru' ? ',' : '.');
const fmtB = (b) => b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(2)} ${t('gb')}` : `${(b / 1024 ** 2).toFixed(0)} ${S.lang === 'ru' ? 'МБ' : 'MB'}`;
const fmtSpeed = (b) => b > 0 ? ` · ${(b / 1024 ** 2).toFixed(1)} ${S.lang === 'ru' ? 'МБ/с' : 'MB/s'}` : '';
const modelById = (id) => S.st?.models.find((m) => m.id === id);
const recommended = () => S.st.models.find((m) => m.recommended);
const installedIds = () => S.st.installed.map((m) => m.id);
const fmtNum = (n) => Number(n).toLocaleString(S.lang === 'ru' ? 'ru-RU' : 'en-US');
// Возможности: у установленной модели — из Ollama, у остальных — из каталога.
const capsOf = (id) => S.st?.installed.find((m) => m.id === id)?.caps || modelById(id)?.caps || [];

/* ---------- значки возможностей ---------- */
const CAPS = ['text', 'code', 'think', 'vision', 'tools', 'image_gen', 'video_gen'];
const ICON = {
  text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>',
  think: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.7 1 1.5 1 2.5h6c0-1 .2-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
  vision: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  tools: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  image_gen: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="8.5" cy="8.5" r="1.5"/>',
  video_gen: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
};
const icon = (k, size = 14) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICON[k]}</svg>`;
// all — показать и то, чего модель не умеет (в том числе генерацию рисунков и видео).
const capChips = (caps, all) => `<div class="caps">${CAPS.filter((k) => all || caps.includes(k)).map((k) => {
  const yes = caps.includes(k);
  return `<span class="cap ${yes ? 'yes' : 'no'}" title="${esc(t('capd_' + k))}">${icon(k)}${t('cap_' + k)}${yes ? '' : ` — ${t('capNo')}`}</span>`;
}).join('')}</div>`;

/* ---------- оболочка: язык, тема, виды ---------- */
function applyLang() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('#langSeg button').forEach((b) => b.classList.toggle('on', b.dataset.lang === S.lang));
  $('#helpBtn').title = t('helpTip');
  $('#themeBtn').title = t('theme');
  $('#input').placeholder = t('placeholder');
  render();
}
function applyTheme() { document.documentElement.dataset.theme = S.theme; }
function show(view) {
  S.view = view;
  ['scan', 'welcome', 'install', 'chat'].forEach((v) => { $('#v-' + v).hidden = v !== view; });
  $('#modelChip').hidden = view !== 'chat';
}
function render() {
  if (!S.st) return;
  if (S.view === 'welcome') renderWelcome();
  if (S.view === 'install') renderInstall();
  if (S.view === 'chat') renderChat();
  if (!$('#modelsModal').hidden) renderModels();
  if (!$('#aboutModal').hidden) renderAbout();
  if (!$('#pcModal').hidden) renderPc();
}

/* ---------- подтверждение ---------- */
// o.yes / o.no — свои подписи; o.cancel — третья кнопка, тогда ответ true / false / null.
// o.extra — HTML под текстом (галочки), o.valid() — можно ли нажать «Да» при текущих галочках, o.danger — красная «Да».
function confirmDlg(title, text, o = {}) {
  return new Promise((resolve) => {
    $('#cTitle').textContent = title; $('#cText').textContent = text;
    const yes = $('#cYes'), ex = $('#cExtra');
    yes.textContent = o.yes || t('cYes'); $('#cNo').textContent = o.no || t('cNo');
    yes.className = 'btn ' + (o.danger ? 'danger-fill' : 'primary');
    ex.innerHTML = o.extra || '';
    const check = () => { yes.disabled = o.valid ? !o.valid(ex) : false; };
    ex.onchange = check; check();
    const c = $('#cCancel'); c.hidden = !o.cancel; c.textContent = o.cancel || '';
    const m = $('#confirmModal'); m.hidden = false;
    const done = (v) => { m.hidden = true; yes.onclick = $('#cNo').onclick = c.onclick = ex.onchange = null; resolve(v); };
    yes.onclick = () => done(true); $('#cNo').onclick = () => done(false); c.onclick = () => done(null);
    (o.danger ? $('#cNo') : yes).focus();   // для необратимого по Enter — отказ
  });
}

/* ---------- приветствие и подбор ---------- */
const modeBadge = (m) => {
  const cls = { gpu: 'good', mixed: 'warn', cpu: 'warn', no: 'bad' }[m.mode];
  return `<span class="badge ${cls}">${t('mode_' + m.mode)}</span>`;
};
const modelBadges = (m) => modeBadge(m)
  + `<span class="badge">${fmtGB(m.size)} ${t('gb')}</span>`
  + (m.fast_cpu ? `<span class="badge">${t('fastCpu')}</span>` : '')
  + (!m.disk_ok ? `<span class="badge bad">${t('noDisk')}</span>` : '');

const hwStatsHTML = (hw) => {
  const gpu = hw.gpu;
  return `
    <div class="stat full"><b title="${esc(gpu ? gpu.name : t('noGpu'))}">${esc(gpu ? gpu.name : t('noGpu'))}</b><span>${t('gpu')}${gpu ? '' : ' — ' + t('cpuMode')}</span></div>
    <div class="stat"><b>${gpu ? fmtGB(hw.vram_gb) + ' ' + t('gb') : '—'}</b><span>${t('vram')}</span></div>
    <div class="stat"><b>${fmtGB(hw.ram_gb)} ${t('gb')}</b><span>${t('ram')}</span></div>
    <div class="stat full"><b>${fmtGB(hw.disk_free_gb)} ${t('gb')}</b><span>${t('disk')}${drive(S.st.paths?.models.path)}</span></div>`;
};
const drive = (p) => (/^[a-z]:/i.test(p || '') ? ' ' + p.slice(0, 2).toUpperCase() : '');

/* ---------- куда ставить ---------- */
const shortPath = (p) => (p.length > 30 ? `${p.slice(0, 9)}…${p.slice(-20)}` : p);
function pathsHTML() {
  const P = S.st.paths;
  const row = (k, label) => {
    const p = P[k];
    const body = S.pathEdit === k
      ? `<input class="pinput" data-pin="${k}" value="${esc(p.path)}" spellcheck="false">
         <button type="button" class="btn sm primary" data-pok="${k}" ${S.pathBusy ? 'disabled' : ''}>OK</button>
         <button type="button" class="btn sm" data-pno>${t('cancel')}</button>`
      : `<div class="pv"><code title="${esc(p.path)}">${esc(shortPath(p.path))}</code>
         <small class="muted">${t('freeGb', { n: fmtGB(p.free_gb) })}</small></div>
         <button type="button" class="btn sm" data-pchg="${k}" ${S.pathBusy ? 'disabled' : ''}>${t('change')}</button>`;
    return `<div class="prow"><span class="pk">${label}</span>${body}</div>`;
  };
  return `<div class="paths"><div class="ptitle">${t('whereTitle')}</div>
    ${row('engine', t('pEngine'))}${row('models', t('pModels'))}
    ${S.pathErr ? `<p class="err small">${esc(S.pathErr)}</p>` : ''}</div>`;
}
function bindPaths(root) {
  root.querySelectorAll('[data-pchg]').forEach((b) => { b.onclick = () => changePath(b.dataset.pchg); });
  root.querySelectorAll('[data-pok]').forEach((b) => { b.onclick = () => applyPath(b.dataset.pok, root.querySelector(`[data-pin="${b.dataset.pok}"]`).value); });
  root.querySelectorAll('[data-pno]').forEach((b) => { b.onclick = () => { S.pathEdit = null; S.pathErr = ''; render(); }; });
  const inp = root.querySelector('[data-pin]');
  if (!inp) return;
  inp.focus(); inp.select();
  inp.onkeydown = (e) => {
    if (e.key === 'Enter') applyPath(inp.dataset.pin, inp.value);
    if (e.key === 'Escape') { S.pathEdit = null; S.pathErr = ''; render(); }
  };
}
// В окне pywebview — системный выбор папки, в браузере (демо, запасной режим) — ввод пути.
async function changePath(kind) {
  S.pathErr = '';
  if (!window.pywebview?.api?.pick_folder) { S.pathEdit = kind; return render(); }
  const p = await window.pywebview.api.pick_folder(S.st.paths[kind].path);
  if (p) applyPath(kind, p);
}
async function applyPath(kind, path) {
  if (S.pathBusy) return;
  S.pathBusy = true; S.pathErr = ''; render();
  try {
    const chk = await (await api('/api/paths/check', { kind, path })).json();
    if (!chk.ok) throw new Error(chk.error);
    if (chk.same) { S.pathEdit = null; return; }
    let move = false;
    if (kind === 'engine' && S.st.engine.installed
      && !(await confirmDlg(t('cEngineDirTitle'), t('cEngineDirText', { path: chk.path })))) return;
    if (kind === 'models' && chk.old?.count) {
      // Смена папки меняет список установленных моделей — только с подтверждением.
      const r = await confirmDlg(t('cModelsDirTitle'), t('cModelsDirText', { n: chk.old.count, size: fmtGB(chk.old.gb), old: chk.old.path, path: chk.path }),
        { yes: t('moveModels'), no: t('redownload'), cancel: t('cancel') });
      if (r === null) return;
      move = r;
    }
    if (S.streaming) S.streaming.abort();
    const r = await (await api('/api/paths', { kind, path: chk.path, move })).json();
    if (!r.ok) throw new Error(r.error);
    S.pathEdit = null;
    if (r.job) { $('#pcModal').hidden = true; watchJob(); return; }
    S.st = await getJSON('/api/state'); S.statFor = null;
  } catch (e) {
    S.pathErr = errText(e.message);
  } finally {
    S.pathBusy = false; render();
  }
}

function renderWelcome() {
  $('#hwStats').innerHTML = hwStatsHTML(S.st.hw);
  const m = modelById(S.sel) || recommended();
  S.sel = m.id;
  $('#recCard').innerHTML = `
    <h3>${m.recommended ? t('recommended') : t('chooseOther')}</h3>
    <div class="name">${esc(m.title)}</div>
    <div class="desc">${t('tag_' + m.tag)}</div>
    <div class="badges">${modelBadges(m)}</div>
    ${capChips(m.caps, true)}
    <div style="flex:1"></div>
    ${pathsHTML()}
    <button class="btn primary big" id="installBtn" ${S.pathBusy ? 'disabled' : ''}>${t('install')}</button>
    <button class="link" id="otherBtn">${t('chooseOther')}</button>`;
  bindPaths($('#recCard'));
  $('#installBtn').onclick = () => startInstall(m.id);
  $('#otherBtn').onclick = () => openModels();
}

async function startInstall(id) {
  S.jobTried = id;
  const r = await (await api('/api/setup', { model: id })).json();
  if (r.error) return;
  watchJob();
}

/* ---------- установка ---------- */
function watchJob() {
  show('install');
  clearInterval(S.poll);
  const tick = async () => {
    S.job = await getJSON('/api/job');
    renderInstall();
    if (!S.job || S.job.state === 'running') return;
    clearInterval(S.poll);
    if (S.job.state === 'done' && S.job.kind === 'uninstall') return uninstallDone(S.job);
    if (S.job.state === 'done') {
      S.st = await getJSON('/api/state'); S.statFor = null;
      if (S.job.kind !== 'install') {
        // Обновили или перенесли движок/модели — возвращаемся в тот же чат и перепроверяем обновления.
        show('chat'); render(); checkUpdates(true);
        return;
      }
      S.model = S.job.model; store.set('model', S.model);
      newChat(); show('chat'); render(); checkUpdates(false);
    }
  };
  S.poll = setInterval(tick, 700); tick();
}

function renderInstall() {
  const j = S.job;
  if (!j) return;
  const m = modelById(j.model);
  const what = j.model ? (m ? m.title : j.model) : 'Ollama';
  $('#instTitle').textContent = j.state === 'error' ? t('errTitle') : j.state === 'cancelled' ? t('cancelled')
    : j.kind === 'uninstall' ? t('uninstalling') : j.kind === 'move' ? t('movingModels') : j.target ? t('movingEngine')
      : `${t(j.kind === 'update' ? 'updating' : 'installing')}: ${what}`;
  const order = j.steps.indexOf(j.step);
  $('#instSteps').innerHTML = j.steps.map((s, i) => {
    const finished = j.state === 'done' || i < order;
    const active = j.state === 'running' && i === order;
    const counted = j.phase === 'download' || j.phase === 'copy' || j.phase === 'delete';
    const busy = active && (!counted || !j.total);
    const pct = finished ? 100 : active ? j.percent : 0;
    let info = t('waiting');
    if (finished) info = t('done');
    else if (active) info = `${t('ph_' + (j.phase || 'start'))}` + (j.total && counted ? ` — ${fmtB(j.done)} / ${fmtB(j.total)}${fmtSpeed(j.speed)}` : '');
    return `<div class="step ${!finished && !active ? 'pending' : ''}">
      <div class="step-head"><span>${i + 1}. ${t('step_' + s)}${s === 'model' && m ? ` · ${esc(m.title)}` : ''}</span><small>${pct && !busy ? Math.round(pct) + '%' : ''}</small></div>
      <div class="bar ${busy ? 'busy' : ''}"><i style="width:${busy ? 100 : pct}%"></i></div>
      <small class="muted">${info}</small></div>`;
  }).join('');
  const err = j.state === 'error' ? `<p class="err small">${esc(errText(j.error))}</p>` : '';
  const un = j.kind === 'uninstall';
  $('#instNote').innerHTML = err || (j.state === 'running' ? t(un ? 'uNote' : 'installNote') : '');
  const failed = j.state === 'error' || j.state === 'cancelled';
  // Удаление не отменяется: деинсталлятор Ollama не прервать, а половина удалённого — хуже, чем всё.
  $('#instActions').innerHTML = j.state === 'running' && un ? '' : j.state === 'running'
    ? `<button class="btn" id="cancelBtn">${t('cancel')}</button>`
    : failed ? `<button class="btn primary" id="retryBtn">${t('retry')}</button><button class="btn" id="backBtn">${t('back')}</button>` : '';
  if ($('#cancelBtn')) $('#cancelBtn').onclick = () => api('/api/cancel', {});
  if ($('#retryBtn')) $('#retryBtn').onclick = () => retryJob(j);
  if ($('#backBtn')) $('#backBtn').onclick = () => (installedIds().length ? (show('chat'), render()) : (show('welcome'), render()));
}
async function retryJob(j) {
  if (j.kind === 'uninstall') { if ((await (await api('/api/uninstall', { parts: j.target })).json()).started) watchJob(); return; }
  if (!j.target) return j.kind === 'update' ? startUpdate(j.model) : startInstall(j.model);
  const r = await (await api('/api/paths', { kind: j.kind === 'move' ? 'models' : 'engine', path: j.target, move: true })).json();
  if (r.job) watchJob(); else { show('chat'); render(); }
}
function errText(e) {
  const code = (e || '').split(':')[0];
  return I18N[S.lang]['err_' + code] ? t('err_' + code) : e;
}

/* ---------- каталог моделей ---------- */
function openModels() { $('#modelsModal').hidden = false; renderModels(); }
function renderModels() {
  const inChat = installedIds().length > 0;
  const rows = S.st.models;
  const have = new Set(installedIds());
  const row = (m, extra) => `<div class="mrow ${m.id === S.model && inChat ? 'on' : ''}">
    <div class="info"><div class="t">${esc(m.title)} ${m.recommended ? `<span class="star">★ ${t('recommended')}</span>` : ''}</div>
    <div class="d">${t('tag_' + m.tag)}</div><div class="badges" style="margin-top:6px">${modelBadges(m)}</div>
    ${capChips(capsOf(m.id), false)}</div>${extra}</div>`;
  let html = '';
  if (inChat) {
    html += `<div class="sect">${t('installed')}</div>`;
    html += rows.filter((m) => have.has(m.id)).map((m) => row(m, m.id === S.model
      ? `<span class="badge good">${t('inUse')}</span>`
      : `<button class="btn sm primary" data-use="${m.id}">${t('use')}</button>`
      + `<button class="btn sm danger" data-del="${m.id}">${t('remove')}</button>`)).join('');
    const extra = S.st.installed.filter((i) => !modelById(i.id));
    html += extra.map((i) => `<div class="mrow"><div class="info"><div class="t">${esc(i.id)}</div>${capChips(i.caps || [], false)}</div>
      ${i.id === S.model ? `<span class="badge good">${t('inUse')}</span>` : `<button class="btn sm primary" data-use="${esc(i.id)}">${t('use')}</button>`}</div>`).join('');
    html += `<div class="sect">${t('available')}</div>`;
  }
  // Предлагаем только то, что подходит этому ПК (fits из catalog.recommend); если ничего — хотя бы рекомендованную.
  const fit = rows.filter((m) => !have.has(m.id) && m.fits);
  const list = fit.length ? fit : rows.filter((m) => !have.has(m.id) && m.recommended);
  if (list.length) html += `<p class="muted small">${t(fit.length ? 'fitNote' : 'noFit')}</p>`;
  html += list.map((m) => row(m,
    `<button class="btn sm primary" data-get="${m.id}">${inChat ? t('installModel') : t('use')}</button>`)).join('');
  html += `<p class="muted small note">${t('noGenNote')}</p>`;
  const body = $('#modelsBody');
  body.innerHTML = html;
  body.querySelectorAll('[data-get]').forEach((b) => { b.onclick = () => pickModel(b.dataset.get, inChat); });
  body.querySelectorAll('[data-use]').forEach((b) => { b.onclick = () => useModel(b.dataset.use); });
  body.querySelectorAll('[data-del]').forEach((b) => { b.onclick = () => removeModel(b.dataset.del); });
}

// Спрашиваем подтверждение везде, где меняется выбор модели.
async function pickModel(id, inChat) {
  const m = modelById(id), rec = recommended();
  if (inChat) {
    if (!(await confirmDlg(t('cInstallTitle'), t('cInstallText', { sel: m.title, size: fmtGB(m.size) })))) return;
    $('#modelsModal').hidden = true; return startInstall(id);
  }
  if (id !== rec.id) {
    const why = m.mode === 'no' ? t('whyNo') : !m.disk_ok ? t('whyDisk') : m.mode === 'gpu' ? t('whyFine', { size: fmtGB(m.size) }) : t('whySlow');
    if (!(await confirmDlg(t('cOtherTitle'), t('cOtherText', { rec: rec.title, sel: m.title, why })))) return;
  }
  S.sel = id; $('#modelsModal').hidden = true; renderWelcome();
}
async function useModel(id) {
  const m = modelById(id);
  if (!(await confirmDlg(t('cSwitchTitle'), t('cSwitchText', { sel: m ? m.title : id })))) return;
  S.model = id; store.set('model', id); $('#modelsModal').hidden = true; render();
}
async function removeModel(id) {
  const m = modelById(id);
  if (!(await confirmDlg(t('cRemoveTitle'), t('cRemoveText', { sel: m ? m.title : id })))) return;
  await api('/api/delete', { model: id });
  S.st = await getJSON('/api/state');
  renderModels();
}

/* ---------- о модели и обновления ---------- */
function openAbout() { $('#aboutModal').hidden = false; S.info = null; renderAbout(); loadAbout(); }
async function loadAbout() {
  const id = S.model;
  try { const r = await api('/api/model?name=' + encodeURIComponent(id)); S.info = r.ok ? await r.json() : {}; } catch { S.info = {}; }
  if (S.model === id && !$('#aboutModal').hidden) renderAbout();
  if (S.model === id && S.info.id === id) { S.stat = S.info; if (S.view === 'chat') renderSideStats(); }
  if (!S.upd) checkUpdates(false);
}
async function checkUpdates(force) {
  if (S.updBusy) return;
  S.updBusy = true; render();
  try { S.upd = await getJSON('/api/updates' + (force ? '?force' : '')); } catch { S.upd = null; }
  S.updBusy = false; render();
}
function renderChip() {
  const m = modelById(S.model);
  $('#modelChipName').textContent = m ? m.title : S.model;
  $('#modelChipCaps').innerHTML = capsOf(S.model).filter((k) => k !== 'text').map((k) => `<span title="${esc(t('cap_' + k))}">${icon(k, 13)}</span>`).join('');
  $('#modelChipUpd').hidden = !(S.upd && (S.upd.engine?.available || S.upd.models?.[S.model]?.available));
  $('#modelChip').title = t('about');
}
function renderAbout() {
  const body = $('#aboutBody'), i = S.info, m = modelById(S.model);
  if (!i) { body.innerHTML = `<p class="muted">${t('loading')}</p>`; return; }
  const title = m ? m.title : S.model;
  const caps = i.caps || capsOf(S.model);
  const w = i.where;
  const where = w ? `${t('where_' + w.mode)}${w.mode !== 'cpu' ? ` · ${t('whereVram', { pct: w.vram_pct })}` : ''}` : t('whereIdle');
  const ctx = i.ctx_max ? t('ctxVal', { max: fmtNum(i.ctx_max) }) + (w && w.ctx ? ` <small class="muted">(${t('ctxNow', { now: fmtNum(w.ctx) })})</small>` : '') : '—';
  const u = S.upd, e = u?.engine, mu = u?.models?.[S.model];
  const unknown = S.updBusy ? t('checking') : t('updUnknown');
  const eLine = !e || e.error ? unknown : e.available ? t('updAvail', { v: e.latest }) : t('upToDate');
  const mLine = !mu || mu.error ? unknown : !mu.checked ? t('updNotChecked') : mu.available ? t('modelUpd') : t('modelFresh');
  body.innerHTML = `
    <div class="about-head"><div class="info"><div class="name">${esc(title)}</div>
      <div class="muted small">${esc([S.model, i.params, i.quant].filter(Boolean).join(' · '))}</div></div>
      <button class="btn sm" id="aboutModels">${t('changeModel')}</button></div>
    <div class="sect">${t('caps')}</div>
    <div class="cap-grid">${CAPS.map((k) => { const yes = caps.includes(k); return `<div class="capitem ${yes ? 'yes' : 'no'}">
      <span class="ic">${icon(k, 16)}</span><div><b>${t('cap_' + k)}</b> <em>${t(yes ? 'capYes' : 'capNo')}</em><small>${t('capd_' + k)}</small></div></div>`; }).join('')}</div>
    <div class="sect">${t('modelSect')}</div>
    <div class="kv">
      <span>${t('diskSize')}</span><b>${i.size ? fmtGB(i.size) + ' ' + t('gb') : '—'}</b>
      <span>${t('ctxLen')}</span><b>${ctx}</b>
      <span>${t('where')}</span><b>${where}</b>
      <span>${t('ollamaVer')}</span><b>${esc(i.version || '—')}</b>
    </div>
    <div class="sect">${t('updates')}</div>
    <div class="mrow"><div class="info"><div class="t">Ollama ${esc(e?.current || i.version || '')}</div><div class="d ${e?.available ? 'warnt' : ''}">${eLine}</div></div>
      ${e?.available ? `<button class="btn sm primary" id="updEngine">${t('update')}</button>` : ''}</div>
    <div class="mrow"><div class="info"><div class="t">${esc(title)}</div><div class="d ${mu?.available ? 'warnt' : ''}">${mLine}</div></div>
      ${mu?.available ? `<button class="btn sm primary" id="updModel">${t('update')}</button>` : ''}</div>
    <div class="row"><button class="btn sm" id="updCheck" ${S.updBusy ? 'disabled' : ''}>${S.updBusy ? t('checking') : t('checkNow')}</button></div>`;
  $('#aboutModels').onclick = () => { $('#aboutModal').hidden = true; openModels(); };
  $('#updCheck').onclick = () => checkUpdates(true);
  if ($('#updEngine')) $('#updEngine').onclick = updateEngine;
  if ($('#updModel')) $('#updModel').onclick = () => updateModel(S.model);
}
// Обновления — тоже изменение модели/движка, поэтому только после подтверждения.
async function updateEngine() {
  const e = S.upd.engine;
  if (!(await confirmDlg(t('cUpdEngineTitle'), t('cUpdEngineText', { latest: e.latest, cur: e.current })))) return;
  startUpdate(null);
}
async function updateModel(id) {
  const m = modelById(id);
  if (!(await confirmDlg(t('cUpdModelTitle'), t('cUpdModelText', { sel: m ? m.title : id })))) return;
  startUpdate(id);
}
async function startUpdate(model) {
  if (S.streaming) S.streaming.abort();
  $('#aboutModal').hidden = true;
  const r = await (await api('/api/update', model ? { model } : {})).json();
  if (r.error) return;
  S.upd = null; watchJob();
}

/* ---------- ваш компьютер ---------- */
function openPc() { S.pathEdit = null; S.pathErr = ''; $('#pcModal').hidden = false; renderPc(); }
function renderPc() {
  $('#pcStats').innerHTML = hwStatsHTML(S.st.hw);
  $('#pcPaths').innerHTML = pathsHTML();
  bindPaths($('#pcPaths'));
  const b = $('#pcRecheck');
  b.disabled = S.pcBusy; b.textContent = S.pcBusy ? t('checking') : t('recheck');
}
async function recheckPc() {
  if (S.pcBusy) return;
  S.pcBusy = true; renderPc();
  try { S.st = await getJSON('/api/state?refresh'); } catch { /* оставляем прежние данные */ }
  S.pcBusy = false; render();
}

/* ---------- полное удаление ---------- */
// Два подтверждения: что удалять (галочки) и «точно?». Удаление моделей и движка — тоже изменение модели, поэтому только через confirmDlg.
async function uninstallAll() {
  const u = await getJSON('/api/uninstall');
  const item = (k, title, info, on = true) => `<label class="${on ? '' : 'off'}"><input type="checkbox" data-u="${k}" ${on ? 'checked' : 'disabled'}>
    <span><b>${title}</b><small>${info}</small></span></label>`;
  const extra = `<div class="uchecks">
    ${item('models', t('uModels'), u.models.count ? t('uModelsInfo', { n: u.models.count, size: fmtGB(u.models.gb), path: esc(u.models.path) }) : t('uModelsNone', { path: esc(u.models.path) }))}
    ${item('engine', t('uEngine'), u.engine.installed ? t('uEngineInfo', { path: esc(u.engine.path) }) : t('uEngineNone'), u.engine.installed)}
    ${item('app', t('uApp'), t('uAppInfo', { path: esc(u.app.data) }) + (u.app.exe ? ' ' + t('uAppExe', { path: esc(u.app.exe) }) : ''))}</div>`;
  const picked = (ex) => [...ex.querySelectorAll('[data-u]:checked')].map((x) => x.dataset.u);
  if (!(await confirmDlg(t('uTitle'), t('uText'), { extra, yes: t('uNext'), no: t('cancel'), danger: true, valid: (ex) => picked(ex).length > 0 }))) return;
  const parts = picked($('#cExtra'));
  const text = t('uSureText', { list: parts.map((p) => t('uL_' + p)).join(', ') }) + (parts.includes('app') ? ' ' + t('uSureApp') : '');
  if (!(await confirmDlg(t('uSureTitle'), text, { yes: t('uYes'), no: t('cancel'), danger: true }))) return;
  if (S.streaming) S.streaming.abort();
  const r = await (await api('/api/uninstall', { parts })).json();
  if (!r.started) return;
  $('#pcModal').hidden = true;
  watchJob();
}
// После удаления программы окно закрывает сервер (/api/quit); в демо и браузере просто остаётся экран «Удалено».
function uninstallDone(j) {
  const app = j.target.includes('app');
  $('#instTitle').textContent = t('uninstalled');
  $('#instNote').textContent = app ? t(S.st.demo ? 'uDoneAppDemo' : 'uDoneApp') : t('uDone');
  if (app) { setTimeout(() => api('/api/quit', {}).catch(() => {}), 2500); return; }
  $('#instActions').innerHTML = `<button class="btn primary" id="backBtn">${t('back')}</button>`;
  $('#backBtn').onclick = async () => {
    S.st = await getJSON('/api/state'); S.statFor = null;
    if (installedIds().length) { ensureModel(); show('chat'); } else show('welcome');
    render();
  };
}

/* ---------- статистика модели в боковой панели ---------- */
async function loadStats() {
  const id = S.model;
  S.statFor = id;
  try { const r = await api('/api/model?name=' + encodeURIComponent(id)); S.stat = r.ok ? await r.json() : { id }; } catch { S.stat = { id }; }
  if (S.model === id && S.view === 'chat') renderSideStats();
}
function renderSideStats() {
  const m = modelById(S.model), i = S.stat?.id === S.model ? S.stat : null, w = i?.where;
  const where = !i ? '…' : w ? t('wshort_' + w.mode) : t('notLoaded');
  // Загруженная модель — фактический контекст из /api/ps, иначе максимальный.
  const ctx = w?.ctx ? fmtNum(w.ctx) : i?.ctx_max ? fmtNum(i.ctx_max) : '—';
  const sp = S.speed[S.model];
  $('#sideStats').title = t('about');
  $('#sideStats').innerHTML = `<div class="ttl" title="${esc(S.model)}">${esc(m ? m.title : S.model)}</div>
    <span>${t('diskSize')}</span><b>${i?.size ? fmtGB(i.size) + ' ' + t('gb') : '—'}</b>
    <span>${t('where')}</span><b>${where}</b>${w && w.mode !== 'cpu' ? `<small>${t('vramPct', { pct: w.vram_pct })}</small>` : ''}
    <span>${t('ctxLen')}</span><b title="${i?.ctx_max ? esc(t('ctxVal', { max: fmtNum(i.ctx_max) })) : ''}">${ctx}</b>
    <span>${t('speed')}</span><b>${sp ? t('tps', { n: fmtNum(sp.toFixed(1)) }) : `<i class="muted">${t('noSpeed')}</i>`}</b>
    <span>Ollama</span><b>${esc(i?.version || '—')}</b>`;
}

/* ---------- картинки ---------- */
// Уменьшаем до 1024 px по длинной стороне: моделям больше не нужно, а история хранится в localStorage.
function shrink(file, max = 1024) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
      g.drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.85).split(',')[1]);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('image')); };
    img.src = url;
  });
}
async function addImages(files) {
  let bad = false;
  for (const f of files) {
    if (!f.type.startsWith('image/')) { bad = true; continue; }
    try { S.pending.push(await shrink(f)); } catch { bad = true; }
  }
  renderAttach(bad ? t('imgErr') : '');
}

/* ---------- текстовые файлы ---------- */
const TEXT_EXTS = ['txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'jsonl', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf', 'log',
  'html', 'htm', 'css', 'scss', 'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'vue', 'py', 'ipynb', 'java', 'kt', 'c', 'h', 'cpp', 'hpp', 'cc',
  'cs', 'go', 'rs', 'rb', 'php', 'swift', 'sql', 'sh', 'bat', 'cmd', 'ps1', 'lua', 'r', 'pl', 'tex', 'srt', 'env', 'gitignore'];
const FILE_MAX_KB = 200, FILES_MAX = 5;   // ~50 тыс. токенов на файл — больше всё равно не влезет в контекст
const isText = (f) => TEXT_EXTS.includes(f.name.split('.').pop().toLowerCase()) || f.type.startsWith('text/');
const fmtKB = (b) => `${fmtNum(Math.max(1, Math.round(b / 1024)))} ${S.lang === 'ru' ? 'КБ' : 'KB'}`;
async function addFiles(files) {
  let err = '';
  for (const f of files) {
    if (S.pendingFiles.length >= FILES_MAX) { err = t('fileMany', { n: FILES_MAX }); break; }
    if (!isText(f)) { err = t('fileType', { name: f.name }); continue; }
    if (f.size > FILE_MAX_KB * 1024) { err = t('fileBig', { name: f.name, max: FILE_MAX_KB }); continue; }
    const text = await f.text().catch(() => null);
    if (text === null || text.includes('\u0000')) { err = t('fileType', { name: f.name }); continue; }
    S.pendingFiles.push({ name: f.name, size: f.size, text });
  }
  renderAttach(err);
}
// Содержимое файлов уходит модели перед текстом сообщения; в пузыре — только чипы с именами.
const withFiles = (m) => {
  const fs = (m.files || []).filter((f) => f.text != null);
  return fs.length ? fs.map((f) => `<file name="${f.name}">\n${f.text}\n</file>`).join('\n\n') + (m.content ? `\n\n${m.content}` : '') : m.content;
};
const fileChip = (f, i) => `<span class="fchip" title="${esc(f.name)}">${icon('file', 14)}<span class="fn">${esc(f.name)}</span><small>${fmtKB(f.size)}</small>${i === undefined ? '' : `<button type="button" data-file="${i}" title="${t('removeImg')}">✕</button>`}</span>`;

function renderAttach(err) {
  const box = $('#attachList');
  box.hidden = !S.pending.length && !S.pendingFiles.length && !err;
  box.innerHTML = S.pending.map((b, i) => `<div class="th"><img src="data:image/jpeg;base64,${b}" alt=""><button type="button" data-img="${i}" title="${t('removeImg')}">✕</button></div>`).join('')
    + S.pendingFiles.map(fileChip).join('')
    + (err ? `<span class="err small">${esc(err)}</span>` : '');
  box.querySelectorAll('[data-img]').forEach((b) => { b.onclick = () => { S.pending.splice(+b.dataset.img, 1); renderAttach(); }; });
  box.querySelectorAll('[data-file]').forEach((b) => { b.onclick = () => { S.pendingFiles.splice(+b.dataset.file, 1); renderAttach(); }; });
}

/* ---------- значки возможностей в поле ввода ---------- */
const canSee = () => capsOf(S.model).includes('vision');
function renderTools(caps) {
  const tools = [['files', caps.includes('text'), 'file'], ['image', caps.includes('vision'), 'image_gen'],
    ['video', false, 'video_gen'], ['think', caps.includes('think'), 'think']];
  $('#compTools').innerHTML = tools.map(([k, ok, ic]) => {
    const on = k === 'think' && ok && S.think;
    const tip = !ok ? t('toolNo_' + k) : k === 'think' ? t(on ? 'tool_thinkOn' : 'tool_thinkOff') : t('tool_' + k, { max: FILE_MAX_KB });
    return `<button type="button" class="tool ${ok ? '' : 'off'} ${on ? 'on' : ''}" data-tool="${k}" aria-disabled="${!ok}"
      ${k === 'think' && ok ? `aria-pressed="${on}"` : ''} title="${esc(tip)}">${icon(ic, 16)}<span>${t('toolL_' + k)}</span></button>`;
  }).join('');
}

/* ---------- чат ---------- */
const curChat = () => S.chats.find((c) => c.id === S.chat);
const saveChats = () => {
  const list = S.chats.slice(0, 50);
  if (!store.set('chats', list)) {
    // Картинки и файлы тяжёлые: при переполнении хранилища убираем их сначала из других чатов, потом отовсюду.
    const strip = (c) => ({ ...c, messages: c.messages.map((m) => {
      if (m.images) m = { ...m, images: undefined, imagesDropped: true };
      if (m.files?.some((f) => f.text != null)) m = { ...m, files: m.files.map((f) => ({ name: f.name, size: f.size })) };
      return m;
    }) });
    if (!store.set('chats', list.map((c) => (c.id === S.chat ? c : strip(c))))) store.set('chats', list.map(strip));
  }
  store.set('chat', S.chat);
};
function newChat() {
  const c = curChat();
  if (c && !c.messages.length) return;
  const n = { id: Date.now().toString(36), title: t('newChat'), messages: [] };
  S.chats.unshift(n); S.chat = n.id; saveChats();
}
function ensureModel() {
  const ids = installedIds();
  if (!ids.includes(S.model)) { S.model = ids[0] || null; store.set('model', S.model); }
}
function renderChat() {
  ensureModel();
  if (!S.model) { show('welcome'); return renderWelcome(); }
  if (!curChat()) newChat();
  const caps = capsOf(S.model);
  renderChip();
  if (S.statFor !== S.model) loadStats();
  renderSideStats();
  renderTools(caps);
  if (!caps.includes('vision') && S.pending.length) { S.pending = []; renderAttach(); }
  $('#chatList').innerHTML = S.chats.map((c) => `<div class="chat-item ${c.id === S.chat ? 'on' : ''}" data-id="${c.id}">
    <span>${esc(c.title)}</span><button title="${t('deleteChat')}" data-del="${c.id}">✕</button></div>`).join('');
  $('#chatList').querySelectorAll('.chat-item').forEach((el) => {
    el.onclick = () => { if (S.streaming) return; S.chat = el.dataset.id; saveChats(); renderChat(); };
  });
  $('#chatList').querySelectorAll('[data-del]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation(); if (S.streaming) return;
      S.chats = S.chats.filter((c) => c.id !== b.dataset.del);
      if (S.chat === b.dataset.del) S.chat = null;
      if (!S.chats.length) newChat(); else if (!S.chat) S.chat = S.chats[0].id;
      saveChats(); renderChat();
    };
  });
  renderMessages();
}
function renderMessages() {
  const c = curChat(), box = $('#messages');
  if (!c.messages.length) {
    box.innerHTML = `<div class="empty"><h2>${t('emptyTitle')}</h2><p>${t('emptyText')}</p>
      <div class="sugg">${['s1', 's2', 's3'].map((k) => `<button data-s="${k}">${t(k)}</button>`).join('')}</div></div>`;
    box.querySelectorAll('[data-s]').forEach((b) => { b.onclick = () => send(t(b.dataset.s)); });
    return;
  }
  box.innerHTML = c.messages.map((m, i) => msgHTML(m, i === c.messages.length - 1 && S.streaming, i >= popFrom)).join('');
  box.scrollTop = box.scrollHeight;
}
function msgHTML(m, live, pop) {
  const cls = pop ? ' pop' : '';
  if (m.role === 'user') {
    const imgs = m.images?.length ? `<div class="imgs">${m.images.map((b) => `<img src="data:image/jpeg;base64,${b}" alt="">`).join('')}</div>`
      : m.imagesDropped ? `<div class="small" style="opacity:.8">[${t('imageMsg')}]</div>` : '';
    const files = m.files?.length ? `<div class="fchips">${m.files.map((f) => fileChip(f)).join('')}</div>` : '';
    return `<div class="msg user${cls}"><div class="bubble">${imgs}${files}${esc(m.content).replace(/\n/g, '<br>')}</div></div>`;
  }
  return `<div class="msg ai${cls}"><div class="avatar">AI</div><div class="bubble"${bubblePh(m, live)}>${bubbleInner(m, live)}</div></div>`;
}
// Фаза анимаций (--ph) — чтобы пересозданные индикаторы не начинали цикл заново.
function bubblePh(m, live) { return live && !m.content && !m.error ? ` style="--ph:-${Date.now() % 3600}ms"` : ''; }
// Содержимое пузыря ответа: во время потока обновляется только оно, сам .msg не пересоздаётся (иначе pop играет на каждый кусок).
function bubbleInner(m, live) {
  const thinkingNow = live && !m.content && !m.error;
  const think = m.thinking ? `<details class="think" ${thinkingNow ? 'open' : ''}><summary>${thinkingNow ? `<span class="dots">${t('thinkingNow')}</span>` : t('thinking')}</summary>${esc(m.thinking).replace(/\n/g, '<br>')}</details>` : '';
  // До первого токена пузырь пуст — показываем, что происходит (загрузка модели в память может идти долго).
  const wait = thinkingNow && !m.thinking ? `<div class="typing"><span class="spin"></span><span class="dots">${t(m.status === 'loading' ? 'loadingModel' : 'waitReply')}</span></div>` : '';
  return `${think}${wait}<div class="md ${live && !wait ? 'cursor' : ''}">${m.error ? `<span class="err">${esc(m.error)}</span>` : md(m.content)}</div>`;
}

/* мини-Markdown: экранирование, затем разметка */
function inline(s) {
  const codes = [];
  s = esc(s).replace(/`([^`\n]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[i]}</code>`);
}
function textBlocks(src) {
  let out = '', list = null, para = [];
  const flush = () => { if (para.length) { out += `<p>${para.join('<br>')}</p>`; para = []; } };
  const close = () => { if (list) { out += `</${list}>`; list = null; } };
  for (const line of src.split('\n')) {
    let m;
    if ((m = line.match(/^(#{1,3})\s+(.*)/))) { flush(); close(); out += `<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`; }
    else if ((m = line.match(/^\s*([-*•]|\d+[.)])\s+(.*)/))) {
      flush(); const tag = /\d/.test(m[1]) ? 'ol' : 'ul';
      if (list !== tag) { close(); out += `<${tag}>`; list = tag; }
      out += `<li>${inline(m[2])}</li>`;
    } else if (!line.trim()) { flush(); close(); }
    else { close(); para.push(inline(line)); }
  }
  flush(); close(); return out;
}
function md(src) {
  return src.split('```').map((p, i) => {
    if (i % 2 === 0) return textBlocks(p);
    const nl = p.indexOf('\n');
    const code = nl === -1 ? p : p.slice(nl + 1);
    return `<div class="codeblock"><button type="button" class="copy">${t('copy')}</button><pre><code>${esc(code.replace(/\n$/, ''))}</code></pre></div>`;
  }).join('');
}

async function send(text) {
  const c = curChat();
  text = (text || '').trim();
  const images = S.pending, files = S.pendingFiles;
  if ((!text && !images.length && !files.length) || S.streaming) return;
  const msg = { role: 'user', content: text };
  if (images.length) msg.images = images;
  if (files.length) msg.files = files;
  c.messages.push(msg);
  if (c.messages.length === 1) c.title = (text || files[0]?.name || t('imageMsg')).slice(0, 40);
  S.pending = []; S.pendingFiles = []; renderAttach();
  const reply = { role: 'assistant', content: '', thinking: '' };
  c.messages.push(reply);
  const ctrl = new AbortController(), model = S.model;
  S.streaming = ctrl; setSendMode(true);
  $('#input').value = ''; autosize();
  popFrom = c.messages.length - 2; renderChat(); popFrom = Infinity;
  const history = c.messages.slice(0, -1).map((m) => (m.images ? { role: m.role, content: withFiles(m), images: m.images } : { role: m.role, content: withFiles(m) }));
  // Перерисовка по таймеру, а не requestAnimationFrame: rAF замирает, если WebView2 считает окно перекрытым.
  let frame = 0;
  const paint = () => { frame = 0; const box = $('#messages'); const near = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    const bub = box.querySelector('.msg.ai:last-child .bubble');
    if (bub) {
      bub.innerHTML = bubbleInner(reply, true);
      if (!reply.content && !reply.error) bub.style.setProperty('--ph', `-${Date.now() % 3600}ms`); else bub.style.removeProperty('--ph');
    }
    if (near) box.scrollTop = box.scrollHeight; };
  try {
    const resp = await api('/api/chat', { model, messages: history, think: S.think }, ctrl.signal);
    const reader = resp.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line) continue;
        const o = JSON.parse(line);
        if (o.error) { reply.error = o.error === 'engine_not_running' ? t('engineDown') : `${t('chatError')}: ${o.error}`; }
        if (o.status) reply.status = o.status;
        const mm = o.message || {};
        if (mm.content) reply.content += mm.content;
        if (mm.thinking) reply.thinking += mm.thinking;
        // Последняя строка потока Ollama: eval_count токенов за eval_duration наносекунд.
        if (o.done && o.eval_count && o.eval_duration) { S.speed[model] = o.eval_count / (o.eval_duration / 1e9); store.set('speed', S.speed); }
        if (!frame) frame = setTimeout(paint, 40);
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') reply.error = `${t('chatError')}: ${e.message}`;
  }
  clearTimeout(frame);
  delete reply.status;
  S.streaming = null; setSendMode(false);
  if (!reply.content && !reply.thinking && !reply.error) c.messages.pop();
  saveChats(); renderChat();
  if (S.model === model) loadStats();
}
function setSendMode(stop) {
  const b = $('#sendBtn');
  b.classList.toggle('stop', stop);
  b.title = stop ? t('stop') : t('send');
  b.innerHTML = stop ? '<svg viewBox="0 0 24 24" width="16" height="16"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>'
    : '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M5 12l14-7-5 14-2-6-7-1z" fill="currentColor"/></svg>';
}
function autosize() { const el = $('#input'); el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 180) + 'px'; }

/* ---------- события ---------- */
$('#composer').onsubmit = (e) => { e.preventDefault(); if (S.streaming) S.streaming.abort(); else send($('#input').value); };
$('#input').addEventListener('input', autosize);
$('#input').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!S.streaming) send($('#input').value); } });
$('#compTools').onclick = (e) => {
  const b = e.target.closest('[data-tool]');
  if (!b || b.classList.contains('off')) return;
  const k = b.dataset.tool;
  if (k === 'files') $('#docInput').click();
  if (k === 'image') $('#fileInput').click();
  if (k === 'think') { S.think = !S.think; store.set('think', S.think); renderTools(capsOf(S.model)); }
};
$('#docInput').accept = TEXT_EXTS.map((x) => '.' + x).join(',');
$('#docInput').onchange = (e) => { addFiles([...e.target.files]); e.target.value = ''; };
$('#newChatBtn').onclick = () => { if (!S.streaming) { newChat(); renderChat(); } };
$('#messages').addEventListener('click', (e) => {
  const b = e.target.closest('.copy'); if (!b) return;
  navigator.clipboard?.writeText(b.parentElement.querySelector('code').textContent);
  b.textContent = t('copied'); setTimeout(() => { b.textContent = t('copy'); }, 1200);
});
$('#modelChip').onclick = openAbout;
$('#aboutClose').onclick = () => { $('#aboutModal').hidden = true; };
$('#aboutModal').onclick = (e) => { if (e.target.id === 'aboutModal') $('#aboutModal').hidden = true; };
$('#fileInput').onchange = (e) => { addImages([...e.target.files]); e.target.value = ''; };
$('#input').addEventListener('paste', (e) => {
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
  if (files.length && canSee()) { e.preventDefault(); addImages(files); }
});
$('.comp-box').addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault(); });
// Перетаскивание: картинки — если модель их понимает, остальное — как текстовые файлы.
$('.comp-box').addEventListener('drop', (e) => {
  const all = [...e.dataTransfer.files];
  if (!all.length) return;
  e.preventDefault();
  const imgs = all.filter((f) => f.type.startsWith('image/'));
  if (imgs.length && !canSee()) renderAttach(t('toolNo_image'));
  else if (imgs.length) addImages(imgs);
  const docs = all.filter((f) => !f.type.startsWith('image/'));
  if (docs.length) addFiles(docs);
});
$('#pickModelBtn').onclick = openModels;
$('#pcBtn').onclick = openPc;
$('#pcRecheck').onclick = recheckPc;
$('#pcUninstall').onclick = uninstallAll;
$('#sideStats').onclick = openAbout;
$('#pcClose').onclick = () => { $('#pcModal').hidden = true; };
$('#pcModal').onclick = (e) => { if (e.target.id === 'pcModal') $('#pcModal').hidden = true; };
$('#modelsClose').onclick = () => { $('#modelsModal').hidden = true; };
$('#modelsModal').onclick = (e) => { if (e.target.id === 'modelsModal') $('#modelsModal').hidden = true; };
$('#helpBtn').onclick = async () => { try { await api('/api/help', {}); } catch { window.open('https://dalink.to/olegche', '_blank'); } };
$('#themeBtn').onclick = () => { S.theme = S.theme === 'dark' ? 'light' : 'dark'; store.set('theme', S.theme); applyTheme(); };
document.querySelectorAll('#langSeg button').forEach((b) => { b.onclick = () => { S.lang = b.dataset.lang; store.set('lang', S.lang); applyLang(); }; });

/* ---------- запуск ---------- */
async function boot() {
  applyTheme(); applyLang(); show('scan');
  setInterval(() => api('/api/ping').catch(() => {}), 4000);
  S.st = await getJSON('/api/state');
  $('#demoBadge').hidden = !S.st.demo;
  const job = await getJSON('/api/job');
  if (job && job.state === 'running') { S.job = job; return watchJob(); }
  if (installedIds().length) { ensureModel(); show('chat'); } else show('welcome');
  render();
  if (installedIds().length) checkUpdates(false);
}
boot().catch((e) => { document.querySelector('#v-scan p').textContent = String(e); });
