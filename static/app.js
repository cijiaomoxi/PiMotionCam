/* pikrellcam-lite 仪表盘前端
   纯原生实现，无任何外部依赖；所有接口均走 API 基址（默认同源）。
   API 基址可用 window.PKC_API_BASE 覆盖，便于脱离真实后端做联调。 */
'use strict';

const API = (window.PKC_API_BASE || '').replace(/\/+$/, '');
const $ = (id) => document.getElementById(id);

/* =====================================================================
 * 通用工具
 * ===================================================================*/

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = (text === null || text === undefined || text === '') ? '–' : text;
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function bytes(n) {
  n = Number(n) || 0;
  if (n < 1024) return n + ' B';
  const u = ['KB', 'MB', 'GB', 'TB'];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return n.toFixed(n >= 100 ? 0 : 1) + ' ' + u[i];
}

function hhmmss(d) {
  d = d || new Date();
  const p = (v) => String(v).padStart(2, '0');
  return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

function stamp(ts) {
  if (!ts) return '–';
  const d = new Date(Number(ts) * 1000);
  if (isNaN(d.getTime())) return String(ts);
  const p = (v) => String(v).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
    p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}

/* =====================================================================
 * 提示条 / 模态框
 * ===================================================================*/

let toastTimer = null;
function toast(msg, kind) {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'toast show ' + (kind || '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast ' + (kind || ''); }, 2600);
}

/** 通用模态框；带 value 时显示输入框，resolve 输入值，取消时 resolve null。 */
function modal(opts) {
  return new Promise((resolve) => {
    const box = $('modal');
    $('modal-title').textContent = opts.title || t('btn.confirm');
    $('modal-text').textContent = opts.text || '';
    const input = $('modal-input');
    input.classList.toggle('hidden', !opts.withInput);
    input.value = opts.value || '';
    input.placeholder = opts.placeholder || '';
    $('modal-ok').textContent = opts.okText || t('btn.ok');
    box.classList.remove('hidden');

    const done = (val) => {
      box.classList.add('hidden');
      $('modal-ok').removeEventListener('click', onOk);
      $('modal-cancel').removeEventListener('click', onCancel);
      input.removeEventListener('keydown', onKey);
      resolve(val);
    };
    const onOk = () => done(opts.withInput ? input.value.trim() : true);
    const onCancel = () => done(null);
    const onKey = (e) => {
      if (e.key === 'Enter') { e.preventDefault(); onOk(); }
      if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
    };
    $('modal-ok').addEventListener('click', onOk);
    $('modal-cancel').addEventListener('click', onCancel);
    input.addEventListener('keydown', onKey);
    if (opts.withInput) setTimeout(() => { input.focus(); input.select(); }, 30);
  });
}

/* =====================================================================
 * API 层
 * ===================================================================*/

function toLogin() {
  if (location.pathname === '/login') return;
  location.href = '/login';
}

async function api(path, opts) {
  const res = await fetch(API + path, Object.assign({ credentials: 'same-origin' }, opts || {}));
  let data = {};
  try { data = await res.json(); } catch (e) { data = {}; }
  if (res.status === 401 && !/\/api\/auth\//.test(path)) {
    toLogin();
    throw new Error(t('err.loginRequired'));
  }
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

const GET = (p) => api(p);
const POST = (p, body) => api(p, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {})
});
const DEL = (p) => api(p, { method: 'DELETE' });

const MEDIA = (kind, name) => API + '/media/' + kind + '/' + encodeURIComponent(name);

/* =====================================================================
 * 全局状态
 * ===================================================================*/

let ST = null;          // /api/state 快照
let CFG = null;         // /api/config 快照
let REGIONS = [];       // 运动区域（归一化 x,y,w,h）
let RPRE = {};          // 区域预设
let ALGO = { far: null, near: null };
let SCHED_INDEX = null; // 正在编辑的定时命令下标
let LOG_LINES = [];

/* =====================================================================
 * 顶栏 + OSD
 * ===================================================================*/

function renderState(s) {
  ST = s;
  const det = s.detection || {};
  const moving = !!(s.motion || det.motion);
  const sto = s.storage || {};

  const pill = $('status-pill');
  if (!sto.available && sto.reason) {
    // 存储异常比普通状态更紧急：外部存储掉了，用户必须马上知道
    pill.className = 'pill bad';
    pill.textContent = t('storage.paused', { r: sto.reason });
  } else if (s.error) {
    pill.className = 'pill bad';
    pill.textContent = t('err.prefix') + s.error;
  } else if (!s.running) {
    pill.className = 'pill bad';
    pill.textContent = t('state.serviceStopped');
  } else if (!s.camera_ready) {
    pill.className = 'pill warn';
    pill.textContent = t('state.cameraNotReady');
  } else {
    pill.className = 'pill ok';
    pill.textContent = t('state.running');
  }
  renderStorageBadge(sto);

  setText('m-fps', (s.fps || 0).toFixed(1));
  setText('m-dfps', (s.detect_fps || 0).toFixed(1));
  setText('m-events', s.events_total || 0);
  const media = s.media || {};
  // 「磁盘」显示目标文件系统的**真实剩余空间**。
  // 媒体配额（磁盘上限）可以调得比整块盘还大——128 GB 的配额配一块
  // 28.7 GB 的 SD 卡完全合法——这时候配额永远不会触发，
  // 唯一有意义、能预警的数字就是"还剩多少空间"。
  const freeHuman = media.disk_free_human || bytes(media.disk_free_bytes || 0);
  setText('m-disk', t('metric.diskFree') + ' ' + freeHuman);
  const diskTile = $('m-disk');
  if (diskTile && diskTile.parentElement) {
    diskTile.parentElement.className = 'metric' + (media.disk_low ? ' bad' : '');
  }
  // 侦测调参页的实时读数：媒体占用 vs 配额，以及磁盘真实剩余
  setText('rec-diskinfo',
    t('label.diskNow', {
      used: media.disk_used || bytes(media.disk_bytes),
      quota: (media.max_disk_gb || 0) + ' GB',
      free: freeHuman,
      total: media.disk_total_human || '-'
    }));
  setText('m-preset', s.preset || t('state.notSelected'));
  setText('ver', s.version || '–');

  // 循环录像状态跟着 /api/state 一起刷新（每秒一次）
  if (s.loop) {
    LOOP = s.loop;
    if ($('loop-tag')) renderLoop(false);
  }

  // OSD 叠加层
  setText('osd-time', hhmmss());
  const badge = $('osd-badge');
  badge.textContent = moving ? t('state.motion') : t('state.still');
  badge.className = 'badge ' + (moving ? 'hot' : 'idle');
  setText('osd-fps', (s.fps || 0).toFixed(1));
  setText('osd-dfps', (s.detect_fps || 0).toFixed(1));
  setText('osd-events', s.events_total || 0);
  setText('osd-disk', freeHuman);
  setText('osd-algo', det.algorithm || '–');
  setText('osd-region', det.region || '–');
  setText('osd-ratio', ((det.ratio || 0) * 100).toFixed(3) + '%');
  setText('osd-preset', s.preset || t('state.notSelected'));
  const bb = det.bbox;
  setText('osd-bbox', bb && bb.length === 4 ? 'bbox ' + bb.join(',') : '');

  // 按钮状态（以配置中的侦测开关为准，而不是瞬时的移动状态）
  const detEnabled = (CFG && CFG.motion) ? CFG.motion.enabled !== false : true;
  $('btn-motion').textContent = detEnabled ? t('btn.pauseDetect') : t('btn.enableDetect');
  $('btn-recpause').textContent = s.record_paused ? t('btn.resumeRecord') : t('btn.pauseRecord');
  $('btn-svc-start').disabled = !!s.running;
  $('btn-svc-stop').disabled = !s.running;
  $('btn-svc-restart').disabled = !s.running;

  // 命中区域高亮
  renderRegions();
}

async function pollState() {
  try {
    renderState(await GET('/api/state'));
  } catch (e) {
    const pill = $('status-pill');
    pill.className = 'pill bad';
    pill.textContent = t('err.cannotConnect');
  }
}

/* =====================================================================
 * 实时预览 + 运动区域编辑
 * ===================================================================*/

const camwrap = $('camwrap');
const camImg = $('cam');
const overlay = $('overlay');

/** 计算视频内容实际占据的矩形（object-fit: contain 会有黑边）。 */
function contentRect() {
  const ir = camImg.getBoundingClientRect();
  const nw = camImg.naturalWidth, nh = camImg.naturalHeight;
  if (!nw || !nh) return { left: ir.left, top: ir.top, width: ir.width, height: ir.height };
  const scale = Math.min(ir.width / nw, ir.height / nh);
  const w = nw * scale, h = nh * scale;
  return {
    left: ir.left + (ir.width - w) / 2,
    top: ir.top + (ir.height - h) / 2,
    width: w, height: h
  };
}

/** 让叠加层与视频内容像素对齐。 */
function syncOverlay() {
  const cr = contentRect();
  const wr = camwrap.getBoundingClientRect();
  overlay.style.left = (cr.left - wr.left) + 'px';
  overlay.style.top = (cr.top - wr.top) + 'px';
  overlay.style.width = cr.width + 'px';
  overlay.style.height = cr.height + 'px';
}

/* ---- 区域渲染 ---- */

let SEL_REGION = -1;    // 当前选中的区域下标（选中后才可拖动/缩放/双击重命名）

function renderRegions() {
  const box = $('regions');
  const det = (ST && ST.detection) || {};
  const hitRegion = det.region || '';
  box.innerHTML = REGIONS.map((r, i) => {
    const cls = ['region-box'];
    if (!r.enabled) cls.push('off');
    if (r.enabled && r.name === hitRegion && det.motion) cls.push('hit');
    if (i === SEL_REGION) cls.push('sel');
    return '<div class="' + cls.join(' ') + '" data-idx="' + i + '" style="left:' + (r.x * 100) +
      '%;top:' + (r.y * 100) + '%;width:' + (r.w * 100) + '%;height:' + (r.h * 100) + '%">' +
      '<span>' + esc(r.name) + '</span>' +
      '<i class="region-handle" data-idx="' + i + '"></i></div>';
  }).join('');
  renderRegionList();
}

