'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function locale(language) {
  const strings = JSON.parse(fs.readFileSync(path.join(__dirname, '../core/locales', language + '.json'), 'utf8'));
  const window = { PKC_I18N: { language, strings, available: [] } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/i18n.js'), 'utf8'), { window });
  return window;
}

test('saved Chinese default names display in English without changing their values', () => {
  const en = locale('en-US');
  const regions = [{ name: '全画面', x: 0, w: 1 }, { name: '区域2', x: .58, w: .13 }];
  const saved = JSON.stringify(regions);
  assert.deepEqual(regions.map(r => en.regionDisplayName(r.name)), ['Full frame', 'Region 2']);
  assert.equal(JSON.stringify(regions), saved);
  assert.equal(en.regionDisplayName('区域003'), 'Region 003');
});

test('generated English names display in Chinese after switching language', () => {
  const zh = locale('zh-CN');
  assert.equal(zh.regionDisplayName('Full frame'), '全画面');
  assert.equal(zh.regionDisplayName('Full screen'), '全画面');
  assert.equal(zh.regionDisplayName('Region 2'), '区域2');
  assert.equal(zh.regionDisplayName('Region3'), '区域3');
});

test('custom names and event-region identifiers are preserved', () => {
  for (const language of ['en-US', 'zh-CN']) {
    const ui = locale(language);
    for (const name of ['池塘入口', 'Camera A', '区域2-北侧', '全画面 自定义', '<script>x</script>', '–', '']) {
      assert.equal(ui.regionDisplayName(name), name);
    }
    assert.equal(ui.regionDisplayName(null), '');
    assert.equal(ui.regionDisplayName(undefined), '');
  }
});

test('both language packs use the new product name and version is 2.8.2', () => {
  for (const language of ['en-US', 'zh-CN']) {
    const ui = locale(language);
    assert.match(ui.t('app.title'), /^PiMotionCam /);
    assert.match(ui.t('app.titleLogin'), /^PiMotionCam /);
    assert.match(ui.t('help.1.body'), /^PiMotionCam /);
  }
  assert.match(fs.readFileSync(path.join(__dirname, '../core/__init__.py'), 'utf8'), /__version__ = "2\.8\.2"/);
});
