"""Web API 与页面路由。

覆盖官方 PiKrellCam 的全部网页能力：实时预览（OSD 叠加）、运动区域图形化编辑、
双算法灵敏度、预设切换、事件/录像/抓拍/延时摄影管理、定时命令、舵机、
系统日志、升级、帮助、密码保护。
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

from .config import APP_DIR, check_password, hash_password
from .i18n import available as i18n_available
from .i18n import resolve as resolve_language
from .i18n import strings as i18n_strings
from .i18n import translate as i18n_translate
from .util import dir_size, human_size, run_command, tail_file

def _make_placeholder_jpeg() -> bytes:
    """相机无帧时用于占位的深灰图，保证 MJPEG 响应能立即开始。"""
    try:
        from PIL import Image, ImageDraw
        import io as _io
        im = Image.new("RGB", (320, 180), (24, 28, 38))
        d = ImageDraw.Draw(im)
        d.text((110, 84), "无信号", fill=(120, 128, 145))
        buf = _io.BytesIO()
        im.save(buf, format="JPEG", quality=60)
        return buf.getvalue()
    except Exception:
        return b""


_PLACEHOLDER_JPEG = _make_placeholder_jpeg()


HELP_SECTIONS = [    {"title": "概览", "body": "pikrellcam-lite 是一个基于 libcamera/picamera2 的移动侦测录像服务，"
                              "提供实时预览、运动检测录像、事件回看与网页调参。"},
    {"title": "运动检测", "body": "使用帧差分实现双算法并行检测：far 算法面向远处小而慢的目标，"
                                  "near 算法面向近处大目标。可在多个运动区域上分别判定，"
                                  "区域可在网页预览图上拖拽绘制并命名保存。"},
    {"title": "录像", "body": "触发后先写入预录缓冲中的历史帧，再继续录制补录时长，"
                              "结束后由 ffmpeg 统一编码为 H.264 MP4，并生成整帧缩略图与"
                              "运动目标裁剪缩略图。"},
    {"title": "定时命令", "body": "可按星期+时刻或固定间隔执行命令，命令可以是内部命令"
                                  "（record on、tl_start 30 等）、FIFO 命令或任意 shell 命令。"},
    {"title": "舵机", "body": "支持 RPi.GPIO 或 ServoBlaster 驱动云台舵机，可保存位置预设并"
                              "设置平移俯仰限位与平滑移动时间。"},
    {"title": "运维", "body": "systemctl --user status pikrellcam-lite 查看状态；"
                              "journalctl --user -u pikrellcam-lite -f 查看实时日志。"},
]


def create_app(service) -> Flask:
    app = Flask(__name__, template_folder=str(APP_DIR / "templates"),
                static_folder=str(APP_DIR / "static"))
    app.secret_key = os.urandom(24)
    app.config["SERVICE"] = service
    # ------------------------------------------------------------------
    # 多语言
    # ------------------------------------------------------------------
    def current_lang() -> str:
        """本次请求使用的语言：配置优先，auto 时按浏览器 Accept-Language 判断。"""
        configured = service.config.get("web", "language", default="auto")
        return resolve_language(configured, request.headers.get("Accept-Language", ""))

    def i18n_payload() -> dict:
        lang = current_lang()
        return {"language": lang, "available": i18n_available(),
                "strings": i18n_strings(lang)}

    # ------------------------------------------------------------------
    # 密码保护
    # ------------------------------------------------------------------
    def auth_required() -> bool:
        stored = service.config.get("web", "password_hash", default="") or ""
        if not stored:
            return False
        return not session.get("pkc_auth")

    @app.before_request
    def _guard():
        if not auth_required():
            return None
        path = request.path
        if path in ("/api/auth/login", "/api/auth", "/login"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"ok": False,
                            "error": i18n_translate("需要登录", current_lang()),
                            "auth": True}), 401
        return redirect(url_for("login_page"))

    # ------------------------------------------------------------------
    # 页面
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html", i18n=i18n_payload())

    @app.route("/login")
    def login_page():
        return render_template("login.html", i18n=i18n_payload())

    @app.route("/media/<kind>/<path:name>")
    def media(kind, name):
        folder = {"videos": "videos", "stills": "stills", "timelapse": "timelapse"}.get(kind)
        if not folder:
            return ("not found", 404)
        path = service.config.media_sub(folder) / name
        if not path.exists() or not path.is_file():
            return ("not found", 404)
        return send_file(str(path), conditional=True)

    # ------------------------------------------------------------------
    # 鉴权 API
    # ------------------------------------------------------------------
    @app.route("/api/auth", methods=["GET"])
    def api_auth():
        stored = service.config.get("web", "password_hash", default="") or ""
        return jsonify({
            "required": bool(stored),
            "authenticated": (not stored) or bool(session.get("pkc_auth")),
        })

    @app.route("/api/auth/login", methods=["POST"])
    def api_login():
        data = request.get_json(silent=True) or {}
        stored = service.config.get("web", "password_hash", default="") or ""
        if not stored:
            return jsonify({"ok": True, "authenticated": True})
        if check_password(stored, data.get("password", "")):
            session["pkc_auth"] = True
            return jsonify({"ok": True, "authenticated": True})
        return jsonify({"ok": False,
                        "error": i18n_translate("密码错误", current_lang())}), 401

    @app.route("/api/auth/logout", methods=["POST"])
    def api_logout():
        session.pop("pkc_auth", None)
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # 多语言 API
    # ------------------------------------------------------------------
    @app.route("/api/i18n", methods=["GET"])
    def api_i18n_get():
        """返回当前语言、全部可选语言与文案字典。"""
        return jsonify(i18n_payload())

    @app.route("/api/i18n", methods=["POST"])
    def api_i18n_set():
        """切换界面语言，持久化到 config.json 的 web.language。"""
        data = request.get_json(silent=True) or {}
        lang = str(data.get("language", "") or "").strip()
        if lang.lower() == "auto":
            lang = "auto"
        else:
            hit = resolve_language(lang, "")
            # resolve_language 对非法值会回落到默认语言，这里要区分"非法"和"默认"
            known = {c["code"] for c in i18n_available()}
            if lang not in known:
                msg = i18n_translate("不支持的语言", current_lang()) + f": {lang}"
                return jsonify({"ok": False, "error": msg}), 400
            lang = hit
        service.config.set({"web": {"language": lang}})
        return jsonify({"ok": True, "language": lang, "strings": i18n_strings(
            resolve_language(lang, request.headers.get("Accept-Language", "")))})

    @app.route("/api/password", methods=["POST"])
    def api_password():
        data = request.get_json(silent=True) or {}
        pwd = (data.get("password") or "").strip()
        if not pwd:
            service.config.set({"web": {"password_hash": ""}})
            return jsonify({"ok": True, "enabled": False})
        service.config.set({"web": {"password_hash": hash_password(pwd)}})
        return jsonify({"ok": True, "enabled": True})

    # ------------------------------------------------------------------
    # 状态与配置
    # ------------------------------------------------------------------
    @app.route("/api/state")
    def api_state():
        st = service.state.snapshot()
        cfg = service.config.snapshot()
        videos = service.config.media_sub("videos")
        st["media"] = {
            "videos": len(list(videos.glob("*.mp4"))) if videos.exists() else 0,
            "stills": len(list(service.config.media_sub("stills").glob("*.jpg"))),
            "disk_bytes": dir_size(service.config.media_dir()),
            "disk_used": human_size(dir_size(service.config.media_dir())),
            "max_disk_gb": cfg["record"]["max_disk_gb"],
            "dir": str(service.config.media_dir()),
        }
        st["presets"] = sorted((cfg.get("presets") or {}).keys())
        st["version"] = _version()
        st["auth_required"] = bool(cfg["web"].get("password_hash"))
        st["camera"] = service.camera.camera_info
        st["release"] = _release_info()
        return jsonify(st)

    @app.route("/api/config", methods=["GET"])
    def api_config_get():
        return jsonify(service.config.snapshot())

    @app.route("/api/config", methods=["POST"])
    def api_config_post():
        data = request.get_json(silent=True) or {}
        patch = {k: v for k, v in data.items() if k in (
            "camera", "motion", "record", "timelapse", "web", "media", "servo", "hooks")}
        if not patch:
            return jsonify({"ok": False, "error": "没有可更新的配置段"}), 400
        if "web" in patch and "password_hash" in patch["web"]:
            patch["web"].pop("password_hash")
        # 采集链路相关的键变化时都要重建管线：
        # 分辨率 / 帧率 / 旋转 / 镜像 / 通路 / 设备
        _CAM_KEYS = ("resolution", "fps", "rotation", "flip", "format", "device")
        old_cam = {k: service.config.get("camera", k) for k in _CAM_KEYS}
        service.config.set(patch)
        new_cam = {k: service.config.get("camera", k) for k in _CAM_KEYS}
        if "camera" in patch and new_cam != old_cam:
            service._restart_camera()
        return jsonify({"ok": True, "config": service.config.snapshot()})

    @app.route("/api/config/reset", methods=["POST"])
    def api_config_reset():
        service.config.reset()
        service._restart_camera()
        return jsonify({"ok": True, "config": service.config.snapshot()})

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    @app.route("/snapshot.jpg")
    def snapshot():
        frame = service.camera.latest
        if not frame:
            return ("", 404)
        resp = app.response_class(frame, mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    @app.route("/video_feed")
    def video_feed():
        boundary = "pkcframe"

        def generate():
            # 先给一张占位图，保证 multipart 响应立即开始，
            # 否则相机还没出帧时浏览器会一直等，页面 load 事件永远不触发。
            yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                   f"Content-Length: {len(_PLACEHOLDER_JPEG)}\r\n\r\n").encode() \
                + _PLACEHOLDER_JPEG + b"\r\n"
            while True:
                frame = service.camera.wait_for_frame(timeout=5.0)
                if frame is None:
                    yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                           f"Content-Length: {len(_PLACEHOLDER_JPEG)}\r\n\r\n").encode() \
                        + _PLACEHOLDER_JPEG + b"\r\n"
                    continue
                yield (f"--{boundary}\r\nContent-Type: image/jpeg\r\n"
                       f"Content-Length: {len(frame)}\r\n\r\n").encode() + frame + b"\r\n"

        return Response(generate(), mimetype=f"multipart/x-mixed-replace; boundary={boundary}",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    # ------------------------------------------------------------------
    # 服务与运动检测
    # ------------------------------------------------------------------
    @app.route("/api/cameras")
    def api_cameras():
        """列出所有可用摄像头（CSI + USB），供网页选择。"""
        from .camera import list_cameras
        try:
            cams = list_cameras()
        except Exception as exc:  # noqa: BLE001
            cams = []
        current = service.config.get("camera", "device", default="auto")
        current_fmt = service.config.get("camera", "format", default="auto")
        return jsonify({"cameras": cams, "current": current, "format": current_fmt,
                        "active": service.camera.camera_info})

    @app.route("/api/cameras/select", methods=["POST"])
    def api_camera_select():
        """切换摄像头（CSI / USB）与采集通路。"""
        data = request.get_json(silent=True) or {}
        device = str(data.get("device", "auto") or "auto")
        patch = {"camera": {"device": device}}
        fmt = data.get("format")
        if fmt:
            fmt = str(fmt).strip().upper()
            allowed = ("AUTO", "MJPEG", "RGB888", "XBGR8888", "YUYV", "YUV420")
            if fmt not in allowed:
                return jsonify({"ok": False, "error": "不支持的采集通路"}), 400
            patch["camera"]["format"] = fmt
        service.config.set(patch)
        service._restart_camera()
        return jsonify({"ok": True, "device": device,
                        "format": patch["camera"].get("format")})

    @app.route("/api/service", methods=["POST"])
    def api_service():
        action = (request.get_json(silent=True) or {}).get("action")
        if action == "start":
            service.start()
        elif action == "stop":
            service.stop()
        elif action == "restart":
            service.restart()
        else:
            return jsonify({"ok": False, "error": "unknown action"}), 400
        return jsonify({"ok": True, "running": service.state.get("running")})

    @app.route("/api/motion", methods=["POST"])
    def api_motion():
        enabled = bool((request.get_json(silent=True) or {}).get("enabled", True))
        service.config.set({"motion": {"enabled": enabled}})
        return jsonify({"ok": True, "enabled": enabled})

    @app.route("/api/regions", methods=["GET"])
    def api_regions_get():
        return jsonify({
            "regions": service.config.get("motion", "regions", default=[]),
            "presets": service.config.get("motion", "region_presets", default={}),
        })

    @app.route("/api/regions", methods=["POST"])
    def api_regions_post():
        data = request.get_json(silent=True) or {}
        regions = data.get("regions")
        if not isinstance(regions, list):
            return jsonify({"ok": False, "error": "regions 必须是数组"}), 400
        clean = []
        for r in regions[:32]:
            try:
                x = max(0.0, min(1.0, float(r.get("x", 0))))
                y = max(0.0, min(1.0, float(r.get("y", 0))))
                w = max(0.01, min(1.0 - x, float(r.get("w", 1))))
                h = max(0.01, min(1.0 - y, float(r.get("h", 1))))
            except Exception:
                continue
            clean.append({
                "name": str(r.get("name") or f"区域{len(clean)+1}")[:32],
                "x": round(x, 4), "y": round(y, 4),
                "w": round(w, 4), "h": round(h, 4),
                "enabled": bool(r.get("enabled", True)),
            })
        service.config.set({"motion": {"regions": clean}})
        return jsonify({"ok": True, "regions": clean})

    @app.route("/api/regions/preset", methods=["POST"])
    def api_region_preset_save():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "名称不能为空"}), 400
        presets = dict(service.config.get("motion", "region_presets", default={}) or {})
        presets[name] = data.get("regions") or []
        # 整段替换 motion.region_presets：深合并会留下被删掉的旧预设
        service.config.replace_value("motion", "region_presets", presets)
        return jsonify({"ok": True, "presets": list(presets.keys())})

    @app.route("/api/regions/preset/activate", methods=["POST"])
    def api_region_preset_activate():
        name = (request.get_json(silent=True) or {}).get("name")
        presets = service.config.get("motion", "region_presets", default={}) or {}
        if name not in presets:
            return jsonify({"ok": False, "error": "预设不存在"}), 404
        service.config.set({"motion": {"regions": presets[name]}})
        return jsonify({"ok": True, "regions": presets[name]})

    @app.route("/api/regions/preset/<name>", methods=["DELETE"])
    def api_region_preset_delete(name):
        presets = dict(service.config.get("motion", "region_presets", default={}) or {})
        if name not in presets:
            return jsonify({"ok": False, "error": "预设不存在"}), 404
        presets.pop(name)
        # 整段替换 motion.region_presets：深合并会把刚删掉的预设合回来
        service.config.replace_value("motion", "region_presets", presets)
        return jsonify({"ok": True, "presets": list(presets.keys())})

    @app.route("/api/algorithms", methods=["GET"])
    def api_algorithms_get():
        return jsonify(service.config.get("motion", "algorithms", default={}))

    @app.route("/api/algorithms", methods=["POST"])
    def api_algorithms_post():
        data = request.get_json(silent=True) or {}
        patch = {}
        for name in ("far", "near"):
            if isinstance(data.get(name), dict):
                patch[name] = {
                    "enabled": bool(data[name].get("enabled", True)),
                    "magnitude_limit": float(data[name].get("magnitude_limit", 15)),
                    "count_limit": float(data[name].get("count_limit", 0.01)),
                    "consecutive_frames": int(data[name].get("consecutive_frames", 2)),
                    "noise_filter": int(data[name].get("noise_filter", 0)),
                }
        if not patch:
            return jsonify({"ok": False, "error": "无有效算法参数"}), 400
        service.config.set({"motion": {"algorithms": patch}})
        return jsonify({"ok": True, "algorithms": service.config.get("motion", "algorithms")})

    # ------------------------------------------------------------------
    # 预设
    # ------------------------------------------------------------------
    @app.route("/api/presets", methods=["GET"])
    def api_presets_get():
        return jsonify({"presets": service.config.get("presets", default={})})

    @app.route("/api/presets", methods=["POST"])
    def api_presets_save():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "名称不能为空"}), 400
        payload = data.get("config") or {}
        service.presets.save(name, payload)
        return jsonify({"ok": True, "presets": service.presets.list()})

    @app.route("/api/presets/activate", methods=["POST"])
    def api_presets_activate():
        name = (request.get_json(silent=True) or {}).get("name")
        try:
            service.presets.activate(name)
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "config": service.config.snapshot()})

    @app.route("/api/presets/<name>", methods=["DELETE"])
    def api_presets_delete(name):
        ok = service.presets.delete(name)
        return jsonify({"ok": ok})

    # ------------------------------------------------------------------
    # 录像 / 延时摄影 / 抓拍
    # ------------------------------------------------------------------
    @app.route("/api/record", methods=["POST"])
    def api_record():
        action = (request.get_json(silent=True) or {}).get("action")
        if action in ("on", "resume"):
            service.config.set({"record": {"paused": False}})
            service.state.update(record_paused=False)
        elif action in ("off", "pause"):
            service.config.set({"record": {"paused": True}})
            service.state.update(record_paused=True)
        else:
            return jsonify({"ok": False, "error": "unknown action"}), 400
        return jsonify({"ok": True, "paused": service.state.get("record_paused")})

    @app.route("/api/still", methods=["POST"])
    def api_still():
        frame = service.camera.latest
        if not frame:
            return jsonify({"ok": False, "error": "没有可用帧"}), 400
        name = f"still_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        (service.config.media_sub("stills")).mkdir(parents=True, exist_ok=True)
        (service.config.media_sub("stills") / name).write_bytes(frame)
        return jsonify({"ok": True, "name": name,
                        "url": url_for("media", kind="stills", name=name)})

    @app.route("/api/timelapse", methods=["GET"])
    def api_timelapse_get():
        return jsonify(service.timelapse.status())

    @app.route("/api/timelapse", methods=["POST"])
    def api_timelapse_post():
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        if action == "start":
            return jsonify(service.timelapse.start(data.get("period")))
        if action == "hold":
            return jsonify(service.timelapse.hold(bool(data.get("on", True))))
        if action == "end":
            return jsonify(service.timelapse.end())
        return jsonify({"ok": False, "error": "unknown action"}), 400

    # ------------------------------------------------------------------
    # 媒体
    # ------------------------------------------------------------------
    @app.route("/api/events")
    def api_events():
        return jsonify(service.recorder.events)

    @app.route("/api/events/<eid>", methods=["DELETE"])
    def api_event_delete(eid):
        ok = service.recorder.delete_event(eid)
        return jsonify({"ok": ok})

    @app.route("/api/videos")
    def api_videos():
        folder = service.config.media_sub("videos")
        items = []
        if folder.exists():
            for f in sorted(folder.glob("*.mp4"), key=lambda p: -p.stat().st_mtime):
                st = f.stat()
                items.append({"name": f.name, "size": st.st_size,
                              "size_h": human_size(st.st_size), "mtime": st.st_mtime})
        return jsonify(items)

    @app.route("/api/stills")
    def api_stills():
        folder = service.config.media_sub("stills")
        items = []
        if folder.exists():
            for f in sorted(folder.glob("*.jpg"), key=lambda p: -p.stat().st_mtime):
                st = f.stat()
                items.append({"name": f.name, "size": st.st_size,
                              "size_h": human_size(st.st_size), "mtime": st.st_mtime})
        return jsonify(items)

    @app.route("/api/purge", methods=["POST"])
    def api_purge():
        what = (request.get_json(silent=True) or {}).get("what", "all")
        n = service.recorder.purge(what)
        return jsonify({"ok": True, "removed": n})

    @app.route("/api/archive", methods=["POST"])
    def api_archive():
        """把事件录像复制到远端（对应官方 NFS Archive）。"""
        data = request.get_json(silent=True) or {}
        eid = data.get("id")
        target = data.get("target") or service.config.get("media", "archive_target", default="")
        if not eid or not target:
            return jsonify({"ok": False, "error": "缺少 id 或未配置归档目标"}), 400
        src = service.config.media_sub("videos") / f"{eid}.mp4"
        if not src.exists():
            return jsonify({"ok": False, "error": "录像不存在"}), 404
        cmd = f"scp -q {src.name} {target}"
        rc, out, err = run_command(cmd, timeout=600, cwd=str(src.parent))
        if rc != 0:
            return jsonify({"ok": False, "error": err.strip()[:400] or "scp 失败"}), 500
        return jsonify({"ok": True, "target": target})

    # ------------------------------------------------------------------
    # 定时命令 / 内部命令
    # ------------------------------------------------------------------
    @app.route("/api/schedules", methods=["GET"])
    def api_schedules_get():
        return jsonify(service.scheduler.entries())

    @app.route("/api/schedules", methods=["POST"])
    def api_schedules_post():
        data = request.get_json(silent=True) or {}
        if not (data.get("command") or "").strip():
            return jsonify({"ok": False, "error": "命令不能为空"}), 400
        return jsonify({"ok": True, "entries": service.scheduler.save_entry(data)})

    @app.route("/api/schedules/<int:index>", methods=["DELETE"])
    def api_schedules_delete(index):
        return jsonify({"ok": service.scheduler.delete_entry(index)})

    @app.route("/api/schedules/reload", methods=["POST"])
    def api_schedules_reload():
        return jsonify({"ok": True, "entries": service.scheduler.reload()})

    @app.route("/api/command", methods=["POST"])
    def api_command():
        cmd = (request.get_json(silent=True) or {}).get("command", "")
        return jsonify({"ok": True, "result": service.run_command(cmd)})

    # ------------------------------------------------------------------
    # 舵机
    # ------------------------------------------------------------------
    @app.route("/api/servo", methods=["GET"])
    def api_servo_get():
        return jsonify(service.servo.status())

    @app.route("/api/servo", methods=["POST"])
    def api_servo_post():
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        if action == "enable":
            return jsonify(service.servo.enable())
        if action == "disable":
            return jsonify(service.servo.disable())
        if action == "goto":
            return jsonify(service.servo.goto(data.get("name", "")))
        if action == "set":
            return jsonify(service.servo.set_angle(data.get("pan"), data.get("tilt"),
                                                   data.get("smooth_ms")))
        if action == "save_position":
            return jsonify(service.servo.save_position(
                data.get("name", ""), data.get("pan", 90), data.get("tilt", 90),
                data.get("preset", "")))
        if action == "delete_position":
            return jsonify(service.servo.delete_position(data.get("name", "")))
        return jsonify({"ok": False, "error": "unknown action"}), 400

    # ------------------------------------------------------------------
    # 钩子 / 日志 / 升级 / 帮助
    # ------------------------------------------------------------------
    @app.route("/api/hooks", methods=["GET"])
    def api_hooks_get():
        return jsonify({"hooks": service.config.get("hooks", default={}),
                        "history": service.hooks.history()})

    @app.route("/api/hooks", methods=["POST"])
    def api_hooks_post():
        data = request.get_json(silent=True) or {}
        patch = {k: str(v) for k, v in data.items()
                 if k in ("on_motion_begin", "on_motion_end",
                          "on_motion_preview_save", "on_timelapse_end")}
        service.config.set({"hooks": patch})
        return jsonify({"ok": True, "hooks": service.config.get("hooks")})

    @app.route("/api/log")
    def api_log():
        lines = tail_file(service.log_file, 300)
        return jsonify({"lines": lines})

    @app.route("/api/upgrade", methods=["POST"])
    def api_upgrade():
        """从 git 远端拉取更新并重启（官方的一键升级）。"""
        repo = str(APP_DIR)
        if not (Path(repo) / ".git").exists():
            return jsonify({"ok": False,
                            "error": "部署目录不是 git 仓库，无法在线升级"}), 400
        rc, out, err = run_command("git pull --ff-only", timeout=180, cwd=repo)
        if rc != 0:
            return jsonify({"ok": False, "error": (err or out)[-500:]}), 500
        service.restart()
        return jsonify({"ok": True, "output": out[-800:]})

    @app.route("/api/help")
    def api_help():
        """帮助说明（内容在语言包里，按当前语言返回）。"""
        lang = current_lang()
        s = i18n_strings(lang)
        sections = []
        i = 1
        while f"help.{i}.title" in s:
            sections.append({"title": s[f"help.{i}.title"],
                             "body": s.get(f"help.{i}.body", "")})
            i += 1
        if not sections:  # 语言包缺内容时回落到内置中文
            return jsonify({"sections": HELP_SECTIONS, "language": lang})
        return jsonify({"sections": sections, "language": lang})

    @app.route("/api/release")
    def api_release():
        """当前运行版本与本地保留的全部历史版本。"""
        return jsonify(_release_info())

    @app.route("/api/system")
    def api_system():
        model = ""
        try:
            model = Path("/proc/device-tree/model").read_text().strip("\x00").strip()
        except Exception:
            pass
        return jsonify({
            "model": model or platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "app_dir": str(APP_DIR),
            "media_dir": str(service.config.media_dir()),
            "hostname": platform.node(),
            "uptime_file": _uptime(),
        })

    return app


def _release_info() -> dict:
    """当前运行的是哪个发布版本，以及本地还保留着哪些历史版本。"""
    from .config import ROOT_DIR
    try:
        from . import __version__
    except Exception:
        __version__ = "2.0.0"
    releases_dir = ROOT_DIR / "releases"
    releases = []
    if releases_dir.is_dir():
        releases = sorted(p.name for p in releases_dir.iterdir() if p.is_dir())
    current = ""
    cur = ROOT_DIR / "current"
    if cur.is_symlink():
        current = os.path.basename(os.readlink(cur))
    return {
        "version": __version__,
        "release": APP_DIR.name,
        "current": current,
        "releases": releases,
        "root": str(ROOT_DIR),
    }


def _version() -> str:
    try:
        rc, out, _ = run_command("git rev-parse --short HEAD", timeout=10, cwd=str(APP_DIR))
        if rc == 0 and out.strip():
            return out.strip()
    except Exception:
        pass
    try:
        from . import __version__
        return __version__
    except Exception:
        return "2.0.0"


def _uptime() -> str:
    try:
        with open("/proc/uptime") as fh:
            secs = float(fh.read().split()[0])
        h, rem = divmod(int(secs), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m}m{s}s"
    except Exception:
        return ""