function renderRegionList() {
  setText('region-count', REGIONS.length);
  const box = $('region-list');
  if (!REGIONS.length) {
    box.innerHTML = '<p class="hint">' + t('region.empty') + '</p>';
    return;
  }
  box.innerHTML = REGIONS.map((r, i) =>
    '<div class="rrow' + (i === SEL_REGION ? ' sel' : '') + '" data-idx="' + i + '">' +
    '<input type="checkbox" data-act="toggle" data-idx="' + i + '"' + (r.enabled ? ' checked' : '') + '>' +
    '<span class="nm" title="' + esc(r.name) + '">' + esc(r.name) + '</span>' +
    '<span class="pc">' + Math.round(r.x * 100) + ',' + Math.round(r.y * 100) + ' ' +
    Math.round(r.w * 100) + '×' + Math.round(r.h * 100) + '%</span>' +
    '<button class="sm" data-act="rename" data-idx="' + i + '">' + t('btn.rename') + '</button>' +
    '<button class="sm danger" data-act="del" data-idx="' + i + '">' + t('btn.delete') + '</button>' +
    '</div>').join('');
}

function nextRegionName() {
  let n = REGIONS.length + 1;
  const used = new Set(REGIONS.map((r) => r.name));
  while (used.has(t('region.defaultName') + n)) n++;
  return t('region.defaultName') + n;
}

async function saveRegions() {
  try {
    const r = await POST('/api/regions', { regions: REGIONS });
    REGIONS = r.regions || REGIONS;
    renderRegions();
    toast(t('toast.regionSaved', { n: REGIONS.length }), 'ok');
  } catch (e) {
    toast(t('err.saveRegions') + e.message, 'err');
  }
}

async function renameRegion(i) {
  const v = await modal({
    title: t('region.renameTitle'), text: t('region.renameText'),
    withInput: true, value: REGIONS[i].name, okText: t('btn.save')
  });
  if (v === null) return;
  REGIONS[i].name = v || nextRegionName();
  renderRegions();
  saveRegions();
}

/* ---- 拖拽绘制 / 移动 / 缩放 ---- */

let drag = null;
let lastPointer = null;   // 最近一次指针位置（归一化）

function clamp01(v) { return Math.max(0, Math.min(1, v)); }

function pointerNorm(e) {
  const cr = contentRect();
  return {
    x: clamp01((e.clientX - cr.left) / (cr.width || 1)),
    y: clamp01((e.clientY - cr.top) / (cr.height || 1))
  };
}

camwrap.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  const p = pointerNorm(e);
  const handle = e.target.closest ? e.target.closest('.region-handle') : null;
  const box = e.target.closest ? e.target.closest('.region-box') : null;
  if (handle) {
    drag = { mode: 'resize', idx: +handle.dataset.idx, ox: p.x, oy: p.y, orig: Object.assign({}, REGIONS[+handle.dataset.idx]) };
  } else if (box) {
    drag = { mode: 'move', idx: +box.dataset.idx, ox: p.x, oy: p.y, orig: Object.assign({}, REGIONS[+box.dataset.idx]) };
  } else {
    drag = { mode: 'draw', x0: p.x, y0: p.y };
    showTemp(p.x, p.y, p.x, p.y);
  }
  e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
  const p = pointerNorm(e);
  lastPointer = p;                       // 记录指针位置，供 mouseup 计算新区域
  if (!drag) return;
  if (drag.mode === 'draw') {
    showTemp(drag.x0, drag.y0, p.x, p.y);
  } else if (drag.mode === 'move') {
    const r = REGIONS[drag.idx];
    if (!r) return;
    r.x = clamp01(Math.min(drag.orig.x + (p.x - drag.ox), 1 - drag.orig.w));
    r.y = clamp01(Math.min(drag.orig.y + (p.y - drag.oy), 1 - drag.orig.h));
    renderRegions();
  } else if (drag.mode === 'resize') {
    const r = REGIONS[drag.idx];
    if (!r) return;
    r.w = clamp01(Math.max(0.02, drag.orig.w + (p.x - drag.ox)));
    r.h = clamp01(Math.max(0.02, drag.orig.h + (p.y - drag.oy)));
    if (r.x + r.w > 1) r.w = 1 - r.x;
    if (r.y + r.h > 1) r.h = 1 - r.y;
    renderRegions();
  }
});

document.addEventListener('mouseup', () => {
  if (!drag) return;
  const d = drag;
  drag = null;
  if (d.mode === 'draw') {
    const tmp = document.querySelector('.temp-rect');
    if (tmp) tmp.remove();
    const p = lastPointer;
    if (!p) return;
    const x = Math.min(d.x0, p.x), y = Math.min(d.y0, p.y);
    const w = Math.abs(p.x - d.x0), h = Math.abs(p.y - d.y0);
    if (w < 0.015 || h < 0.015) return;   // 误点击，忽略
    if (REGIONS.length >= 32) { toast(t('err.regionLimit'), 'err'); return; }
    REGIONS.push({ name: nextRegionName(), x: x, y: y, w: w, h: h, enabled: true });
    SEL_REGION = REGIONS.length - 1;   // 选中新区域，方便立即重命名或微调
    renderRegions();
    saveRegions();
    toast(t('toast.regionAdded'), 'ok');
  } else {
    saveRegions();
  }
});

function showTemp(x0, y0, x1, y1) {
  const x = Math.min(x0, x1), y = Math.min(y0, y1);
  const w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
  const surf = $('drawsurface');
  let el = surf.querySelector('.temp-rect');
  if (!el) {
    el = document.createElement('div');
    el.className = 'temp-rect';
    surf.appendChild(el);
  }
  el.style.left = (x * 100) + '%';
  el.style.top = (y * 100) + '%';
  el.style.width = (w * 100) + '%';
  el.style.height = (h * 100) + '%';
}

/* 双击区域框 → 重命名 */
$('regions').addEventListener('dblclick', (e) => {
  const box = e.target.closest ? e.target.closest('.region-box') : null;
  if (box) renameRegion(+box.dataset.idx);
});

/* 区域列表上的操作：点击行选中该区域（选中后才可在画面上拖动/缩放） */
$('region-list').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) {
    const row = e.target.closest('.rrow');
    if (row) { SEL_REGION = (+row.dataset.idx === SEL_REGION) ? -1 : +row.dataset.idx; renderRegions(); }
    return;
  }
  const i = +btn.dataset.idx;
  if (btn.dataset.act === 'rename') renameRegion(i);
  if (btn.dataset.act === 'del') {
    REGIONS.splice(i, 1);
    if (SEL_REGION >= REGIONS.length) SEL_REGION = -1;
    renderRegions();
    saveRegions();
  }
});
$('region-list').addEventListener('change', (e) => {
  const cb = e.target.closest('input[data-act="toggle"]');
  if (!cb) return;
  REGIONS[+cb.dataset.idx].enabled = cb.checked;
  renderRegions();
  saveRegions();
});

$('btn-regions-save').addEventListener('click', saveRegions);

$('btn-region-add').addEventListener('click', () => {
  if (REGIONS.length >= 32) { toast(t('err.regionLimit'), 'err'); return; }
  const nm = $('new-region-name').value.trim() || nextRegionName();
  REGIONS.push({ name: nm, x: 0, y: 0, w: 1, h: 1, enabled: true });
  $('new-region-name').value = '';
  renderRegions();
  saveRegions();
});

/* ---- 区域预设 ---- */

async function loadRegions() {
  try {
    const r = await GET('/api/regions');
    REGIONS = r.regions || [];
    RPRE = r.presets || {};
    renderRegions();
    renderRegionPresets();
  } catch (e) { /* 稍后重试 */ }
}

function renderRegionPresets() {
  const names = Object.keys(RPRE);
  const sel = $('rp-select');
  const cur = sel.value;
  sel.innerHTML = names.length
    ? names.map((n) => '<option value="' + esc(n) + '">' + esc(n) + '</option>').join('')
    : '<option value="">' + t('preset.noneOption') + '</option>';
  if (names.indexOf(cur) >= 0) sel.value = cur;
  $('rp-list').innerHTML = names.length
    ? names.map((n) => '<div class="rrow"><span class="nm">' + esc(n) +
      '</span><span class="pc">' + t('preset.regionCount', { n: (RPRE[n] || []).length }) + '</span>' +
      '<button class="sm" data-rp="' + esc(n) + '">' + t('btn.load') + '</button></div>').join('')
    : '<p class="hint">' + t('regionPreset.empty') + '</p>';
}

$('rp-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-rp]');
  if (!btn) return;
  await activateRegionPreset(btn.dataset.rp);
});

$('btn-rp-save').addEventListener('click', async () => {
  const name = $('rp-name').value.trim();
  if (!name) { toast(t('err.presetNameRequired'), 'err'); return; }
  try {
    await POST('/api/regions/preset', { name: name, regions: REGIONS });
    $('rp-name').value = '';
    await loadRegions();
    toast(t('toast.regionPresetSaved'), 'ok');
  } catch (e) { toast(t('err.saveFailed') + e.message, 'err'); }
});

$('btn-rp-load').addEventListener('click', async () => {
  const name = $('rp-select').value;
  if (!name) { toast(t('err.selectPresetFirst'), 'err'); return; }
  await activateRegionPreset(name);
});

async function activateRegionPreset(name) {
  try {
    const r = await POST('/api/regions/preset/activate', { name: name });
    REGIONS = r.regions || [];
    renderRegions();
    toast(t('toast.regionPresetLoadedName', { n: name }), 'ok');
  } catch (e) { toast(t('err.loadFailed') + e.message, 'err'); }
}

/* =====================================================================
 * 双算法灵敏度
 * ===================================================================*/

const ALGO_META = {
  far: { title: 'far', desc: t('algo.farDesc') },
  near: { title: 'near', desc: t('algo.nearDesc') }
};

