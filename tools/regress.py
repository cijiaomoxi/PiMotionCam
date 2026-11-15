#!/usr/bin/env python3
"""pikrellcam-lite 全量 API 回归测试。

对运行中的服务逐个接口做冒烟测试，验证「发布前不该坏的东西都没坏」。
只做**可逆**的操作：所有会改状态的动作都改完立刻改回去；
清空媒体、重启服务、改密码、升级这类有副作用的动作默认跳过，
需要时用 --destructive 打开。

用法：
    python3 tools/regress.py                       # 默认打 127.0.0.1:8080
    python3 tools/regress.py --host pi.local       # 跨机测试
    python3 tools/regress.py --destructive         # 连清空/重启/改密码也测
    python3 tools/regress.py --json                # 输出 JSON 便于机器消费

退出码：0 = 全部通过，1 = 有失败项。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8080"
TIMEOUT = 20

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


# ----------------------------------------------------------------------
def req(method: str, path: str, body=None, raw: bool = False, headers=None,
        limit: int | None = None):
    """发一个请求，返回 (status, payload)。payload 为 dict/bytes/str。

    `limit` 限制读取的字节数——**必须**给流式端点（如 /video_feed）传值，
    否则 read() 会一直等下去，服务是正常的但测试会挂死。
    """
    url = BASE + path
    data = None
    hdrs = {"Accept": "*/*"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=TIMEOUT) as resp:
            raw_bytes = resp.read() if limit is None else resp.read(limit)
            status = resp.status
    except urllib.error.HTTPError as e:
        raw_bytes = e.read()
        status = e.code
    except Exception as e:                       # 连接失败等
        return 0, str(e)
    if raw:
        return status, raw_bytes
    try:
        return status, json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return status, raw_bytes.decode("utf-8", "replace")


def check(name: str, cond: bool, detail: str = ""):
    results.append((name, PASS if cond else FAIL, detail))
    icon = {PASS: "✓", FAIL: "✗", SKIP: "-"}[PASS if cond else FAIL]
    print("  %s %-42s %s" % (icon, name, detail if not cond else ""))
    return cond


def skip(name: str, why: str = ""):
    results.append((name, SKIP, why))
    print("  - %-42s %s" % (name, why))


def get_json(name: str, path: str, want=()):
    st, data = req("GET", path)
    if st != 200:
        return check(name, False, "HTTP %s %s" % (st, str(data)[:90]))
    if want:
        missing = [k for k in want if not isinstance(data, dict) or k not in data]
        if missing:
            return check(name, False, "缺字段 %s" % missing[:5])
    return check(name, True)


# ----------------------------------------------------------------------
def test_pages():
    print("\n[1] 页面与静态资源")
    st, body = req("GET", "/", raw=True)
    html = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    check("GET / 返回 200", st == 200, "HTTP %s" % st)
    check("首页含 data-i18n 标记", 'data-i18n="' in html)
    check("首页注入 window.PKC_I18N", "window.PKC_I18N" in html)
    check("首页引入 i18n.js", "i18n.js" in html)
    check("首页引入 polling.js", "polling.js" in html)
    check("首页含语言切换器容器", 'id="lang-switch"' in html)

    st, body = req("GET", "/static/i18n.js", raw=True)
    check("GET /static/i18n.js", st == 200 and b"applyI18n" in body,
          "HTTP %s" % st)

    st, body = req("GET", "/static/app.js", raw=True)
    check("GET /static/app.js", st == 200 and b"function t(" not in body,
          "HTTP %s" % st)
    st, body = req("GET", "/static/polling.js", raw=True)
    check("GET /static/polling.js", st == 200 and b"createPoller" in body)

    st, body = req("GET", "/snapshot.jpg", raw=True)
    check("GET /snapshot.jpg 返回 JPEG", st == 200 and body[:2] == b"\xff\xd8",
          "HTTP %s" % st)

    # video_feed 是 multipart/x-mixed-replace 无限流，
    # 开头是 boundary 头，真正的 JPEG 魔数在其后——只读开头几百字节。
    st, body = req("GET", "/video_feed", raw=True, limit=512)
    check("GET /video_feed 含 JPEG 帧", st == 200 and b"\xff\xd8\xff" in body,
          "HTTP %s %r" % (st, body[:24]))


def test_reads():
    print("\n[2] 只读接口")
    get_json("GET /api/state", "/api/state", ("camera", "recording", "motion"))
    get_json("GET /api/config", "/api/config", ("camera", "motion", "record", "web"))
    get_json("GET /api/cameras", "/api/cameras")
    get_json("GET /api/algorithms", "/api/algorithms")
    get_json("GET /api/events", "/api/events")
    get_json("GET /api/videos", "/api/videos")
    get_json("GET /api/stills", "/api/stills")
    get_json("GET /api/regions", "/api/regions")
    get_json("GET /api/presets", "/api/presets")
    get_json("GET /api/schedules", "/api/schedules")
    get_json("GET /api/servo", "/api/servo")
    get_json("GET /api/timelapse", "/api/timelapse")
    get_json("GET /api/loop", "/api/loop", ("enabled", "recording", "segments"))
    get_json("GET /api/audio", "/api/audio", ("enabled", "running", "level"))
    get_json("GET /api/imaging", "/api/imaging", ("values", "schema"))
    get_json("GET /api/hooks", "/api/hooks")
    get_json("GET /api/auth", "/api/auth")
    get_json("GET /api/release", "/api/release")
    get_json("GET /api/system", "/api/system")
    st, data = req("GET", "/api/log")
    check("GET /api/log", st == 200, "HTTP %s" % st)


def test_i18n():
    print("\n[3] 多语言")
    st, data = req("GET", "/api/i18n")
    ok = st == 200 and isinstance(data, dict)
    if ok:
        for k in ("language", "available", "strings"):
            if k not in data:
                ok = False
                break
    check("GET /api/i18n 结构完整", ok, "HTTP %s" % st)
    if not ok:
        return
    _, cfg0 = req("GET", "/api/config")
    lang0 = cfg0.get("web", {}).get("language", "auto")
    codes = [a.get("code") for a in data.get("available", [])]
    # 先切到 auto，后面才能验证「按浏览器 Accept-Language 协商」
    req("POST", "/api/i18n", {"language": "auto"})
    check("至少提供 2 门语言", len(codes) >= 2, str(codes))
    check("文案字典非空", len(data.get("strings", {})) > 100,
          "len=%s" % len(data.get("strings", {})))
    zh = data["strings"]

    # Accept-Language 协商
    st, d2 = req("GET", "/api/i18n", headers={"Accept-Language": "en-US,en;q=0.9"})
    check("Accept-Language: en-US → en-US", d2.get("language") == "en-US",
          str(d2.get("language")))
    st, d3 = req("GET", "/api/i18n", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    check("Accept-Language: zh-CN → zh-CN", d3.get("language") == "zh-CN",
          str(d3.get("language")))

    # 帮助内容随语言变化
    st, h_en = req("GET", "/api/help", headers={"Accept-Language": "en-US"})
    st, h_zh = req("GET", "/api/help", headers={"Accept-Language": "zh-CN"})
    en_titles = [s.get("title") for s in h_en.get("sections", [])]
    zh_titles = [s.get("title") for s in h_zh.get("sections", [])]
    check("/api/help 英文内容非空", len(en_titles) > 0)
    check("/api/help 中英文不同", en_titles != zh_titles,
          "%s / %s" % (en_titles[:2], zh_titles[:2]))

    # 切换语言
    st, data = req("POST", "/api/i18n", {"language": "en-US"})
    check("POST /api/i18n → en-US", st == 200 and data.get("language") == "en-US",
          "HTTP %s %s" % (st, str(data)[:80]))
    st, data = req("GET", "/api/i18n")
    check("切换后 GET 返回 en-US", data.get("language") == "en-US",
          str(data.get("language")))

    # 非法语言
    st, data = req("POST", "/api/i18n", {"language": "xx-XX"})
    check("POST /api/i18n 非法语言 → 400", st == 400,
          "HTTP %s %s" % (st, str(data)[:80]))
    # 关键回归点：这条请求曾经因为 i18n 模块的自死锁把服务永久卡住，
    # 所以必须在它之后确认服务还活着。
    st, data = req("GET", "/api/state")
    check("非法语言请求后服务仍可响应", st == 200, "HTTP %s" % st)

    # 还原
    req("POST", "/api/i18n", {"language": lang0 or "auto"})
    st, data = req("GET", "/api/config")
    check("语言已还原", data.get("web", {}).get("language") == lang0)


def test_writes():
    print("\n[4] 可逆写操作")
    # --- 侦测算法参数：读出来，改成一样的，再写回去 ---
    st, algo = req("GET", "/api/algorithms")
    if st == 200 and isinstance(algo, dict):
        payload = {"far": algo.get("far"), "near": algo.get("near")}
        st, r = req("POST", "/api/algorithms", payload)
        check("POST /api/algorithms（写回原值）", st == 200, "HTTP %s %s" % (st, str(r)[:70]))
    else:
        skip("POST /api/algorithms", "GET 失败")

    # --- 运动侦测开关：关再开 ---
    st, state = req("GET", "/api/config")
    was = state.get("motion", {}).get("enabled") if isinstance(state, dict) else None
    if isinstance(was, bool):
        st, r = req("POST", "/api/motion", {"enabled": not was})
        check("POST /api/motion 切换开关", st == 200, "HTTP %s" % st)
        st, r = req("POST", "/api/motion", {"enabled": was})
        check("POST /api/motion 还原", st == 200, "HTTP %s" % st)
    else:
        skip("POST /api/motion", "读不到 motion.enabled")

    # --- 区域：原样保存 ---
    st, regions = req("GET", "/api/regions")
    if st == 200 and isinstance(regions, dict):
        payload = regions.get("regions", regions)
        st, r = req("POST", "/api/regions", {"regions": payload})
        check("POST /api/regions（原样保存）", st == 200, "HTTP %s %s" % (st, str(r)[:70]))
    else:
        skip("POST /api/regions", "GET 失败")

    # --- 配置：原样写回 ---
    st, cfg = req("GET", "/api/config")
    if st == 200 and isinstance(cfg, dict):
        body = {k: v for k, v in cfg.items() if isinstance(v, dict)}
        st, r = req("POST", "/api/config", body)
        check("POST /api/config（原样写回）", st == 200, "HTTP %s %s" % (st, str(r)[:70]))
    else:
        skip("POST /api/config", "GET 失败")

    # --- 录像开关 ---
    st, r = req("POST", "/api/record", {"action": "on"})
    check("POST /api/record on", st == 200, "HTTP %s" % st)
    st, r = req("POST", "/api/record", {"action": "off"})
    check("POST /api/record off", st == 200, "HTTP %s" % st)
    req("POST", "/api/record", {"action": "off" if cfg.get("record", {}).get("paused") else "on"})

    # --- 抓拍 ---
    st, r = req("POST", "/api/still")
    check("POST /api/still", st == 200, "HTTP %s %s" % (st, str(r)[:70]))

    # --- 预设：建一个再删掉 ---
    tmp = "__regress_tmp__"
    st, r = req("POST", "/api/presets", {"name": tmp})
    ok_create = st == 200
    check("POST /api/presets（建临时预设）", ok_create, "HTTP %s %s" % (st, str(r)[:70]))
    if ok_create:
        st, r = req("DELETE", "/api/presets/" + tmp)
        check("DELETE /api/presets（删临时预设）", st == 200, "HTTP %s" % st)
        # 只看返回码不够：曾经出现「接口返回 ok 但配置里还在」的缺陷
        st, lst = req("GET", "/api/presets")
        names = list(lst.keys()) if isinstance(lst, dict) else \
            [x.get("name") for x in lst if isinstance(x, dict)] if isinstance(lst, list) else []
        check("删除后预设确实不存在", tmp not in names, str(names))
    else:
        skip("DELETE /api/presets", "创建失败")

    # --- 区域预设：建一个再删掉 ---
    st, r = req("POST", "/api/regions/preset", {"name": tmp})
    ok_create = st == 200
    check("POST /api/regions/preset（建临时预设）", ok_create,
          "HTTP %s %s" % (st, str(r)[:70]))
    if ok_create:
        st, r = req("DELETE", "/api/regions/preset/" + tmp)
        check("DELETE /api/regions/preset", st == 200, "HTTP %s" % st)
        st, rg = req("GET", "/api/regions")
        names = list((rg.get("presets") or {}).keys()) if isinstance(rg, dict) else []
        check("删除后区域预设确实不存在", tmp not in names, str(names))
    else:
        skip("DELETE /api/regions/preset", "创建失败")

    # --- 定时命令：建一条再删掉 ---
    st, r = req("POST", "/api/schedules",
                {"weekday": "*", "time": "03:00", "command": "echo regress"})
    ok_create = st == 200
    check("POST /api/schedules（建临时命令）", ok_create, "HTTP %s %s" % (st, str(r)[:70]))
    if ok_create:
        st, lst = req("GET", "/api/schedules")
        items = lst if isinstance(lst, list) else lst.get("commands", []) if isinstance(lst, dict) else []
        # 该路由声明为 <int:index>，只接受数字下标（uid 走 HTTP 会 404）
        idx = None
        for it in items:
            if isinstance(it, dict) and it.get("command") == "echo regress":
                idx = it.get("index")
                break
        if idx is not None:
            st, r = req("DELETE", "/api/schedules/%s" % idx)
            check("DELETE /api/schedules（删临时命令）", st == 200, "HTTP %s" % st)
        else:
            skip("DELETE /api/schedules", "找不到刚建的命令")
    else:
        skip("DELETE /api/schedules", "创建失败")

    st, r = req("POST", "/api/schedules/reload")
    check("POST /api/schedules/reload", st == 200, "HTTP %s" % st)

    # --- 内部命令 ---
    st, r = req("POST", "/api/command", {"command": "echo regress"})
    check("POST /api/command", st == 200, "HTTP %s %s" % (st, str(r)[:70]))

    # --- 舵机：只读状态，不下发转动 ---
    st, r = req("GET", "/api/servo")
    check("GET /api/servo（不下发转动）", st == 200, "HTTP %s" % st)

    # --- 事件钩子：原样写回 ---
    st, hooks = req("GET", "/api/hooks")
    if st == 200 and isinstance(hooks, dict):
        st, r = req("POST", "/api/hooks", hooks)
        check("POST /api/hooks（原样写回）", st == 200, "HTTP %s %s" % (st, str(r)[:70]))
    else:
        skip("POST /api/hooks", "GET 失败")


def test_destructive():
    print("\n[5] 有副作用的操作（--destructive）")
    st, r = req("POST", "/api/service", {"action": "restart"})
    check("POST /api/service restart", st == 200, "HTTP %s" % st)
    time.sleep(6)
    st, _ = req("GET", "/api/state")
    check("重启后服务恢复", st == 200, "HTTP %s" % st)

    st, r = req("POST", "/api/purge", {"what": "stills"})
    check("POST /api/purge（清空抓拍）", st == 200, "HTTP %s" % st)


# ----------------------------------------------------------------------
def main() -> int:
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="8080")
    ap.add_argument("--destructive", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    BASE = "http://%s:%s" % (args.host, args.port)

    print("=" * 66)
    print("pikrellcam-lite 回归测试  →  %s" % BASE)
    print("=" * 66)

    st, _ = req("GET", "/api/state")
    if st != 200:
        print("服务不可达（HTTP %s），先启动服务再跑回归。" % st)
        return 2

    cfg_status, original = req("GET", "/api/config")
    if cfg_status != 200 or not isinstance(original, dict):
        return 2
    try:
        test_pages()
        test_reads()
        test_i18n()
        test_writes()
        if args.destructive:
            test_destructive()
        else:
            skip("有副作用的操作", "加 --destructive 才跑")
    finally:
        # Restore settings even if a test fails or is interrupted. Never infer
        # the configured motion switch from the instantaneous motion result.
        restored, _ = req("POST", "/api/config", original)
        check("测试后配置恢复", restored == 200)

    npass = sum(1 for _n, s, _d in results if s == PASS)
    nfail = sum(1 for _n, s, _d in results if s == FAIL)
    nskip = sum(1 for _n, s, _d in results if s == SKIP)
    print("\n" + "=" * 66)
    print("结果: %d PASS / %d FAIL / %d SKIP" % (npass, nfail, nskip))
    if nfail:
        print("\n失败项:")
        for n, s, d in results:
            if s == FAIL:
                print("  ✗ %-42s %s" % (n, d))
    print("=" * 66)

    if args.json:
        print(json.dumps([{"name": n, "status": s, "detail": d} for n, s, d in results],
                         ensure_ascii=False, indent=2))
    return 1 if nfail else 0


if __name__ == "__main__":
    try:
        import io as _io
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    sys.exit(main())
