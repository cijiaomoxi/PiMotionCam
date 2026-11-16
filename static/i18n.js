/* PiMotionCam 多语言运行时
   ------------------------------------------------------------------
   与后端共用 `core/locales/*.json` 同一份文案：
     * 后端在渲染模板时把整包注入 `window.PKC_I18N`；
     * 前端用 `t('key')` 取文案，用 `applyI18n()` 替换静态标记；
     * 切换语言走 `POST /api/i18n` 落库后整页重载，避免局部更新漏项。

   新增一种语言：
     1. 复制 `core/locales/zh-CN.json` 改成新语言代码并翻译；
     2. 在 `core/i18n.py` 的 LANGUAGES 里登记一行。
   前端无需任何改动。 */
(function (global) {
  'use strict';

  var P = global.PKC_I18N || { language: 'zh-CN', available: [], strings: {} };
  var STR = P.strings || {};
  var CURRENT = P.language || 'zh-CN';
  var API = (global.PKC_API_BASE || '').replace(/\/+$/, '');

  /* 取文案；找不到 key 时原样返回 key，便于一眼看出漏配。 */
  function t(key, vars) {
    if (key === null || key === undefined) return '';
    var s = (STR[key] !== undefined && STR[key] !== null) ? String(STR[key]) : String(key);
    if (vars) {
      s = s.replace(/\{(\w+)\}/g, function (m, k) {
        return (vars[k] !== undefined && vars[k] !== null) ? String(vars[k]) : m;
      });
    }
    return s;
  }

  // Saved names identify detection regions. Localize built-in labels only;
  // never rewrite configuration, preset names or user-provided descriptions.
  function regionDisplayName(name) {
    var value = (name === null || name === undefined) ? '' : String(name);
    if (/^(?:全画面|Full frame|Full screen)$/i.test(value)) return t('region.fullFrame');
    var numbered = /^(?:区域\s*|Region\s*)([0-9]+)$/i.exec(value);
    return numbered ? t('region.numberedName', { n: numbered[1] }) : value;
  }

  /* 把静态标记的文案替换掉。
     约定：
       data-i18n             → 替换 textContent
       data-i18n-title       → 替换 title 属性
       data-i18n-placeholder → 替换 placeholder 属性
       data-i18n-alt         → 替换 alt 属性 */
  function applyI18n(root) {
    var scope = root || document;
    var nodes = scope.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute('data-i18n');
      if (!key) continue;
      var val = STR[key];
      if (val === undefined || val === null) continue;
      nodes[i].textContent = val;
    }
    var attrs = ['title', 'placeholder', 'alt'];
    for (var a = 0; a < attrs.length; a++) {
      var attr = attrs[a];
      var list = scope.querySelectorAll('[data-i18n-' + attr + ']');
      for (var j = 0; j < list.length; j++) {
        var k2 = list[j].getAttribute('data-i18n-' + attr);
        if (!k2) continue;
        var v2 = STR[k2];
        if (v2 === undefined || v2 === null) continue;
        list[j].setAttribute(attr, v2);
      }
    }
    document.documentElement.setAttribute('lang', CURRENT);
    var titleEl = document.querySelector('title[data-i18n]');
    if (titleEl) document.title = titleEl.textContent;
  }

  /* 切换语言：写回服务端配置后整页重载。 */
  function setLanguage(code) {
    if (!code || code === CURRENT) return Promise.resolve();
    return fetch(API + '/api/i18n', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: code })
    }).catch(function () { /* 失败也重载，至少回到服务端默认语言 */ })
      .then(function () { global.location.reload(); });
  }

  /* 构建语言下拉框。挂到 id=lang-switch 的容器里。 */
  function mountLangSwitch(containerId) {
    var box = document.getElementById(containerId || 'lang-switch');
    if (!box) return;
    var list = P.available || [];
    if (!list.length) return;
    var sel = document.createElement('select');
    sel.className = 'langsel';
    sel.id = 'lang-select';
    sel.setAttribute('aria-label', 'Language');
    sel.title = 'Language / 语言';
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      var opt = document.createElement('option');
      opt.value = item.code;
      opt.textContent = item.native || item.name || item.code;
      if (item.code === CURRENT) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener('change', function () { setLanguage(sel.value); });
    box.appendChild(sel);
  }

  global.PKC_I18N = P;
  global.t = t;
  global.regionDisplayName = regionDisplayName;
  global.applyI18n = applyI18n;
  global.setLanguage = setLanguage;
  global.mountLangSwitch = mountLangSwitch;
})(window);