const ALGO_PARAMS = [
  {
    key: 'magnitude_limit', label: t('algo.magnitude'), min: 1, max: 80, step: 1,
    fmt: (v) => String(v), desc: t('algo.magnitudeDesc')
  },
  {
    key: 'count_limit', label: t('algo.count'), min: 0.001, max: 0.2, step: 0.001,
    fmt: (v) => (v * 100).toFixed(2) + '%', desc: t('algo.countDesc')
  },
  {
    key: 'consecutive_frames', label: t('algo.consecutive'), min: 1, max: 20, step: 1,
    fmt: (v) => v + ' ' + t('algo.framesUnit'), desc: t('algo.consecutiveDesc')
  },
  {
    key: 'noise_filter', label: t('algo.noise'), min: 0, max: 10, step: 1,
    fmt: (v) => (v === 0 ? t('algo.off') : v + ' px'), desc: t('algo.noiseDesc')
  }
];

function buildAlgoCards() {
  const box = $('algo-box');
  box.innerHTML = ['far', 'near'].map((name) => {
    const m = ALGO_META[name];
    const fields = ALGO_PARAMS.map((p) =>
      '<label class="field"><span>' + p.label + ' <code>' + p.key + '</code><b class="val" id="v-' + name + '-' + p.key + '"></b></span>' +
      '<input type="range" id="a-' + name + '-' + p.key + '" data-algo="' + name + '" data-key="' + p.key + '" ' +
      'min="' + p.min + '" max="' + p.max + '" step="' + p.step + '">' +
      '<small class="hint">' + p.desc + '</small></label>').join('');
    return '<div class="panel" style="margin:0">' +
      '<h2>' + m.title + ' <span class="tag">' + m.desc + '</span>' +
      '<span class="spacer"></span>' +
      '<label class="check"><input type="checkbox" id="a-' + name + '-enabled"> ' + t('common.enable') + '</label></h2>' +
      '<div class="cols">' + fields + '</div></div>';
  }).join('');
}

function fillAlgo() {
  ['far', 'near'].forEach((name) => {
    const a = (ALGO[name] || {});
    const en = $('a-' + name + '-enabled');
    if (en) en.checked = a.enabled !== false;
    ALGO_PARAMS.forEach((p) => {
      const el = $('a-' + name + '-' + p.key);
      if (!el) return;
      const v = Number(a[p.key] !== undefined ? a[p.key] : p.min);
      el.value = v;
      setText('v-' + name + '-' + p.key, p.fmt(v));
    });
  });
}

function collectAlgo() {
  const out = {};
  ['far', 'near'].forEach((name) => {
    const o = {};
    const en = $('a-' + name + '-enabled');
    o.enabled = en ? en.checked : true;
    ALGO_PARAMS.forEach((p) => {
      const el = $('a-' + name + '-' + p.key);
      o[p.key] = el ? Number(el.value) : 0;
    });
    out[name] = o;
  });
  return out;
}

let algoTimer = null;
function scheduleAlgoSave() {
  clearTimeout(algoTimer);
  algoTimer = setTimeout(saveAlgo, 350);
}

async function saveAlgo() {
  const payload = collectAlgo();
  try {
    const r = await POST('/api/algorithms', payload);
    ALGO = r.algorithms || payload;
    fillAlgo();
    setText('algo-hint', t('common.saved'));
    setTimeout(() => setText('algo-hint', ''), 2000);
  } catch (e) { toast(t('err.saveAlgo') + e.message, 'err'); }
}

async function loadAlgo() {
  try {
    ALGO = await GET('/api/algorithms');
    fillAlgo();
  } catch (e) { /* 忽略 */ }
}

/* =====================================================================
 * 配置（录像 / 相机 / 延时 / 侦测开关）
 * ===================================================================*/

const RES_OPTIONS = ['640x480', '1280x720', '1920x1080', '1024x768', '800x600'];
const DET_RES_OPTIONS = ['160x120', '320x240', '640x480', '1280x720'];

function fillSelect(sel, options, value) {
  const v = String(value || '');
  const list = options.indexOf(v) >= 0 ? options : options.concat([v]);
  sel.innerHTML = list.map((o) => '<option value="' + esc(o) + '">' + esc(o) + '</option>').join('');
  sel.value = v;
}

/** 设置滑块的值并同步旁边的数字读数。 */
function setRangeValue(id, vid, v, fmt) {
  const el = $(id);
  if (!el) return;
  el.value = v;
  setText(vid, fmt ? fmt(v) : v);
}

function fillConfig() {
  if (!CFG) return;
  const cam = CFG.camera || {}, rec = CFG.record || {}, tl = CFG.timelapse || {}, mo = CFG.motion || {};

  const setRange = setRangeValue;
  setRange('rec-pre', 'v-rec-pre', rec.pre_seconds, (v) => v + ' s');
  setRange('rec-post', 'v-rec-post', rec.post_seconds, (v) => v + ' s');
  setRange('rec-gap', 'v-rec-gap', rec.event_gap_seconds, (v) => v + ' s');
  setRange('rec-maxev', 'v-rec-maxev', rec.max_event_seconds, (v) => v + ' s');
  setRange('rec-maxdisk', 'v-rec-maxdisk', rec.max_disk_gb, (v) => v + ' GB');
  setRange('rec-minfree', 'v-rec-minfree', rec.min_free_gb, (v) => v + ' GB');
  setRange('rec-quality', 'v-rec-quality', rec.quality, (v) => 'CRF ' + v);
  if ($('rec-encoder')) $('rec-encoder').value = rec.encoder || 'auto';

  setRange('cam-fps', 'v-cam-fps', cam.fps, (v) => v + ' fps');
  setRange('cam-rot', 'v-cam-rot', cam.rotation, (v) => v + '°');
  if ($('cam-flip')) $('cam-flip').value = cam.flip || 'none';
  setRange('cam-detfps', 'v-cam-detfps', cam.detect_fps, (v) => v + ' fps');
  setRange('cam-exp', 'v-cam-exp', cam.exposure, (v) => (v < 0 ? t('common.auto') : v));
  fillSelect($('cam-res'), RES_OPTIONS, (cam.resolution || []).join('x'));
  fillSelect($('cam-detres'), DET_RES_OPTIONS, (cam.detect_resolution || []).join('x'));

  $('cfg-motion-enabled').checked = mo.enabled !== false;
  $('cfg-startup-motion').checked = !!mo.startup_motion;
  $('cfg-tl-enabled').checked = !!tl.enabled;
  $('cfg-tl-hold').checked = !!tl.hold;
  setRange('tl-period', 'v-tl-period', tl.period, (v) => v + ' s');
}

async function loadConfig() {
  try {
    CFG = await GET('/api/config');
    fillConfig();
    renderConfigPresets();
  } catch (e) { /* 忽略 */ }
}

async function saveConfig() {
  const body = {
    record: {
      pre_seconds: +$('rec-pre').value,
      post_seconds: +$('rec-post').value,
      event_gap_seconds: +$('rec-gap').value,
      max_event_seconds: +$('rec-maxev').value,
      max_disk_gb: +$('rec-maxdisk').value,
      min_free_gb: +$('rec-minfree').value,
      encoder: $('rec-encoder').value,
      quality: +$('rec-quality').value
    },
    camera: {
      resolution: $('cam-res').value.split('x').map(Number),
      fps: +$('cam-fps').value,
      rotation: +$('cam-rot').value,
      flip: $('cam-flip').value,
      detect_resolution: $('cam-detres').value.split('x').map(Number),
      detect_fps: +$('cam-detfps').value,
      exposure: +$('cam-exp').value
    },
    timelapse: {
      enabled: $('cfg-tl-enabled').checked,
      period: +$('tl-period').value,
      hold: $('cfg-tl-hold').checked
    },
    motion: {
      startup_motion: $('cfg-startup-motion').checked
    }
  };
  try {
    await POST('/api/config', body);
    setText('cfg-hint', t('toast.configSaved'));
    setTimeout(() => setText('cfg-hint', ''), 2500);
    await loadConfig();
    toast(t('toast.configSaved'), 'ok');
  } catch (e) { toast(t('err.saveConfig') + e.message, 'err'); }
}

/* =====================================================================
 * 成像参数矩阵
 *
 * 控件不是写死在 HTML 里的，而是照着后端 /api/imaging 返回的 schema
 * 现场生成：加一个参数只要改 core/imaging.py 的 SPECS，前后端都不用动。
 * ===================================================================*/
let IMAGING = null;

const IMAGING_GROUP_ORDER = ['tone', 'exposure', 'color'];

function imagingValueText(spec, v) {
  if (spec.type === 'enum') {
    const o = (spec.options || []).find((x) => x.value === v);
    return o ? t(o.label) : String(v);
  }
  if (spec.auto !== undefined && Number(v) === Number(spec.auto)) return t('common.auto');
  return spec.unit ? String(v) + ' ' + spec.unit : String(v);
}

function buildImagingControls() {
  const box = $('imaging-box');
  if (!box || !IMAGING || !IMAGING.schema) return;
  const groups = {};
  IMAGING.schema.forEach((s) => {
    if (!groups[s.group]) groups[s.group] = [];
    groups[s.group].push(s);
  });
  const order = IMAGING_GROUP_ORDER.concat(
    Object.keys(groups).filter((g) => IMAGING_GROUP_ORDER.indexOf(g) < 0));

  let html = '';
  order.forEach((g) => {
    const items = groups[g] || [];
    if (!items.length) return;
    html += '<div class="imgroup"><h3>' + esc(t('imaging.group.' + g)) + '</h3><div class="cols">';
    items.forEach((s) => {
      const id = 'img-' + s.key;
      let ctrl;
      if (s.type === 'enum') {
        ctrl = '<select id="' + id + '">' + s.options.map((o) =>
          '<option value="' + esc(o.value) + '">' + esc(t(o.label)) + '</option>').join('') +
          '</select>';
      } else {
        ctrl = '<input type="range" id="' + id + '" min="' + s.min + '" max="' + s.max +
          '" step="' + s.step + '">';
      }
      html += '<label class="field" data-imgkey="' + esc(s.key) + '"' +
        (s.help ? ' title="' + esc(t(s.help)) + '"' : '') + '>' +
        '<span>' + esc(t(s.label)) + '<b class="val" id="v-' + id + '"></b></span>' +
        ctrl + '</label>';
    });
    html += '</div></div>';
  });
  box.innerHTML = html;
  fillImaging();
  bindImaging();
}

