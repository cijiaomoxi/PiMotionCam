#!/usr/bin/env python3
"""把项目里的中文文案迁移成 i18n key，并生成 `core/locales/*.json`。

做三件事：
  1. `templates/*.html`：给带中文的元素加 `data-i18n`，带中文的属性加
     `data-i18n-title` / `data-i18n-placeholder` / `data-i18n-alt`；
  2. `static/app.js` 与登录页内联脚本：把中文字符串字面量换成 `t('key')`；
  3. 依据 `tools/i18n_table.py` 生成 zh-CN / en-US 语言包。

查表规则：
  * 先用**原文精确匹配**（含首尾空格）—— 这样 "开始 " 与 "开始" 是两条不同文案；
  * 精确没命中，再按**去空白后**匹配 —— HTML 文本节点两边通常有缩进空白；
  * 两种都没命中就报告出来，人工补表。

匹配策略（JS）：
  * 整个字面量命中 → 整句换成 `t('key')`；
  * 整句没命中 → 按字面量里的中文片段切成 `头 + t('key') + 尾`。

匹配策略（HTML）：
  * 元素内**只有这一段文字**（没有子元素）→ 直接给元素加 `data-i18n`；
  * 元素内还有别的子元素 → 只给这段文字套一层 `<span data-i18n>`。

迁移是幂等的：已经打过标记的文件再次运行不会重复处理。
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from htmltree import parse, RAW_TAGS            # noqa: E402
from i18n_table import EXTRA, HELP, T           # noqa: E402
from jslex import literal_spans                 # noqa: E402

LOCALE_DIR = ROOT / "core" / "locales"

# 汉字 + 中文标点（、。：；，（）「」…… 等）。
# 只认汉字会漏掉「、」这种纯标点的文本节点，英文界面就会残留中文顿号。
CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff01-\uff5e\u2018-\u201d\u2014\u2026]")
# 只在 HTML 属性里做 i18n 标记的属性
I18N_ATTRS = ("title", "placeholder", "alt")

# ----------------------------------------------------------------------
# 需要手工改写的语句：把"中文片段 + 变量 + 中文片段"换成带占位符的整句模板。
# 这些地方英文语序与中文不同，自动切分会产生别扭的句子。
# ----------------------------------------------------------------------
MANUAL_JS = [
    ("toast('区域已保存（' + REGIONS.length + ' 个）', 'ok');",
     "toast(t('toast.regionSaved', { n: REGIONS.length }), 'ok');"),
    ("'</span><span class=\"pc\">' + (RPRE[n] || []).length + ' 个区域</span>' +",
     "'</span><span class=\"pc\">' + t('preset.regionCount', { n: (RPRE[n] || []).length }) + '</span>' +"),
    ("fmt: (v) => v + ' 帧', desc: '连续命中多少帧才判定为移动'",
     "fmt: (v) => v + ' ' + t('algo.framesUnit'), desc: t('algo.consecutiveDesc')"),
    ("'</span><span class=\"pc\">' + Object.keys(p[n] || {}).length + ' 个配置段</span>' +",
     "'</span><span class=\"pc\">' + t('preset.sectionCount', { n: Object.keys(p[n] || {}).length }) + '</span>' +"),
    ("toast('已清理 ' + (r.removed || 0) + ' 个文件', 'ok');",
     "toast(t('toast.purged', { n: r.removed || 0 }), 'ok');"),
    ("? '每 ' + e.interval_minutes + ' 分钟'",
     "? t('sched.every', { n: e.interval_minutes })"),
    ("setText('sc-hint', '正在编辑第 ' + idx + ' 条，保存后覆盖');",
     "setText('sc-hint', t('sched.editing', { n: idx }));"),
    ("text: '确定删除第 ' + idx + ' 条命令？'",
     "text: t('confirm.deleteSched', { n: idx })"),
    ("? ('共发现 ' + cams.length + ' 个摄像头，当前使用：' + camLabel(active))",
     "? (t('cam.foundUsing', { n: cams.length }) + camLabel(active))"),
    ("toast('已转到「' + btn.dataset.goto + '」', 'ok');",
     "toast(t('servo.movedToName', { n: btn.dataset.goto }), 'ok');"),
    ("toast('已载入区域预设「' + name + '」', 'ok');",
     "toast(t('toast.regionPresetLoadedName', { n: name }), 'ok');"),
    ("toast('已激活预设「' + name + '」', 'ok');",
     "toast(t('toast.presetActivatedName', { n: name }), 'ok');"),
    ("text: '确定删除预设「' + name + '」？'",
     "text: t('confirm.deletePresetName', { n: name })"),
    ("text: '确定删除事件「' + id + '」及其录像文件？'",
     "text: t('confirm.deleteEventName', { n: id })"),
    ("toast('已抓拍：' + (r.name || ''), 'ok');",
     "toast(t('toast.snapshotSavedName', { n: r.name || '' }), 'ok');"),
    ("toast('延时摄影已开始（周期 ' + period + 's）', 'ok');",
     "toast(t('toast.tlStartedPeriod', { n: period }), 'ok');"),
    ("text: '确定' + (action === 'start' ? '启动' : action === 'stop' ? '停止' : '重启') + '服务？',",
     "text: t('confirm.serviceAction', { action: action === 'start' ? t('svc.start') "
     ": action === 'stop' ? t('svc.stop') : t('svc.restart') }),"),
    ("async function purge(what, label) {",
     "async function purge(what, labelKey) {\n  const label = t(labelKey);"),
    ("if (!(await modal({ title: '清空' + label, text: '确定删除全部' + label + '？该操作不可恢复。', okText: '删除' }))) return;",
     "if (!(await modal({ title: t('btn.purge') + ' ' + label, "
     "text: t('confirm.purgeWhat', { what: label }), okText: t('btn.delete') }))) return;"),
    ("purge('all', '录像与抓拍'));", "purge('all', 'label.mediaAll'));"),
    ("purge('videos', '录像'));", "purge('videos', 'label.videos'));"),
    ("purge('stills', '抓拍'));", "purge('stills', 'label.stills'));"),
    ("'<td>' + (on ? '启用' : '停用') + '</td>' +",
     "'<td>' + (on ? t('detail.enabled') : t('detail.disabled')) + '</td>' +"),
    ("'<dt>状态</dt><dd>' + (s.enabled ? '启用' : '停用') + '</dd>' +",
     "'<dt>状态</dt><dd>' + (s.enabled ? t('detail.enabled') : t('detail.disabled')) + '</dd>' +"),
    ("' ~ ' + esc(s.pan_max) + '（PIN ' + esc(s.pan_pin) + '）</dd>' +",
     "' ~ ' + esc(s.pan_max) + ' (PIN ' + esc(s.pan_pin) + ')</dd>' +"),
    ("' ~ ' + esc(s.tilt_max) + '（PIN ' + esc(s.tilt_pin) + '）</dd>';",
     "' ~ ' + esc(s.tilt_max) + ' (PIN ' + esc(s.tilt_pin) + ')</dd>';"),
]

MANUAL_LOGIN = [
    ("$('err').textContent = msg || '登录失败';",
     "$('err').textContent = msg || t('err.loginFailed');"),
    ("fail((res.data && res.data.error) || '密码错误');",
     "fail((res.data && res.data.error) || t('err.badPassword'));"),
    (".catch(function () { fail('无法连接服务'); });",
     ".catch(function () { fail(t('err.cannotConnect')); });"),
]

# 上面这些手工替换里用到的 key —— 它们不会经过字面量扫描，
# 单独登记一下，免得被当成"没在源码里出现"的死条目。
MANUAL_KEYS = {
    "toast.regionSaved", "preset.regionCount", "algo.framesUnit",
    "algo.consecutiveDesc", "preset.sectionCount", "toast.purged",
    "sched.every", "sched.editing", "confirm.deleteSched", "cam.foundUsing",
    "servo.movedToName", "toast.regionPresetLoadedName",
    "toast.presetActivatedName", "confirm.deletePresetName",
    "confirm.deleteEventName", "toast.snapshotSavedName",
    "toast.tlStartedPeriod", "confirm.serviceAction", "svc.start",
    "svc.stop", "svc.restart", "btn.purge", "btn.delete", "label.mediaAll",
    "label.videos", "label.stills", "detail.enabled", "detail.disabled",
    "confirm.purgeWhat", "err.loginFailed", "err.badPassword",
    "err.cannotConnect",
}


# ----------------------------------------------------------------------
class Catalog:
    """文案目录：负责查表，并记录每个 key 最终采用的中英文。"""

    def __init__(self, table: dict):
        self.exact: dict[str, tuple[str, str]] = {}
        for raw, (key, en) in table.items():
            self.exact[raw] = (key, en)
        self.norm: dict[str, tuple[str, str]] = {}
        for raw, (key, en) in table.items():
            s = raw.strip()
            if s not in self.norm or raw == s:
                self.norm[s] = (key, en)

        self.used: set[str] = set()
        self.zh: dict[str, str] = {}
        self.en: dict[str, str] = {}
        self.conflicts: list[str] = []

    def lookup_core(self, core: str, lead: str = "", trail: str = ""):
        """按「去空白后的核心词」查表。

        `lead` / `trail` 是核心词在源码里带的空白，用来在多个候选里挑语义
        最贴切的那一条（例如 "开始 " 是事件起始、"开始" 是按钮）。

        返回 (key, en, zh, verbatim)：
          * verbatim=True  —— 源码里的空白和文案自带的空白一致，译文就按
            原样保留（含首尾空格），调用方不要再拆空白；
          * verbatim=False —— 空白对不上，译文取核心词（去首尾空格），
            调用方要把空白留在 t() 调用外面。
        """
        sig = (bool(lead), bool(trail))
        fallback = None
        for raw, (key, en) in self.exact.items():
            if raw.strip() != core:
                continue
            lead_s = raw[:len(raw) - len(raw.lstrip())]
            trail_s = raw[len(raw.rstrip()):]
            if (bool(lead_s), bool(trail_s)) == sig:
                return key, en, raw, True
            if fallback is None:
                fallback = (key, en.strip(), raw.strip(), False)
        if fallback is not None:
            return fallback
        hit = self.norm.get(core)
        if hit is None:
            return None
        key, en, raw = hit
        return key, en.strip(), raw.strip(), False

    def use(self, key: str, zh: str, en: str):
        """登记一次使用；同一 key 取值冲突时以先到的为准并记录。"""
        self.used.add(key)
        if key in self.zh:
            if self.zh[key] != zh or self.en[key] != en:
                self.conflicts.append("%s: %r/%r vs %r/%r"
                                      % (key, self.zh[key], self.en[key], zh, en))
            return
        self.zh[key] = zh
        self.en[key] = en


def _already_applied(new: str, src: str) -> bool:
    """判断一条手工替换是否已经生效过。

    替换后的语句可能又被自动迁移二次改写（例如整句被拆成 t() 调用），
    所以不能直接比对文本——只要替换里用到的 key 都已经在源码里，
    就认为它生效过了。
    """
    if new in src:
        return True
    keys = re.findall(r"t\('([^']+)'", new)
    if not keys:
        return False
    return all(("t('%s'" % k) in src for k in keys)


def cjk_runs(text: str):
    """找出字符串里所有含汉字的非 ASCII 片段。"""
    out = []
    for m in re.finditer(r"[^\x00-\x7f]+", text):
        run = m.group(0)
        if CJK.search(run):
            out.append((m.start(), m.end(), run))
    return out


def js_quote(value: str) -> str:
    """按原样风格重新加引号（并转义换行等）。"""
    esc = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    if "'" in esc and '"' not in esc:
        return '"%s"' % esc
    return "'%s'" % esc.replace("'", "\\'")


def split_ws(value: str):
    """把一段文本拆成 (前导空白, 核心词, 尾部空白)。"""
    lead = value[:len(value) - len(value.lstrip())]
    trail = value[len(value.rstrip()):]
    return lead, value.strip(), trail


def wrap_t(lead: str, key: str, trail: str) -> str:
    """生成 `前导空白 + t('key') + 尾部空白` 的 JS 表达式。"""
    if lead and trail:
        return "%s + t('%s') + %s" % (js_quote(lead), key, js_quote(trail))
    if lead:
        return "%s + t('%s')" % (js_quote(lead), key)
    if trail:
        return "t('%s') + %s" % (key, js_quote(trail))
    return "t('%s')" % key


def transform_js_literals(src: str, cat: Catalog, report: list) -> str:
    """把 JS 源码里的中文字面量换成 t('key') 调用。"""
    spans = literal_spans(src)
    edits = []          # (start, end, new_text)
    for start, end, value in spans:
        if not CJK.search(value):
            continue
        lead, core, trail = split_ws(value)
        hit = cat.lookup_core(core, lead, trail)
        if hit is not None:
            key, en, zh, verbatim = hit
            cat.use(key, zh, en)
            if verbatim:
                edits.append((start, end, "t('%s')" % key))
            else:
                edits.append((start, end, wrap_t(lead, key, trail)))
            continue
        # 整句没命中 → 按中文片段切
        runs = cjk_runs(value)
        pieces = []
        pos = 0
        ok = True
        for a, b, run in runs:
            r_lead, r_core, r_trail = split_ws(run)
            sub = cat.lookup_core(r_core, r_lead, r_trail)
            if sub is None:
                report.append("JS 文案未收录: %r" % value[:80])
                ok = False
                break
            key, en, zh = sub[0], sub[1], sub[2]
            cat.use(key, zh, en)
            pieces.append((value[pos:a], key, value[b:]))
            pos = b
        if not ok:
            continue
        if len(pieces) > 1:
            report.append("JS 多片段字面量(需人工): %r" % value[:80])
            continue
        head, key, tail = pieces[0]
        if not head and not tail:
            new = "t('%s')" % key
        else:
            new = "%s + t('%s') + %s" % (js_quote(head), key, js_quote(tail))
        edits.append((start, end, new))

    for start, end, new in sorted(edits, reverse=True):
        src = src[:start] + new + src[end:]
    return src


def transform_js(src: str, cat: Catalog, report: list):
    for old, new in MANUAL_JS:
        if old not in src:
            if not _already_applied(new, src):
                report.append("JS 手工替换未命中: %s" % old[:70])
            continue
        src = src.replace(old, new, 1)
    return transform_js_literals(src, cat, report)


def transform_html(src: str, cat: Catalog, report: list):
    _root, nodes = parse(src)
    edits = []          # (start, end, new_text)

    for node in nodes:
        if node.name in RAW_TAGS:
            # 内联脚本里的中文字面量也要替换
            if node.name == "script":
                content = src[node.content_start:node.content_end]
                new_content = transform_js_literals(content, cat, report)
                if new_content != content:
                    edits.append((node.content_start, node.content_end, new_content))
            continue
        # --- 属性 ---
        for attr in I18N_ATTRS:
            if "data-i18n-%s" % attr in node.tag_src:
                continue          # 已经打过标，别重复加
            m = re.search(r'(?<![\w-])%s\s*=\s*"([^"]*)"' % attr, node.tag_src)
            if not m:
                continue
            value = m.group(1)
            if not CJK.search(value):
                continue
            hit = cat.lookup_core(value.strip())
            if hit is None:
                report.append("HTML 属性文案未收录: %r" % value[:70])
                continue
            key, en, zh = hit[0], hit[1], hit[2]
            cat.use(key, zh, en)
            pos = node.tag_start + m.start()
            end = node.tag_start + m.end()
            new_attr = '%s="%s" data-i18n-%s="%s"' % (attr, value, attr, key)
            edits.append((pos, end, new_attr))

        # --- 元素文本 ---
        if "data-i18n" in node.tag_src:
            continue
        if len(node.texts) == 1 and not node.has_element_children:
            ts, te = node.texts[0]
            core = src[ts:te].strip()
            if not CJK.search(core):
                continue
            hit = cat.lookup_core(core)
            if hit is None:
                report.append("HTML 文本未收录: %r" % core[:70])
                continue
            key, en, zh = hit[0], hit[1], hit[2]
            cat.use(key, zh, en)
            pos = node.attr_insert_pos()
            edits.append((pos, pos, ' data-i18n="%s"' % key))
            continue

        for ts, te in node.texts:
            raw = src[ts:te]
            lead, core, trail = split_ws(raw)
            if not CJK.search(core):
                continue
            hit = cat.lookup_core(core, lead, trail)
            if hit is None:
                report.append("HTML 文本未收录: %r" % core[:70])
                continue
            key, en, zh = hit[0], hit[1], hit[2]
            cat.use(key, zh, en)
            lead = raw[:len(raw) - len(raw.lstrip())]
            trail = raw[len(raw.rstrip()):]
            edits.append((ts, te, '%s<span data-i18n="%s">%s</span>%s'
                          % (lead, key, core, trail)))

    for start, end, new in sorted(edits, reverse=True):
        src = src[:start] + new + src[end:]
    return src


def transform_login(src: str, cat: Catalog, report: list):
    for old, new in MANUAL_LOGIN:
        if old not in src:
            if not _already_applied(new, src):
                report.append("登录页手工替换未命中: %s" % old[:70])
            continue
        src = src.replace(old, new, 1)
    return transform_html(src, cat, report)


# ----------------------------------------------------------------------
def main() -> int:
    check_only = "--check" in sys.argv
    cat = Catalog(T)
    report: list[str] = []

    files = {
        "templates/index.html": lambda s: transform_html(s, cat, report),
        "templates/login.html": lambda s: transform_login(s, cat, report),
        "static/app.js": lambda s: transform_js(s, cat, report),
    }

    changed = []
    for rel, fn in files.items():
        path = ROOT / rel
        src = io.open(path, encoding="utf-8").read()
        new = fn(src)
        if new != src:
            changed.append(rel)
            if not check_only:
                io.open(path, "w", encoding="utf-8").write(new)

    # 语言包：先铺 T / EXTRA，再叠加实际使用到的取值
    zh, en = {}, {}
    for raw, (key, e) in T.items():
        # 模板类文案（如 "Found {n} webcam(s), currently using: "）自带首尾空格，
        # 那是有意义的分隔符，不能 strip 掉。
        zh.setdefault(key, raw.strip())
        en.setdefault(key, e)
    for key, (z, e) in EXTRA.items():
        zh[key] = z
        en[key] = e
    for key, (z, e) in HELP.items():
        zh[key] = z
        en[key] = e
    for key in sorted(cat.used):
        if key in cat.zh:
            zh[key] = cat.zh[key]
            en[key] = cat.en[key]
        else:
            zh.setdefault(key, key)
            en.setdefault(key, key)

    if not check_only:
        LOCALE_DIR.mkdir(parents=True, exist_ok=True)
        for code, data in (("zh-CN", zh), ("en-US", en)):
            p = LOCALE_DIR / ("%s.json" % code)
            io.open(p, "w", encoding="utf-8").write(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    unused = []
    for raw, (key, _e) in T.items():
        if key not in cat.used and key not in EXTRA and key not in MANUAL_KEYS:
            unused.append((key, raw))

    print("处理文件: %s" % (", ".join(changed) or "（无变化）"))
    print("语言包: %d 条（zh-CN / en-US），实际用到 %d 条"
          % (len(zh), len(cat.used)))
    if report:
        print("\n⚠ 需要人工处理 %d 处:" % len(report))
        for r in report:
            print("   -", r)
    if cat.conflicts:
        print("\n⚠ 同一 key 取值冲突 %d 处:" % len(cat.conflicts))
        for c in cat.conflicts[:20]:
            print("   -", c)
    if unused and changed:
        print("\n⚠ 表里有 %d 条文案没在源码里出现:" % len(unused))
        for k, n in unused[:60]:
            print("   - %-28s %s" % (k, n[:50]))
    elif unused:
        print("\n（源码已是迁移后的状态，未使用的表条目略过）")
    if not report:
        print("\n✅ 无漏网文案")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
