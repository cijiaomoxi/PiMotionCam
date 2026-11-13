"""服务容器：把各功能模块装配起来，并实现内部命令调度。"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import time
from pathlib import Path

from .camera import Camera
from .config import APP_DIR, ROOT_DIR, Config
from .detect import Detector
from .hooks import Hooks
from .presets import Presets
from .recorder import Recorder
from .scheduler import Scheduler
from .servo import Servo
from .state import RuntimeState
from .storage import StorageMonitor
from .timelapse import Timelapse

LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "pikrellcam.log"


class AppService:
    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = self._make_logger()
        self.log_file = LOG_FILE

        self.config = Config()
        self.config.ensure_dirs()
        self.state = RuntimeState()
        self.hooks = Hooks(self.config, log=self.log)
        self.detector = Detector(self.config)
        self.recorder = Recorder(self.config, self.state, on_event=self._on_event,
                                 log=self.log)
        self.camera = Camera(self.config, self.state, self.detector, self.recorder,
                             log=self.log)
        self.presets = Presets(self.config, self.state, on_camera_changed=self._restart_camera)
        self.timelapse = Timelapse(self.config, self.state, self.camera, self.hooks, log=self.log)
        self.servo = Servo(self.config, self.state, log=self.log)
        self.scheduler = Scheduler(self.config, self.run_command, log=self.log)
        self.storage = StorageMonitor(self.config, self.state, log=self.log,
                                     on_disk=self.recorder.refresh_disk_state)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @staticmethod
    def _make_logger() -> logging.Logger:
        logger = logging.getLogger("pikrellcam")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            try:
                handler = logging.handlers.RotatingFileHandler(
                    LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
                ))
                logger.addHandler(handler)
            except Exception:
                pass
            logger.addHandler(logging.StreamHandler(sys.stdout))
        return logger

    def log(self, msg: str, *args):
        try:
            self.logger.info(msg, *args)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self.state.get("running"):
                return
            self.config.ensure_dirs()
            self.state.update(started_at=time.time(), error=None)
            # 预热原生加速内核：编译/加载放在启动阶段，
            # 避免第一次检测时才付出编译开销
            self._warm_native()
            self.camera.start()
            self.scheduler.start()
            self.storage.start()
            self.log("service started")

    def _warm_native(self):
        """确保原生加速内核可用（失败则回落纯 Python 实现）。"""
        try:
            from . import native
            if native.ensure_built():
                self.log(f"native acceleration enabled ({native.build_log()})")
            else:
                self.log("native acceleration unavailable, "
                         "falling back to pure python")
        except Exception as exc:  # noqa: BLE001
            self.log(f"native acceleration init failed: {exc}")

    def stop(self) -> None:
        with self._lock:
            self.scheduler.stop()
            self.storage.stop()
            self.recorder.stop()
            self.camera.stop()
            self.state.update(running=False, camera_ready=False, recording=False)
            self.log("service stopped")

    def restart(self) -> None:
        self.stop()
        time.sleep(1.0)
        self.start()

    def _restart_camera(self):
        try:
            self.camera.restart()
        except Exception as exc:  # noqa: BLE001
            self.log(f"camera restart failed: {exc}")

    # ------------------------------------------------------------------
    def _on_event(self, name: str, payload: dict):
        """录制器事件回调 → 触发用户配置的钩子命令。"""
        self.log(f"event {name}: {payload.get('id')}")
        if name == "on_motion_begin":
            self.hooks.fire("on_motion_begin", payload)
        elif name == "on_motion_end":
            self.hooks.fire("on_motion_end", payload)
            if payload.get("ok"):
                self.hooks.fire("on_motion_preview_save", payload)

    # ------------------------------------------------------------------
    # 内部命令（供 at-commands / FIFO / Web 调用）
    # ------------------------------------------------------------------
    def run_command(self, command: str) -> str:
        cmd = (command or "").strip()
        if not cmd:
            return ""
        parts = cmd.split()
        verb = parts[0].lower()
        args = parts[1:]
        self.log(f"command: {cmd}")

        try:
            if verb == "record":
                action = args[0] if args else "on"
                if action == "on":
                    self.config.set({"record": {"paused": False}})
                    self.state.update(record_paused=False)
                    return "record on"
                if action == "off":
                    self.config.set({"record": {"paused": True}})
                    self.state.update(record_paused=True)
                    return "record off"
                if action == "pause":
                    self.config.set({"record": {"paused": True}})
                    self.state.update(record_paused=True)
                    return "record paused"
                return "unknown"

            if verb == "record_pause":
                self.config.set({"record": {"paused": True}})
                self.state.update(record_paused=True)
                return "record paused"

            if verb == "still":
                frame = self.camera.latest
                if not frame:
                    return "no frame"
                ok, reason, _ = self.config.media_write_target()
                if not ok:
                    return f"storage unavailable: {reason}"
                name = time.strftime("still_%Y%m%d_%H%M%S.jpg")
                path = self.config.media_sub("stills") / name
                path.write_bytes(frame)
                return name

            if verb == "tl_start":
                period = int(args[0]) if args and args[0].isdigit() else None
                self.timelapse.start(period)
                return f"tl_start {period or ''}".strip()

            if verb == "tl_hold":
                on = not (args and args[0].lower() == "off")
                self.timelapse.hold(on)
                return f"tl_hold {'on' if on else 'off'}"

            if verb == "tl_end":
                self.timelapse.end()
                return "tl_end"

            if verb == "motion_enable":
                arg = (args[0].lower() if args else "toggle")
                cur = bool(self.config.get("motion", "enabled", default=True))
                if arg == "toggle":
                    cur = not cur
                else:
                    cur = arg in ("on", "true", "1", "yes")
                self.config.set({"motion": {"enabled": cur}})
                return f"motion_enable {cur}"

            if verb == "motion" and args and args[0] == "load_regions":
                name = args[1] if len(args) > 1 else "default"
                presets = self.config.get("motion", "region_presets", default={}) or {}
                regions = presets.get(name)
                if not regions:
                    return f"no region preset {name}"
                self.config.set({"motion": {"regions": regions}})
                return f"regions loaded: {name}"

            if verb == "motion" and args and args[0] == "limits":
                mag = float(args[1]) if len(args) > 1 else 15
                cnt = float(args[2]) if len(args) > 2 else 0.01
                self.config.set({"motion": {"algorithms": {"far": {"magnitude_limit": mag, "count_limit": cnt}}}})
                return f"motion limits {mag} {cnt}"

            if verb == "servo":
                if args and args[0] == "goto":
                    res = self.servo.goto(args[1])
                    return f"servo goto {args[1]} ok={res.get('ok')}"
                if args and args[0] == "set":
                    pan = float(args[1]) if len(args) > 1 else None
                    tilt = float(args[2]) if len(args) > 2 else None
                    self.servo.set_angle(pan, tilt)
                    return f"servo set {pan} {tilt}"
                if args and args[0] == "enable":
                    self.servo.enable()
                    return "servo enabled"

            if verb == "loop":
                arg = (args[0].lower() if args else "status")
                if arg in ("on", "start", "true", "1"):
                    self.recorder.set_loop_enabled(True)
                    return "loop on"
                if arg in ("off", "stop", "false", "0"):
                    self.recorder.set_loop_enabled(False)
                    return "loop off"
                st = self.recorder.loop_stats()
                return ("loop %s segments=%d bytes=%d recording=%s"
                        % ("on" if st.get("enabled") else "off",
                           st.get("segments", 0), st.get("bytes", 0),
                           st.get("recording", False)))

            if verb == "imaging":
                # 只读查询当前成像参数；改参数走网页的成像参数面板
                st = self.camera.imaging_status()
                vals = st.get("values", {})
                return ("imaging backend=%s brightness=%s contrast=%s saturation=%s"
                        % (st.get("backend"), vals.get("brightness"),
                           vals.get("contrast"), vals.get("saturation")))

            if verb == "start":
                self.start()
                return "started"
            if verb == "stop":
                self.stop()
                return "stopped"
            if verb == "restart":
                self.restart()
                return "restarted"
        except Exception as exc:  # noqa: BLE001
            self.log(f"command error: {cmd}: {exc}")
            return f"error: {exc}"
        return f"unknown command: {cmd}"