function fillImaging() {
  if (!IMAGING) return;
  const vals = IMAGING.values || {};
  const sup = IMAGING.supported || {};
  (IMAGING.schema || []).forEach((s) => {
    const el = $('img-' + s.key);
    if (!el) return;
    const v = vals[s.key] !== undefined && vals[s.key] !== null ? vals[s.key] : s.default;
    el.value = v;
    setText('v-img-' + s.key, imagingValueText(s, v));
    const wrap = el.closest('[data-imgkey]');
    if (!wrap) return;
    const ok = sup[s.key] !== false;
    wrap.classList.toggle('dim', !ok);
    el.disabled = !ok;
    if (!ok && !wrap.getAttribute('data-unsup')) {
      wrap.setAttribute('data-unsup', '1');
      wrap.title = t('imaging.notSupported');
    }
  });
}

function bindImaging() {
  (IMAGING && IMAGING.schema ? IMAGING.schema : []).forEach((s) => {
    const el = $('img-' + s.key);
    if (!el) return;
    const upd = () => setText('v-img-' + s.key, imagingValueText(s, el.value));
    el.addEventListener('input', upd);
    el.addEventListener('change', upd);
  });
}

function collectImaging() {
  const out = {};
  ((IMAGING && IMAGING.schema) || []).forEach((s) => {
    const el = $('img-' + s.key);
    if (!el) return;
    out[s.key] = s.type === 'enum' ? el.value : Number(el.value);
  });
  return out;
}

async function loadImaging() {
  try {
    IMAGING = await GET('/api/imaging');
    buildImagingControls();
    const b = IMAGING.backend || '';
    const names = {
      rpicam: t('imaging.backendRpicam'),
      libcamera: t('imaging.backendLibcamera'),
      v4l2: t('imaging.backendV4l2')
    };
    setText('imaging-backend', names[b] || b || '–');
    const uns = (IMAGING.unsupported || []).length;
    if (IMAGING.applied === false) {
      setText('imaging-hint', t('imaging.notApplied'));
    } else {
      setText('imaging-hint', uns ? t('imaging.unsupported', { n: uns }) : '');
    }
  } catch (e) { /* 忽略 */ }
}

async function saveImaging() {
  const btn = $('btn-imaging-save');
  if (btn) btn.disabled = true;
  try {
    const r = await POST('/api/imaging', { values: collectImaging() });
    IMAGING = r;
    buildImagingControls();
    setText('imaging-hint', r.message || t('toast.imagingSaved'));
    toast(t('toast.imagingSaved'), 'ok');
    setTimeout(() => setText('imaging-hint', ''), 3000);
  } catch (e) {
    toast(t('err.saveImaging') + e.message, 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function resetImaging() {
  const out = {};
  ((IMAGING && IMAGING.schema) || []).forEach((s) => { out[s.key] = s.default; });
  try {
    const r = await POST('/api/imaging', { values: out });
    IMAGING = r;
    buildImagingControls();
    toast(t('toast.imagingReset'), 'ok');
  } catch (e) {
    toast(t('err.saveImaging') + e.message, 'err');
  }
}

/* =====================================================================
 * 循环录像（loop）
 * ===================================================================*/
let LOOP = null;

function renderLoop(updateSliders) {
  if (!LOOP) return;
  // 录像被暂停时循环录像也不会开段（与上游 pause 语义一致），
  // 面板必须如实说明，否则用户只会觉得开关没生效。
  const paused = !!LOOP.paused;
  const tag = $('loop-tag');
  if (tag) {
    tag.textContent = LOOP.enabled
      ? (LOOP.recording ? t('loop.recording') : (paused ? t('loop.paused') : t('loop.enabled')))
      : t('loop.disabled');
    tag.classList.toggle('warn', !LOOP.enabled || (paused && !LOOP.recording));
  }
  let detail = t('loop.detail', {
    n: LOOP.segments || 0,
    size: bytes(LOOP.bytes || 0),
    limit: bytes(LOOP.limit_bytes || 0)
  });
  if (LOOP.fps) detail += ' · ' + t('loop.fps', { fps: LOOP.fps });
  if (LOOP.enabled && paused && !LOOP.recording) detail += ' · ' + t('loop.pausedHint');
  setText('loop-detail', detail);
  if ($('loop-enabled')) $('loop-enabled').checked = !!LOOP.enabled;
  // 滑块只在真正刷新时同步：每秒轮询 /api/state 也会调这里，
  // 无条件回写会把用户正在拖的滑块弹回去。
  if (updateSliders) {
    setRangeValue('loop-seg', 'v-loop-seg', LOOP.segment_seconds, (v) => v + ' s');
    setRangeValue('loop-pct', 'v-loop-pct', LOOP.max_disk_percent, (v) => v + ' %');
    setRangeValue('loop-q', 'v-loop-q', LOOP.quality, (v) => 'CRF ' + v);
  }
}

async function loadLoop() {
  try {
    LOOP = await GET('/api/loop');
    renderLoop(true);
  } catch (e) { /* 忽略 */ }
}

async function saveLoop() {
  const body = {
    enabled: $('loop-enabled') ? $('loop-enabled').checked : false,
    segment_seconds: +$('loop-seg').value,
    max_disk_percent: +$('loop-pct').value,
    quality: +$('loop-q').value
  };
  try {
    LOOP = await POST('/api/loop', body);
    renderLoop(true);
    toast(t('toast.loopSaved'), 'ok');
  } catch (e) {
    toast(t('err.saveLoop') + e.message, 'err');
  }
}

async function purgeLoop() {
  if (!(await modal({
    title: t('btn.purgeLoop'),
    text: t('confirm.purgeLoop'),
    okText: t('btn.delete')
  }))) return;
  try {
    await POST('/api/purge', { what: 'loop' });
    await loadLoop();
    toast(t('toast.loopPurged'), 'ok');
  } catch (e) {
    toast(t('err.opFailed') + e.message, 'err');
  }
}

/* 配置预设 */
async function loadPresets() {
  try {
    const r = await GET('/api/presets');
    const p = r.presets || {};
    const names = Object.keys(p);
    setText('preset-count', names.length);
    $('preset-list').innerHTML = names.length
      ? names.map((n) => '<div class="rrow"><span class="nm">' + esc(n) +
        '</span><span class="pc">' + t('preset.sectionCount', { n: Object.keys(p[n] || {}).length }) + '</span>' +
        '<button class="sm" data-p="1" data-name="' + esc(n) + '">' + t('btn.activate') + '</button>' +
        '<button class="sm danger" data-p="2" data-name="' + esc(n) + '">' + t('btn.delete') + '</button></div>').join('')
      : '<p class="hint">' + t('preset.empty') + '</p>';
  } catch (e) { /* 忽略 */ }
}

function renderConfigPresets() { loadPresets(); }

$('preset-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-p]');
  if (!btn) return;
  const name = btn.dataset.name;
  if (btn.dataset.p === '1') {
    try {
      await POST('/api/presets/activate', { name: name });
      await loadConfig();
      await loadAlgo();
      await loadRegions();
      toast(t('toast.presetActivatedName', { n: name }), 'ok');
    } catch (err) { toast(t('err.activateFailed') + err.message, 'err'); }
  } else {
    if (!(await modal({ title: t('preset.deleteTitle'), text: t('confirm.deletePresetName', { n: name }), okText: t('btn.delete') }))) return;
    try {
      await DEL('/api/presets/' + encodeURIComponent(name));
      await loadPresets();
      toast(t('toast.presetDeleted'), 'ok');
    } catch (err) { toast(t('err.deleteFailed') + err.message, 'err'); }
  }
});

$('btn-preset-save').addEventListener('click', async () => {
  const name = $('preset-name').value.trim();
  if (!name) { toast(t('err.presetNameRequired'), 'err'); return; }
  if (!CFG) return;
  const payload = {
    camera: CFG.camera, motion: CFG.motion, record: CFG.record,
    timelapse: CFG.timelapse, servo: CFG.servo, media: CFG.media
  };
  try {
    await POST('/api/presets', { name: name, config: payload });
    $('preset-name').value = '';
    await loadPresets();
    toast(t('toast.presetSaved'), 'ok');
  } catch (e) { toast(t('err.savePreset') + e.message, 'err'); }
});

/* =====================================================================
 * 媒体
 * ===================================================================*/

async function loadEvents() {
  const box = $('events');
  try {
    const list = await GET('/api/events');
    setText('event-count', list.length);
    if (!list.length) { box.innerHTML = '<p class="hint">' + t('media.noEvents') + '</p>'; return; }
    box.innerHTML = list.map((e) => {
      const vid = MEDIA('videos', e.video);
      const thumb = e.thumb ? MEDIA('stills', e.thumb) : '';
      const obj = e.thumb_object ? MEDIA('stills', e.thumb_object) : '';
      return '<div class="ev">' +
        '<div class="thumbs">' +
        (thumb ? '<img src="' + esc(thumb) + '" alt="' + t('thumb.alt') + '" loading="lazy">' : '') +
        (obj ? '<img class="obj" src="' + esc(obj) + '" alt="' + t('thumb.cropAlt') + '" loading="lazy">' : '') +
        '</div>' +
        '<div class="meta">' +
        '<div class="t">' + esc(e.id) + '</div>' +
        '<div class="s">' + t('btn.start') + ' ' + stamp(e.start) + ' ' + t('event.duration') + ' ' + (e.duration || 0) + 's · ' +
        bytes(e.size) + ' ' + t('event.frames') + ' ' + (e.frames || 0) + '</div>' +
        '<div class="s">' + t('event.algorithm') + ' ' + esc(e.algorithm || '–') + ' ' + t('event.region') + ' ' + esc(e.region || '–') +
        ' ' + t('event.codec') + ' ' + esc(e.encoder || '–') + '</div>' +
        '<div class="acts">' +
        '<a class="btn sm" style="padding:3px 9px;border:1px solid var(--line-2);border-radius:6px" href="' + esc(vid) +
        '" target="_blank">' + t('btn.play') + '</a>' +
        '<a class="btn sm" style="padding:3px 9px;border:1px solid var(--line-2);border-radius:6px" href="' + esc(vid) +
        '" download="' + esc(e.video) + '">' + t('btn.download') + '</a>' +
        '<button class="sm" data-ev="archive" data-id="' + esc(e.id) + '">' + t('btn.archive') + '</button>' +
        '<button class="sm danger" data-ev="del" data-id="' + esc(e.id) + '">' + t('btn.delete') + '</button>' +
        '</div></div></div>';
    }).join('');
  } catch (e) {
    box.innerHTML = '<p class="hint">' + t('err.eventsLoadFailed') + '' + esc(e.message) + '</p>';
  }
}

$('events').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-ev]');
  if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.ev === 'del') {
    if (!(await modal({ title: t('event.deleteTitle'), text: t('confirm.deleteEventName', { n: id }), okText: t('btn.delete') }))) return;
    try {
      await DEL('/api/events/' + encodeURIComponent(id));
      await loadEvents();
      toast(t('toast.eventDeleted'), 'ok');
    } catch (err) { toast(t('err.deleteFailed') + err.message, 'err'); }
  } else if (btn.dataset.ev === 'archive') {
    try {
      const r = await POST('/api/archive', { id: id });
      toast(t('toast.archivedTo') + ' ' + (r.target || t('common.remote')), 'ok');
    } catch (err) { toast(t('err.archiveFailed') + err.message, 'err'); }
  }
});

