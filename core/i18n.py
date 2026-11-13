"""多语言（i18n）支持。

语言包放在 `core/locales/<语言代码>.json`，结构是扁平的
`{"key": "文案"}`。新增一种语言只需要：

1. 复制一份 `core/locales/zh-CN.json` 改成新语言代码，翻译其中的文案；
2. 在本文件的 `LANGUAGES` 里登记一行。

前后端共用同一份语言包：
  * 后端用 `translate()` 翻译自己产生的消息；
  * 前端通过 `GET /api/i18n` 拿到整包，在浏览器端做 key 替换。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent / "locales"

DEFAULT_LANG = "zh-CN"
FALLBACK_LANG = "zh-CN"

# 语言代码 -> {"name": 英文名, "native": 本地语言名}
LANGUAGES: dict[str, dict[str, str]] = {
    "zh-CN": {"name": "Chinese (Simplified)", "native": "简体中文"},
    "en-US": {"name": "English", "native": "English"},
}

# 必须是**可重入**锁：translate() 持锁期间会再调 strings()，
# 用普通 Lock 会自死锁——表现是 POST /api/i18n 传非法语言时请求永不返回，
# 而且这把锁会被一直占着，之后所有用到语言包的接口全部卡死。
_lock = threading.RLock()
_cache: dict[str, dict[str, str]] = {}
# 源码文案 -> key 的反向索引。
#
# 后端代码里写死的是**中文原文**（例如 "需要登录"），所以反向索引必须
# 固定从「源语言」那份语言包里建，不能按目标语言建 —— 否则用中文原文
# 去查英文包的反向索引必然落空。
_reverse: dict[str, str] = {}


# ----------------------------------------------------------------------
def available() -> list[dict]:
    """列出全部可选语言。"""
    return [{"code": code, **meta} for code, meta in LANGUAGES.items()]


def _read(code: str) -> dict[str, str]:
    path = LOCALE_DIR / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}


def strings(code: str) -> dict[str, str]:
    """取某个语言的文案字典；缺键自动用兜底语言补齐。"""
    with _lock:
        if code not in _cache:
            _cache[code] = _read(code)
            if code == FALLBACK_LANG:
                _reverse.update({v: k for k, v in _cache[code].items()})
        base = dict(_cache.get(FALLBACK_LANG) or {})
        base.update(_cache[code])
        return base


def translate(text: str, code: str = DEFAULT_LANG) -> str:
    """把一段中文源文案翻译成目标语言（后端自用）。

    语言包里没有对应条目时原样返回，不会抛异常。
    """
    if not text:
        return text
    with _lock:
        if FALLBACK_LANG not in _cache:
            strings(FALLBACK_LANG)  # 触发加载，顺带建好反向索引
        key = _reverse.get(text)
    if not key:
        return text
    return strings(code).get(key, text)


# ----------------------------------------------------------------------
def _parse_accept_language(header: str) -> list[str]:
    """把 Accept-Language 头解析成按优先级排序的语言代码列表。"""
    out: list[tuple[float, str]] = []
    for part in (header or "").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, params = part.partition(";")
        code = code.strip().lower()
        if not code:
            continue
        q = 1.0
        for p in params.split(";"):
            p = p.strip()
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    q = 1.0
        out.append((q, code))
    out.sort(key=lambda x: -x[0])
    return [c for _, c in out]


def _match(code: str) -> str | None:
    """把浏览器给的语言代码匹配到已登记的语言。"""
    code = (code or "").lower()
    if not code:
        return None
    if code in LANGUAGES:
        return code
    # zh-cn / zh_cn / zh-hans / zh → zh-CN
    primary = code.replace("_", "-").split("-")[0]
    for known in LANGUAGES:
        if known.lower().split("-")[0] == primary:
            return known
    return None


def resolve(configured: str | None = None,
            accept_language: str | None = None) -> str:
    """决定本次请求用哪种语言。

    configured 来自配置 `web.language`：
      * 具体语言代码（zh-CN / en-US）→ 直接用
      * "auto" / 空 → 按浏览器 Accept-Language 自动识别
      * 其它非法值 → 回落到默认语言
    """
    configured = (configured or "auto").strip()
    if configured and configured.lower() != "auto":
        hit = _match(configured)
        if hit:
            return hit
        return DEFAULT_LANG
    for code in _parse_accept_language(accept_language or ""):
        hit = _match(code)
        if hit:
            return hit
    return DEFAULT_LANG