async function loadFiles(kind) {
  const box = $(kind === 'videos' ? 'videos' : 'stills');
  try {
    const list = await GET('/api/' + kind);
    setText(kind === 'videos' ? 'video-count' : 'still-count', list.length);
    if (!list.length) { box.innerHTML = '<p class="hint">' + t('media.noFiles') + '</p>'; return; }
    box.innerHTML = list.map((f) => {
      const url = MEDIA(kind, f.name);
      const isVideo = kind === 'videos';
      const thumb = isVideo ? MEDIA('stills', f.name.replace(/\.mp4$/i, '.jpg')) : url;
      return '<div class="file">' +
        '<img src="' + esc(thumb) + '" alt="' + esc(f.name) + '" loading="lazy" ' +
        'onerror="this.outerHTML=\'&lt;div style=&quot;height:84px;display:grid;place-items:center;color:var(--dim);font-size:20px&quot;&gt;▶&lt;/div&gt;\'">' +
        '<div class="fm" title="' + esc(f.name) + '">' + esc(f.name) + '</div>' +
        '<div class="fs">' + esc(f.size_h || bytes(f.size)) + ' · ' + stamp(f.mtime) + '</div>' +
        '<div class="fs"><a href="' + esc(url) + '" target="_blank">' + t('btn.view') + '</a> · ' +
        '<a href="' + esc(url) + '" download="' + esc(f.name) + '">' + t('btn.download') + '</a></div>' +
        '</div>';
    }).join('');
  } catch (e) {
    box.innerHTML = '<p class="hint">' + t('err.listLoadFailed') + '' + esc(e.message) + '</p>';
  }
}

async function loadTimelapse() {
  try {
    const t = await GET('/api/timelapse');
    setText('tl-state', t.running ? (t.hold ? t('tl.runningHold') : t('state.running')) : t('tl.notRunning'));
    setText('tl-detail', t('tl.period') + ' ' + (t.period || 0) + t('tl.taken') + ' ' + (t.index || 0) + ' ' + t('tl.shots') +
      (t.session ? ' ' + t('tl.session') + ' ' + t.session : ''));
    $('btn-tl-hold').textContent = t.hold ? t('btn.cancelHold') : t('btn.hold');
    $('btn-tl-hold').disabled = !t.running;
    $('btn-tl-end').disabled = !t.running;
  } catch (e) { /* 忽略 */ }
}

$('btn-tl-start').addEventListener('click', async () => {
  const period = Math.max(1, parseInt($('tl-start-period').value, 10) || 30);
  try {
    await POST('/api/timelapse', { action: 'start', period: period });
    await loadTimelapse();
    toast(t('toast.tlStartedPeriod', { n: period }), 'ok');
  } catch (e) { toast(t('err.startFailed') + e.message, 'err'); }
});

$('btn-tl-hold').addEventListener('click', async () => {
  const cur = $('btn-tl-hold').textContent === t('btn.cancelHold');
  try {
    await POST('/api/timelapse', { action: 'hold', on: cur });
    await loadTimelapse();
  } catch (e) { toast(t('err.opFailed') + e.message, 'err'); }
});

$('btn-tl-end').addEventListener('click', async () => {
  if (!(await modal({ title: t('btn.endTimelapse'), text: t('confirm.endTimelapse'), okText: t('btn.end') }))) return;
  try {
    const r = await POST('/api/timelapse', { action: 'end' });
    await loadTimelapse();
    toast(t('toast.tlEnded') + (r.video ? t('sep.colon') + r.video : ''), 'ok');
  } catch (e) { toast(t('err.endFailed') + e.message, 'err'); }
});

async function purge(what, labelKey) {
  const label = t(labelKey);
  if (!(await modal({ title: t('btn.purge') + ' ' + label, text: t('confirm.purgeWhat', { what: label }), okText: t('btn.delete') }))) return;
  try {
    const r = await POST('/api/purge', { what: what });
    toast(t('toast.purged', { n: r.removed || 0 }), 'ok');
    await loadEvents(); await loadFiles('videos'); await loadFiles('stills');
  } catch (e) { toast(t('err.purgeFailed') + e.message, 'err'); }
}
$('btn-purge-all').addEventListener('click', () => purge('all', 'label.mediaAll'));
$('btn-purge-videos').addEventListener('click', () => purge('videos', 'label.videos'));
$('btn-purge-stills').addEventListener('click', () => purge('stills', 'label.stills'));

/* =====================================================================
 * 存储位置（USB / 外部存储）
 *
 * 默认策略：外部存储被拔出时**暂停录像**而不是悄悄写回 SD 卡。
 * 写回 SD 卡会在长期运行后把根分区撑满，树莓派直接变砖。
 * ===================================================================*/
let STORAGE = null;

function storageKindLabel(kind) {
  if (kind === 'internal') return t('storage.internal');
  if (kind === 'usb') return t('storage.usb');
  if (kind === 'sdcard') return t('storage.sdcard');
  if (kind === 'external') return t('storage.external');
  return t('storage.unknown');
}

function storageStateLabel(s) {
  if (!s) return '';
  if (!s.available) return t('storage.unavailable');
  if (s.fallback) return t('storage.fallback');
  return t('storage.ok');
}

/** 只刷新存储标签与提示——每秒轮询 /api/state 时用，不触发设备枚举。 */
function renderStorageBadge(s) {
  const sto = s || {};
  const tag = $('storage-tag');
  if (tag) {
    tag.textContent = storageStateLabel(sto);
    tag.className = 'tag' + (sto.available ? (sto.fallback ? ' warn' : ' ok') : ' danger');
  }
  const hint = $('storage-hint');
  if (hint) {
    if (!sto.available && sto.reason) {
      hint.textContent = t('storage.paused', { r: sto.reason });
      hint.className = 'hint warn';
    } else if (sto.fallback && sto.reason) {
      hint.textContent = t('storage.fallbackNote', { r: sto.reason });
      hint.className = 'hint warn';
    } else {
      hint.textContent = '';
      hint.className = 'hint';
    }
  }
}

async function loadStorage() {
  try {
    const r = await GET('/api/storage');
    const s = (r && r.storage) || {};
    STORAGE = s;

    const devs = s.devices || [];
    const cur = s.configured || '';
    const internalPath = s.internal || '';
    // 内置存储一律用"空路径"表示（media.dir 留空 = 用应用目录下 media/），
    // 这样配置里不会留下写死的绝对路径。
    const isInternal = (p) => !p || p === internalPath;

    // 下拉框：内置存储永远排第一，后面跟检测到的外部设备
    const sel = $('storage-dir');
    if (sel) {
      const seen = {};
      const opts = [];
      const push = (value, label) => {
        if (seen[value]) return;
        seen[value] = 1;
        opts.push({ value: value, label: label });
      };
      push('', t('storage.internalOption'));
      devs.forEach((d) => {
        // 内置存储已经用"空路径"这一项代表了，不再重复列出，
        // 否则下拉框里会出现两条含义相同的"内置存储"。
        if (d.kind === 'internal') return;
        push(d.path, d.label + ' · ' + d.path + ' · ' + storageKindLabel(d.kind) +
          ' · ' + (d.free_human || '-') + ' ' + t('storage.free'));
      });
      if (cur && !isInternal(cur)) push(cur, cur);   // 兜底：当前配置一定可选
      sel.innerHTML = opts.map((o) =>
        '<option value="' + esc(o.value) + '">' + esc(o.label) + '</option>').join('');
      sel.value = isInternal(cur) ? '' : cur;
    }

    const rm = $('storage-require-mount');
    if (rm) rm.checked = !!s.require_mount;
    const fb = $('storage-fallback');
    if (fb) fb.checked = !!s.fallback_internal;

    setText('storage-tag', storageStateLabel(s));
    const tag = $('storage-tag');
    if (tag) {
      tag.className = 'tag' + (s.available ? (s.fallback ? ' warn' : ' ok') : ' danger');
    }

    const u = s.usage || {};
    setText('storage-usage', t('storage.usageLine', {
      free: u.free_human || '-',
      total: u.total_human || '-'
    }));

    // 剩余空间低于下限时明确告警（选外置盘时尤其重要：
    // 新目标的剩余空间跟 SD 卡完全是两回事）
    const lowHint = $('storage-low');
    if (lowHint) {
      if (s.disk_low) {
        lowHint.textContent = s.disk_reason || t('storage.lowSpace');
        lowHint.className = 'hint warn';
      } else {
        lowHint.textContent = '';
        lowHint.className = 'hint';
      }
    }

    // 设备明细：每个候选盘都把剩余空间列出来，方便横向比较
    const box = $('storage-devices');
    if (box) {
      box.innerHTML = devs.length ? devs.map((d) => {
        const badge = d.ok
          ? '<span class="tag ok">' + t('storage.ok') + '</span>'
          : '<span class="tag danger">' + esc(d.reason || t('storage.unavailable')) + '</span>';
        const kind = d.kind === 'internal'
          ? t('storage.internal')
          : storageKindLabel(d.kind);
        const space = d.free_human
          ? '<span class="pc">' + esc(d.free_human) + ' / ' + esc(d.total_human || '-') +
            '</span>'
          : '';
        return '<div class="rrow"><span class="nm">' + esc(d.label || d.path) + '</span>' +
          '<span class="pc">' + esc(d.path) + ' · ' + esc(kind) + '</span>' +
          space + badge + '</div>';
      }).join('') : '<p class="hint">' + t('storage.noDevices') + '</p>';
    }

    // 不可用时把原因直接摆在面板上
    const hint = $('storage-hint');
    if (hint) {
      if (!s.available && s.reason) {
        hint.textContent = t('storage.paused', { r: s.reason });
        hint.className = 'hint warn';
      } else if (s.fallback && s.reason) {
        hint.textContent = t('storage.fallbackNote', { r: s.reason });
        hint.className = 'hint warn';
      } else {
        hint.textContent = '';
        hint.className = 'hint';
      }
    }
  } catch (e) { /* 忽略 */ }
}

async function saveStorage() {
  const body = {
    dir: $('storage-dir') ? $('storage-dir').value : '',
    require_mount: $('storage-require-mount') ? $('storage-require-mount').checked : true,
    fallback_internal: $('storage-fallback') ? $('storage-fallback').checked : false
  };
  try {
    const r = await POST('/api/storage', body);
    if (r && r.error) throw new Error(r.error);
    await loadStorage();
    toast(t('toast.storageSaved'), 'ok');
  } catch (e) {
    toast(t('err.storageSaveFailed') + (e.message || ''), 'err');
    await loadStorage();
  }
}

$('btn-storage-apply').addEventListener('click', saveStorage);
$('btn-storage-refresh').addEventListener('click', loadStorage);

/* =====================================================================
 * 定时命令
 * ===================================================================*/

let SCHEDULES = [];

async function loadSchedules() {
  try {
    SCHEDULES = await GET('/api/schedules');
    setText('sc-count', SCHEDULES.length);
    const tb = $('schedules');
    if (!SCHEDULES.length) {
      tb.innerHTML = '<tr><td colspan="6" class="hint">' + t('sched.empty') + '</td></tr>';
      return;
    }
    tb.innerHTML = SCHEDULES.map((e, i) => {
      const idx = (e.index !== undefined && e.index !== null) ? e.index : i;  // 后端未返回 index 时用数组下标
      const when = (e.interval_minutes !== undefined && e.interval_minutes !== null)
        ? t('sched.every', { n: e.interval_minutes })
        : (e.time || '–');
      const on = e.enabled !== false;
      return '<tr><td class="mono">' + idx + '</td>' +
        '<td class="mono">' + esc(e.days || '*') + '</td>' +
        '<td class="mono">' + esc(when) + '</td>' +
        '<td class="mono">' + esc(e.command || '') + '</td>' +
        '<td>' + (on ? t('detail.enabled') : t('detail.disabled')) + '</td>' +
        '<td><div class="acts">' +
        '<button class="sm" data-s="edit" data-pos="' + i + '" data-idx="' + idx + '">' + t('btn.edit') + '</button>' +
        '<button class="sm" data-s="run" data-pos="' + i + '">' + t('btn.runNow') + '</button>' +
        '<button class="sm danger" data-s="del" data-pos="' + i + '" data-idx="' + idx + '">' + t('btn.delete') + '</button>' +
        '</div></td></tr>';
    }).join('');
  } catch (e) {
    $('schedules').innerHTML = '<tr><td colspan="6" class="hint">' + t('err.schedLoadFailed') + '' + esc(e.message) + '</td></tr>';
  }
}

function resetScheduleForm() {
  SCHED_INDEX = null;
  $('sc-days').value = '*';
  $('sc-time').value = '08:00';
  $('sc-interval').value = 0;
  $('sc-command').value = '';
  $('sc-enabled').checked = true;
  setText('sc-hint', '');
}

$('btn-sc-save').addEventListener('click', async () => {
  const cmd = $('sc-command').value.trim();
  if (!cmd) { toast(t('err.cmdEmpty'), 'err'); return; }
  const body = {
    days: $('sc-days').value.trim() || '*',
    command: cmd,
    enabled: $('sc-enabled').checked
  };
  const interval = parseInt($('sc-interval').value, 10) || 0;
  if (interval > 0) body.interval_minutes = interval;
  else body.time = $('sc-time').value || '08:00';
  if (SCHED_INDEX !== null) body.index = SCHED_INDEX;
  try {
    await POST('/api/schedules', body);
    resetScheduleForm();
    await loadSchedules();
    toast(t('toast.schedSaved'), 'ok');
  } catch (e) { toast(t('err.saveFailed') + e.message, 'err'); }
});

$('btn-sc-reset').addEventListener('click', resetScheduleForm);

$('schedules').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-s]');
  if (!btn) return;
  const pos = +btn.dataset.pos;            // 前端列表中的位置（用来取条目）
  const idx = btn.dataset.idx !== undefined ? +btn.dataset.idx : pos;  // 后端下标（删除/覆盖用）
  const ent = SCHEDULES[pos];
  if (!ent) return;
  if (btn.dataset.s === 'edit') {
    SCHED_INDEX = idx;
    $('sc-days').value = ent.days || '*';
    $('sc-time').value = ent.time || '08:00';
    $('sc-interval').value = ent.interval_minutes || 0;
    $('sc-command').value = ent.command || '';
    $('sc-enabled').checked = ent.enabled !== false;
    setText('sc-hint', t('sched.editing', { n: idx }));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else if (btn.dataset.s === 'del') {
    if (!(await modal({ title: t('sched.deleteTitle'), text: t('confirm.deleteSched', { n: idx }), okText: t('btn.delete') }))) return;
    try {
      await DEL('/api/schedules/' + idx);
      await loadSchedules();
      toast(t('toast.deleted'), 'ok');
    } catch (err) { toast(t('err.deleteFailed') + err.message, 'err'); }
  } else if (btn.dataset.s === 'run') {
    try {
      const r = await POST('/api/command', { command: ent.command });
      $('cmd-out').textContent = r.result || t('cmd.noOutput');
      toast(t('toast.cmdExecuted'), 'ok');
    } catch (err) { toast(t('err.execFailed') + err.message, 'err'); }
  }
});

$('btn-cmd-run').addEventListener('click', async () => {
  const cmd = $('cmd-text').value.trim();
  if (!cmd) { toast(t('err.cmdRequired'), 'err'); return; }
  try {
    const r = await POST('/api/command', { command: cmd });
    $('cmd-out').textContent = r.result || t('cmd.noOutput');
    toast(t('toast.cmdExecuted'), 'ok');
  } catch (e) { toast(t('err.execFailed') + e.message, 'err'); }
});

$('btn-sc-reload').addEventListener('click', async () => {
  try {
    await POST('/api/schedules/reload', {});
    await loadSchedules();
    toast(t('toast.schedReloaded'), 'ok');
  } catch (e) { toast(t('err.loadFailed') + e.message, 'err'); }
});

/* =====================================================================
 * 舵机
 * ===================================================================*/

async function loadServo() {
  try {
    const s = await GET('/api/servo');
    setText('servo-tag', (s.enabled ? t('servo.tagEnabled') : t('servo.tagDisabled')) + ' · ' + (s.backend || 'none'));
    const cur = s.current || {};
    $('servo-info').innerHTML =
      '<dt>' + t('detail.backend') + '</dt><dd>' + esc(s.backend || '-') + '</dd>' +
      '<dt>' + t('detail.status') + '</dt><dd>' + (s.enabled ? t('detail.enabled') : t('detail.disabled')) + '</dd>' +
      '<dt>' + t('detail.currentWord') + ' Pan</dt><dd>' + esc(cur.pan === undefined ? '-' : cur.pan) + '</dd>' +
      '<dt>' + t('detail.currentWord') + ' Tilt</dt><dd>' + esc(cur.tilt === undefined ? '-' : cur.tilt) + '</dd>' +
      '<dt>Pan ' + t('detail.limitWord') + '</dt><dd>' + esc(s.pan_min) + ' ~ ' + esc(s.pan_max) + ' (PIN ' + esc(s.pan_pin) + ')</dd>' +
      '<dt>Tilt ' + t('detail.limitWord') + '</dt><dd>' + esc(s.tilt_min) + ' ~ ' + esc(s.tilt_max) + ' (PIN ' + esc(s.tilt_pin) + ')</dd>';
    const pos = s.positions || [];
    setText('pos-count', pos.length);
    $('servo-positions').innerHTML = pos.length
      ? pos.map((p) => '<div class="rrow"><span class="nm">' + esc(p.name) + '</span>' +
        '<span class="pc">pan ' + esc(p.pan) + ' · tilt ' + esc(p.tilt) + '</span>' +
        '<button class="sm" data-goto="' + esc(p.name) + '">' + t('btn.goto') + '</button></div>').join('')
      : '<p class="hint">' + t('servo.noPositionPresets') + '</p>';
    const sp = $('servo-pan'), st = $('servo-tilt');
    if (sp && !sp.dataset.touched) {
      sp.min = s.pan_min; sp.max = s.pan_max;
      if (cur.pan !== undefined && cur.pan !== null) { sp.value = cur.pan; setText('v-servo-pan', cur.pan); }
    }
    if (st && !st.dataset.touched) {
      st.min = s.tilt_min; st.max = s.tilt_max;
      if (cur.tilt !== undefined && cur.tilt !== null) { st.value = cur.tilt; setText('v-servo-tilt', cur.tilt); }
    }
  } catch (e) { /* 忽略 */ }
}

$('servo-positions').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-goto]');
  if (!btn) return;
  try {
    await POST('/api/servo', { action: 'goto', name: btn.dataset.goto });
    toast(t('servo.movedToName', { n: btn.dataset.goto }), 'ok');
    setTimeout(loadServo, 600);
  } catch (err) { toast(t('err.moveFailed') + err.message, 'err'); }
});

$('btn-servo-set').addEventListener('click', async () => {
  try {
    await POST('/api/servo', {
      action: 'set',
      pan: +$('servo-pan').value,
      tilt: +$('servo-tilt').value,
      smooth_ms: +$('servo-smooth').value
    });
    toast(t('toast.servoMoved'), 'ok');
    setTimeout(loadServo, 600);
  } catch (e) { toast(t('err.opFailed') + e.message, 'err'); }
});

$('btn-servo-savepos').addEventListener('click', async () => {
  const name = $('pos-name').value.trim();
  if (!name) { toast(t('err.positionNameRequired'), 'err'); return; }
  try {
    await POST('/api/servo', {
      action: 'save_position', name: name,
      pan: +$('servo-pan').value, tilt: +$('servo-tilt').value
    });
    $('pos-name').value = '';
    await loadServo();
    toast(t('toast.positionSaved'), 'ok');
  } catch (e) { toast(t('err.saveFailed') + e.message, 'err'); }
});

$('btn-servo-enable').addEventListener('click', async () => {
  try {
    await POST('/api/servo', { action: 'enable' });
    await loadServo();
    toast(t('toast.servoEnabled'), 'ok');
  } catch (e) { toast(t('err.enableFailed') + e.message, 'err'); }
});

$('btn-servo-disable').addEventListener('click', async () => {
  try {
    await POST('/api/servo', { action: 'disable' });
    await loadServo();
    toast(t('toast.servoDisabled'), 'ok');
  } catch (e) { toast(t('err.disableFailed') + e.message, 'err'); }
});

/* =====================================================================
 * 系统
 * ===================================================================*/

async function serviceAction(action) {
  if (!(await modal({
    title: t('panel.serviceAction'),
    text: t('confirm.serviceAction', { action: action === 'start' ? t('svc.start') : action === 'stop' ? t('svc.stop') : t('svc.restart') }),
    okText: t('btn.ok')
  }))) return;
  try {
    await POST('/api/service', { action: action });
    toast(t('toast.serviceActionDone'), 'ok');
    setTimeout(pollState, 1200);
  } catch (e) { toast(t('err.opFailed') + e.message, 'err'); }
}
$('btn-svc-start').addEventListener('click', () => serviceAction('start'));
$('btn-svc-stop').addEventListener('click', () => serviceAction('stop'));
$('btn-svc-restart').addEventListener('click', () => serviceAction('restart'));

$('btn-upgrade').addEventListener('click', async () => {
  const ok = await modal({
    title: t('btn.upgrade'),
    text: t('confirm.upgrade'),
    okText: t('btn.startUpgrade')
  });
  if (!ok) return;
  $('up-state').textContent = t('state.upgrading');
  try {
    const r = await POST('/api/upgrade', {});
    $('up-out').textContent = r.output || r.error || '';
    $('up-state').textContent = r.ok ? t('toast.upgradeDone') : t('toast.upgradeFailed');
    toast(r.ok ? t('toast.upgradeDone') : t('toast.upgradeFailed'), r.ok ? 'ok' : 'err');
  } catch (e) {
    $('up-state').textContent = t('toast.upgradeFailed');
    $('up-out').textContent = e.message;
    toast(t('err.upgradeFailed') + e.message, 'err');
  }
});

$('btn-pwd').addEventListener('click', async () => {
  const pwd = $('pwd-input').value;
  try {
    const r = await POST('/api/password', { password: pwd });
    $('pwd-input').value = '';
    setText('pwd-state', r.enabled ? t('pwd.enabled') : t('pwd.turnedOff'));
    toast(r.enabled ? t('pwd.set') : t('pwd.protectionOff'), 'ok');
  } catch (e) { toast(t('err.setFailed') + e.message, 'err'); }
});

const HOOK_KEYS = ['on_motion_begin', 'on_motion_end', 'on_motion_preview_save', 'on_timelapse_end'];

async function loadHooks() {
  try {
    const r = await GET('/api/hooks');
    const h = r.hooks || {};
    HOOK_KEYS.forEach((k) => { if ($('hk-' + k)) $('hk-' + k).value = h[k] || ''; });
    const hist = r.history || [];
    $('hooks-history').innerHTML = hist.length
      ? hist.slice(-12).reverse().map((x) => '<div class="rrow"><span class="nm">' +
        esc(typeof x === 'string' ? x : (x.name || x.event || JSON.stringify(x))) + '</span></div>').join('')
      : '';
  } catch (e) { /* 忽略 */ }
}

$('btn-hooks-save').addEventListener('click', async () => {
  const body = {};
  HOOK_KEYS.forEach((k) => { body[k] = $('hk-' + k) ? $('hk-' + k).value : ''; });
  try {
    await POST('/api/hooks', body);
    setText('hooks-hint', t('toast.hooksSaved'));
    setTimeout(() => setText('hooks-hint', ''), 2500);
    toast(t('toast.hookConfigSaved'), 'ok');
  } catch (e) { toast(t('err.saveFailed') + e.message, 'err'); }
});

async function loadHelp() {
  try {
    const r = await GET('/api/help');
    const secs = r.sections || [];
    $('help').innerHTML = secs.map((s) =>
      '<h3>' + esc(s.title) + '</h3><p>' + esc(s.body) + '</p>').join('');
  } catch (e) { /* 忽略 */ }
}

async function loadSystem() {
  try {
    const s = await GET('/api/system');
    $('sysinfo').innerHTML =
      '<dt>' + t('detail.hostname') + '</dt><dd>' + esc(s.hostname || '-') + '</dd>' +
      '<dt>' + t('detail.model') + '</dt><dd>' + esc(s.model || '-') + '</dd>' +
      '<dt>' + t('detail.platform') + '</dt><dd>' + esc(s.platform || '-') + '</dd>' +
      '<dt>Python</dt><dd>' + esc(s.python || '-') + '</dd>' +
      '<dt>' + t('detail.appDir') + '</dt><dd>' + esc(s.app_dir || '-') + '</dd>' +
      '<dt>' + t('detail.mediaDir') + '</dt><dd>' + esc(s.media_dir || '-') + '</dd>' +
      '<dt>' + t('detail.uptime') + '</dt><dd>' + esc(s.uptime_file || '-') + '</dd>';
  } catch (e) { /* 忽略 */ }
}

/* ---------------------------- 摄像头选择 ---------------------------- */

let CAM_SWITCHING = false;

function camLabel(c) {
  const kind = c.type === 'csi' ? 'CSI' : 'USB';
  const model = (c.model || '').trim() || c.device || c.id || t('cam.unknown');
  const dev = c.type === 'csi' ? ('#' + c.index) : c.device;
  return '[' + kind + '] ' + model + '  (' + dev + ')';
}

function camSelects() {
  return [$('preview-cam-select'), $('cam-select')].filter(Boolean);
}

/* 采集通路（auto / MJPEG / RGB888）选择器，预览页与系统页各一个 */
function fmtSelects() {
  return [$('preview-fmt-select'), $('cam-fmt-select')].filter(Boolean);
}

/* 预览页和系统页共用同一份列表与当前值 */
function fillCamSelects(cams, current, currentFmt) {
  const opts = ['<option value="auto">' + t('cam.auto') + '</option>'];
  cams.forEach((c) => {
    const val = c.type === 'csi' ? String(c.index) : c.device;
    opts.push('<option value="' + esc(val) + '">' + esc(camLabel(c)) + '</option>');
  });
  camSelects().forEach((sel) => {
    sel.innerHTML = opts.join('');
    sel.value = (current && current !== 'auto') ? current : 'auto';
  });
  const f = (currentFmt || 'auto').toUpperCase();
  fmtSelects().forEach((sel) => {
    sel.value = (f === 'AUTO' || f === '') ? 'auto' : f;
  });
}

async function loadCameras() {
  const sels = camSelects();
  if (!sels.length) return;
  try {
    const r = await GET('/api/cameras');
    const cams = r.cameras || [];
    const cur = r.current || 'auto';
    const active = r.active || {};

    fillCamSelects(cams, cur, r.format || 'auto');

    const be = active.backend || '-';
    const beTag = { v4l2: 'USB / V4L2', libcamera: 'CSI / libcamera', rpicam: 'CSI / rpicam-vid' };
    setText('cam-backend-tag', beTag[be] || '-');
    setText('cam-hint', cams.length
      ? (t('cam.foundUsing', { n: cams.length }) + camLabel(active))
      : t('cam.noneFound'));

    const detail = $('cam-detail');
    if (detail) {
      detail.innerHTML =
        '<dt>' + t('detail.backend') + '</dt><dd>' + esc(be) + '</dd>' +
        '<dt>' + t('detail.type') + '</dt><dd>' + esc(active.type || '-') + '</dd>' +
        '<dt>' + t('detail.device') + '</dt><dd>' + esc(active.device || active.id || '-') + '</dd>' +
        '<dt>' + t('detail.model') + '</dt><dd>' + esc(active.model || '-') + '</dd>' +
        '<dt>' + t('detail.format') + '</dt><dd>' + esc(active.format || '-') + '</dd>' +
        '<dt>' + t('detail.resolution') + '</dt><dd>' + esc((active.resolution || []).join('x') || '-') + '</dd>';
    }
  } catch (e) {
    setText('cam-hint', t('err.camListFailed') + e.message);
  }
}

async function applyCamera() {
  if (CAM_SWITCHING) return;
  const sel = $('preview-cam-select') || $('cam-select');
  if (!sel) return;
  const device = sel.value || 'auto';

  // 采集通路：两个选择器取其一，两个页面同步
  const fsel = $('preview-fmt-select') || $('cam-fmt-select');
  const format = fsel ? (fsel.value || 'auto') : 'auto';

  // 同步另一个选择器
  camSelects().forEach((s) => { if (s !== sel) s.value = device; });
  fmtSelects().forEach((s) => { s.value = format; });

  CAM_SWITCHING = true;
  setText('feed-hint', t('cam.switching'));
  try {
    await POST('/api/cameras/select', { device: device, format: format });
    toast(t('cam.switching'), 'info');
    // 采集链路重建需要几秒，等稳定后再刷新列表与恢复提示
    setTimeout(async () => {
      await loadCameras();
      CAM_SWITCHING = false;
      setText('feed-hint', t('hint.dragRegions'));
    }, 3500);
  } catch (e) {
    CAM_SWITCHING = false;
    setText('feed-hint', t('hint.dragRegions'));
    toast(t('err.switchFailed') + e.message, 'err');
  }
}

async function loadReleaseInfo() {
  const box = $('release-info');
  if (!box) return;
  try {
    const r = await GET('/api/release');
    box.innerHTML =
      '<dt>' + t('detail.currentVersion') + '</dt><dd>v' + esc(r.version || '-') + '</dd>' +
      '<dt>' + t('detail.releaseDir') + '</dt><dd>' + esc(r.release || '-') + '</dd>' +
      '<dt>' + t('detail.keptVersions') + '</dt><dd>' + esc((r.releases || []).join(t('sep.list')) || '-') + '</dd>' +
      '<dt>' + t('detail.sharedRoot') + '</dt><dd>' + esc(r.root || '-') + '</dd>';
  } catch (e) { /* 忽略 */ }
}

async function loadLog() {
  try {
    const r = await GET('/api/log');
    const lines = r.lines || [];
    LOG_LINES = lines;
    const box = $('logbox');
    box.innerHTML = lines.map((l) => {
      const t = esc(l);
      const cls = /error|ERROR|Traceback|失败/i.test(l) ? 'lv-e'
        : (/warn|WARN|警告/i.test(l) ? 'lv-w' : (/info|INFO/i.test(l) ? 'lv-i' : ''));
      return '<span class="' + cls + '">' + t + '</span>';
    }).join('\n');
    if ($('log-auto').checked) box.scrollTop = box.scrollHeight;
  } catch (e) { /* 忽略 */ }
}

$('btn-log-clear').addEventListener('click', () => { $('logbox').innerHTML = ''; });

/* =====================================================================
 * 预览区的快捷操作
 * ===================================================================*/

$('btn-motion').addEventListener('click', async () => {
  const detEnabled = (CFG && CFG.motion) ? CFG.motion.enabled !== false : true;
  try {
    await POST('/api/motion', { enabled: !detEnabled });
    await loadConfig();
    await pollState();
    toast(detEnabled ? t('toast.detectPaused') : t('toast.detectEnabled'), 'ok');
  } catch (e) { toast(t('err.opFailed') + e.message, 'err'); }
});

$('btn-recpause').addEventListener('click', async () => {
  const paused = !!(ST && ST.record_paused);
  try {
    await POST('/api/record', { action: paused ? 'resume' : 'pause' });
    await pollState();
    toast(paused ? t('toast.recordResumed') : t('toast.recordPaused'), 'ok');
  } catch (e) { toast(t('err.opFailed') + e.message, 'err'); }
});

$('btn-still').addEventListener('click', async () => {
  try {
    const r = await POST('/api/still', {});
    toast(t('toast.snapshotSavedName', { n: r.name || '' }), 'ok');
    if ($('page-media').classList.contains('active')) loadFiles('stills');
  } catch (e) { toast(t('err.snapshotFailed') + e.message, 'err'); }
});

$('btn-restart').addEventListener('click', async () => {
  if (!(await modal({ title: t('btn.restartService'), text: t('confirm.restart'), okText: t('svc.restart') }))) return;
  try {
    await POST('/api/service', { action: 'restart' });
    toast(t('toast.serviceRestarted'), 'ok');
  } catch (e) { toast(t('err.restartFailed') + e.message, 'err'); }
});

$('btn-refresh').addEventListener('click', () => { pollState(); loadConfig(); loadAlgo(); loadRegions(); loadCameras(); });
$('btn-logout').addEventListener('click', async () => {
  try { await POST('/api/auth/logout', {}); } catch (e) { /* 忽略 */ }
  location.href = '/login';
});

/* =====================================================================
 * 标签页
 * ===================================================================*/

const TAB_LOADERS = {
  preview: () => { loadRegions(); loadConfig(); },
  detect: () => { loadConfig(); loadAlgo(); loadPresets(); loadImaging(); },
  media: () => { loadEvents(); loadFiles('videos'); loadFiles('stills'); loadTimelapse(); loadStorage(); loadLoop(); },
  schedule: () => { loadSchedules(); },
  servo: () => { loadServo(); },
  system: () => { loadHooks(); loadHelp(); loadSystem(); loadLog(); loadCameras(); loadReleaseInfo(); }
};

function showTab(name, updateHash) {
  const btn = document.querySelector('.tab[data-tab="' + name + '"]');
  if (!btn) return;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === btn));
  document.querySelectorAll('.tabpage').forEach((p) => p.classList.toggle('active', p.id === 'page-' + name));
  if (TAB_LOADERS[name]) TAB_LOADERS[name]();
  if (updateHash !== false) {
    try { history.replaceState(null, '', '#' + name); } catch (e) { location.hash = name; }
  }
}

$('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  showTab(btn.dataset.tab);
});

/* =====================================================================
 * 初始化
 * ===================================================================*/

function bindRanges() {
  // 算法滑块：即时显示数值，松开后自动保存
  document.addEventListener('input', (e) => {
    const el = e.target;
    if (!el.dataset) return;
    if (el.dataset.algo) {
      const p = ALGO_PARAMS.find((x) => x.key === el.dataset.key);
      if (p) setText('v-' + el.dataset.algo + '-' + el.dataset.key, p.fmt(Number(el.value)));
    }
  });
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (el.dataset && el.dataset.algo) scheduleAlgoSave();
  });

  // 配置滑块
  const cfgRanges = [
    ['rec-pre', 'v-rec-pre', (v) => v + ' s'],
    ['rec-post', 'v-rec-post', (v) => v + ' s'],
    ['rec-gap', 'v-rec-gap', (v) => v + ' s'],
    ['rec-maxev', 'v-rec-maxev', (v) => v + ' s'],
    ['rec-maxdisk', 'v-rec-maxdisk', (v) => v + ' GB'],
    ['rec-minfree', 'v-rec-minfree', (v) => v + ' GB'],
    ['rec-quality', 'v-rec-quality', (v) => 'CRF ' + v],
    ['cam-fps', 'v-cam-fps', (v) => v + ' fps'],
    ['cam-rot', 'v-cam-rot', (v) => v + '°'],
    ['cam-detfps', 'v-cam-detfps', (v) => v + ' fps'],
    ['cam-exp', 'v-cam-exp', (v) => (v < 0 ? t('common.auto') : v)],
    ['tl-period', 'v-tl-period', (v) => v + ' s'],
    ['loop-seg', 'v-loop-seg', (v) => v + ' s'],
    ['loop-pct', 'v-loop-pct', (v) => v + ' %'],
    ['loop-q', 'v-loop-q', (v) => 'CRF ' + v]
  ];
  cfgRanges.forEach((r) => {
    const el = $(r[0]);
    if (!el) return;
    el.addEventListener('input', () => setText(r[1], r[2](Number(el.value))));
  });

  // 舵机滑块
  [['servo-pan', 'v-servo-pan'], ['servo-tilt', 'v-servo-tilt'], ['servo-smooth', 'v-servo-smooth']].forEach((p) => {
    const el = $(p[0]);
    if (!el) return;
    el.addEventListener('input', () => {
      el.dataset.touched = '1';
      setText(p[1], el.value);
    });
  });
  setText('v-servo-smooth', 0);
}

$('btn-cfg-save').addEventListener('click', saveConfig);

$('btn-cfg-reset').addEventListener('click', async () => {
  if (!(await modal({ title: t('btn.resetConfig'), text: t('confirm.resetConfig'), okText: t('btn.restore') }))) return;
  try {
    await POST('/api/config/reset', {});
    await loadConfig();
    await loadAlgo();
    await loadRegions();
    toast(t('toast.configReset'), 'ok');
  } catch (e) { toast(t('err.resetFailed') + e.message, 'err'); }
});

$('cfg-motion-enabled').addEventListener('change', async (e) => {
  try {
    await POST('/api/motion', { enabled: e.target.checked });
    toast(e.target.checked ? t('toast.detectEnabled') : t('toast.detectPaused'), 'ok');
  } catch (err) { toast(t('err.opFailed') + err.message, 'err'); }
});

async function init() {
  // 先把静态文案换成当前语言，再挂语言切换器
  applyI18n();
  mountLangSwitch();

  buildAlgoCards();
  bindRanges();

  // 视频流
  camImg.src = API + '/video_feed';
  camImg.addEventListener('load', syncOverlay);
  camImg.addEventListener('error', () => setText('feed-hint', t('err.noStream')));
  window.addEventListener('resize', syncOverlay);
  setInterval(syncOverlay, 2000);

  // 鉴权
  try {
    const a = await GET('/api/auth');
    if (a.required && !a.authenticated) { toLogin(); return; }
    $('btn-logout').classList.toggle('hidden', !a.required);
    setText('pwd-state', a.required ? t('pwd.enabled') : t('pwd.disabled'));
  } catch (e) { /* 后续轮询会显示连接状态 */ }

  await loadConfig();
  await loadAlgo();
  await loadRegions();
  await loadPresets();
  await loadCameras();
  await loadImaging();
  await loadLoop();
  await pollState();

  // 支持 #system 之类的锚点直达
  const hash = (location.hash || '').replace('#', '');
  if (hash && document.querySelector('.tab[data-tab="' + hash + '"]')) {
    showTab(hash, false);
  }

  $('btn-cam-apply').addEventListener('click', applyCamera);
  $('btn-cam-refresh').addEventListener('click', loadCameras);
  $('btn-preview-cam').addEventListener('click', applyCamera);
  $('cam-select').addEventListener('change', applyCamera);
  $('preview-cam-select').addEventListener('change', applyCamera);

  $('btn-imaging-save').addEventListener('click', saveImaging);
  $('btn-imaging-reset').addEventListener('click', resetImaging);
  $('btn-loop-save').addEventListener('click', saveLoop);
  $('btn-loop-purge').addEventListener('click', purgeLoop);

  setInterval(pollState, 1000);
  setInterval(loadLog, 1000);
  setInterval(loadTimelapse, 3000);
  setTimeout(loadServo, 500);
}

init();
