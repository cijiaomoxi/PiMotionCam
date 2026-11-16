"""服务容器：把各功能模块装配起来，并实现内部命令调度。"""
from __future__ import annotations

import logging
import logging.handlers
import shlex
import os
import sys
import threading
import time
from pathlib import Path

from .audio import AudioCapture, probe_devices
from .camera import Camera
from .config import APP_DIR, ROOT_DIR, CONFIG_FILE, Config
from .control import ControlServer
from .detect import Detector
from .hooks import Hooks
from .presets import Presets
from .recorder import Recorder
from .scheduler import Scheduler
from .servo import Servo
from .state import RuntimeState
from .storage import StorageMonitor
from .timelapse import Timelapse
from .media_tools import next_name
from .audio_recording import AudioRecorder

LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "pikrellcam.log"


class AppService:
    def __init__(self, config_path=CONFIG_FILE):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = self._make_logger()
        self.log_file = LOG_FILE

        self.config = Config(config_path)
        self.config.ensure_dirs()
        self.state = RuntimeState()
        self._audio_control_lock = threading.RLock()
        self._audio_consumers = {}
        self._audio_accepting = True
        self.hooks = Hooks(self.config, log=self.log)
        self.detector = Detector(self.config)
        # 麦克风：常驻采集到环形缓冲，录像收尾时切片合流。
        # 没有麦克风的机器上它自己就是关闭的，不影响录像。
        self.audio = AudioCapture(self.state, log=self.log)
        self.audio_recorder = AudioRecorder(self)
        self.audio.on_level = self._sound_level
        self._sound_started = None
        self._sound_last = 0.
        self.recorder = Recorder(self.config, self.state, on_event=self._on_event,
                                 log=self.log, audio=self.audio)
        self.camera = Camera(self.config, self.state, self.detector, self.recorder,
                             log=self.log)
        self.presets = Presets(self.config, self.state, on_camera_changed=self._restart_camera,
                               on_activate=self._preset_activated)
        self.timelapse = Timelapse(self.config, self.state, self.camera, self.hooks, log=self.log)
        self.servo = Servo(self.config, self.state, log=self.log, on_move=self.detector.suppress,
                           on_preset=self.presets.activate)
        self.scheduler = Scheduler(self.config, self.run_command, log=self.log)
        self.storage = StorageMonitor(self.config, self.state, log=self.log,
                                     on_disk=self.recorder.refresh_disk_state)
        self._lock = threading.Lock()
        self._still_lock = threading.Lock()
        self.control = ControlServer(self.config, self.run_command, self._network_message, self.log)

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
            self._audio_accepting = True
            self.state.update(started_at=time.time(), error=None)
            # 预热原生加速内核：编译/加载放在启动阶段，
            # 避免第一次检测时才付出编译开销
            self._warm_native()
            # 麦克风**比相机先起**：它不依赖相机，提前采集才能让环形缓冲
            # 尽快预热。相机初始化要几十秒（等 V4L2 出流），要是等相机起来
            # 再开麦，服务重启后头一分钟录出来的视频全是哑的。
            self.apply_audio_config()
            self.camera.start()
            # 相机起来后才知道它挂在哪个 USB 口，这时再校正一次麦克风设备
            self._recheck_audio_device()
            self.scheduler.start()
            self.storage.start()
            self.control.start()
            self.hooks.fire("on_startup")
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
            self.control.stop()
            self.servo.disable()
            self.storage.stop()
            self.audio_recorder.stop()
            self.camera.stop()
            self.recorder.stop()
            self.recorder.finish_audio(timeout=8)
            with self._audio_control_lock:
                self._audio_accepting = False
                self._audio_consumers.clear()
                self.audio.stop()
            self.state.update(running=False, camera_ready=False, recording=False)
            self.log("service stopped")

    def restart(self) -> None:
        self.stop()
        time.sleep(1.0)
        self.start()

    def _restart_camera(self):
        try:
            self.camera.stop()
            self.recorder.stop()
            self.detector.reset()
            self.camera.start()
        except Exception as exc:  # noqa: BLE001
            self.log(f"camera restart failed: {exc}")

    def _preset_activated(self):
        self.detector.suppress(self.config.get("motion", "settle_seconds", default=1))
        self.apply_audio_config()

    # ------------------------------------------------------------------
    # 音频（麦克风）
    # ------------------------------------------------------------------
    def _audio_prefer_port(self) -> str:
        """摄像头所在的 USB 端口号。

        USB 摄像头自带的麦克风就在**同一个 USB 口**上（ALSA 与 sysfs 的
        路径写法不同，这里归一成端口号来比对）。
        """
        try:
            v4l2 = getattr(self.camera, "v4l2", None)
            dev = getattr(v4l2, "device", "") if v4l2 else ""
            if dev:
                from .audio import video_usb_port
                return video_usb_port(dev)
        except Exception:
            pass
        return ""

    def audio_status(self) -> dict:
        """音频（麦克风）状态：配置 + 运行时 + 本机可用设备。"""
        st = self.audio.status() if self.audio else {}
        with self._audio_control_lock:
            st["live_clients"] = sum(kind == "live" for kind in self._audio_consumers.values())
        st["stream_enabled"] = bool(self.config.get("record", "audio_stream_enabled", default=False))
        st["trigger_enabled"] = bool(self.config.get("record", "audio_trigger_enabled", default=False))
        st["trigger_level"] = self.config.get("record", "audio_trigger_level", default=.2)
        st["trigger_seconds"] = self.config.get("record", "audio_trigger_seconds", default=.3)
        st["gain_db"] = self.config.get("record", "audio_gain_db", default=0.)
        st["audio_record"] = self.audio_recorder.status()
        try:
            st["enabled"] = bool(self.config.get("record", "audio_enabled",
                                                 default=False))
        except Exception:
            st["enabled"] = False
        try:
            st["configured_device"] = str(self.config.get("record", "audio_device",
                                                          default="auto") or "auto")
        except Exception:
            st["configured_device"] = "auto"
        try:
            st["bitrate"] = int(self.config.get("record", "audio_bitrate",
                                                 default=64) or 64)
        except (TypeError, ValueError):
            st["bitrate"] = 64
        try:
            st["buffer_seconds"] = int(self.config.get("record", "audio_buffer_seconds",
                                                       default=180) or 180)
        except (TypeError, ValueError):
            st["buffer_seconds"] = 180
        try:
            st["devices"] = [d.to_dict() for d in probe_devices()]
        except Exception:
            st["devices"] = []
        return st

    def _recheck_audio_device(self) -> None:
        """相机起来后校正麦克风设备。

        麦克风比相机先启动（环形缓冲要尽早预热），那时候还拿不到摄像头
        所在的 USB 端口号，挑设备只能靠"任意 USB 设备"这条规则。现在
        端口号知道了，如果同口上有一颗更好的麦克风，就切过去。
        """
        try:
            if not self.state.get("audio_enabled"):
                return
            # 用户手动指定过设备就不动
            if str(self.config.get("record", "audio_device", default="auto")
                   or "auto") != "auto":
                return
            port = self._audio_prefer_port()
            if not port:
                return
            devs = probe_devices()
            same = [d for d in devs if d.port == port]
            if not same:
                return
            cur = str((self.audio.status() or {}).get("device") or "")
            if any(cur in (d.id, d.plug_id) for d in same):
                return
            self.log("麦克风设备校正：改用与摄像头同一 USB 口的设备")
            self.apply_audio_config()
        except Exception as exc:  # noqa: BLE001
            self.log("麦克风设备校正失败: %s" % exc)

    def apply_audio_config(self) -> dict:
        with self._audio_control_lock:
            return self._apply_audio_config_locked()

    def acquire_audio(self, kind="live"):
        """One ALSA reader shared by recording, monitoring and audio-only use."""
        with self._audio_control_lock:
            if not self._audio_accepting:
                raise RuntimeError("Audio service is restarting")
            if kind == "live":
                if not self.config.get("record", "audio_stream_enabled", default=False):
                    raise PermissionError("Live audio is disabled")
                if sum(value == "live" for value in self._audio_consumers.values()) >= 4:
                    raise RuntimeError("Live audio listener limit reached")
            token = object()
            self._audio_consumers[token] = kind
            try:
                thread = getattr(self.audio, "_thread", None)
                if not self.audio.running and not (thread and thread.is_alive()):
                    self._apply_audio_config_locked()
                if self.audio.status().get("state") == "error":
                    raise RuntimeError("No usable microphone is available")
            except Exception:
                self._audio_consumers.pop(token, None)
                raise

        def release():
            with self._audio_control_lock:
                if token not in self._audio_consumers:
                    return
                self._audio_consumers.pop(token)
                if not self._audio_consumers and not self._background_audio():
                    self.audio.stop()

        return self.audio, release

    def _apply_audio_config_locked(self) -> dict:
        """按配置启停麦克风采集。

        没插麦 / 采集起不来时只会把状态报成 error，录像主流程照常跑。
        """
        try:
            enabled = self._background_audio()
        except Exception:
            enabled = False
        if not enabled and not self._audio_consumers:
            try:
                self.audio.stop()
            except Exception:
                pass
            self.state.update(audio_enabled=False)
            return self.audio.status()

        def _num(key: str, default: int) -> int:
            try:
                return int(self.config.get("record", key, default=default) or default)
            except (TypeError, ValueError):
                return default

        device = str(self.config.get("record", "audio_device", default="auto") or "auto")
        signature = (device, _num("audio_rate", 16000), _num("audio_channels", 1),
                     _num("audio_buffer_seconds", 180), self._audio_prefer_port())
        if self.audio.running and signature == getattr(self, "_audio_signature", None):
            self.audio._gain_db = float(self.config.get("record", "audio_gain_db", default=0.))
            return self.audio.status()
        st = self.audio.start(device=device,
                              rate=_num("audio_rate", 16000),
                              channels=_num("audio_channels", 1),
                              buffer_seconds=_num("audio_buffer_seconds", 180),
                              prefer_port=self._audio_prefer_port(),
                              gain_db=self.config.get("record", "audio_gain_db", default=0.0))
        self.state.update(audio_enabled=True)
        self._audio_signature = signature
        if st.get("error"):
            self.log("麦克风不可用：%s" % st.get("error"))
        return st

    def _background_audio(self):
        return bool(self.config.get("record", "audio_enabled", default=False) or
                    self.config.get("record", "audio_trigger_enabled", default=False))

    def _sound_level(self, level):
        enabled = self.config.get("record", "audio_trigger_enabled", default=False)
        if not enabled or self.config.get("record", "paused", default=False):
            self._sound_started = None
            return
        now = time.monotonic()
        threshold = max(.001, min(1., float(self.config.get("record", "audio_trigger_level", default=.2))))
        if level < threshold:
            self._sound_started = None
            return
        if self._sound_started is None:
            self._sound_started = now
        hold = max(0., min(10., float(self.config.get("record", "audio_trigger_seconds", default=.3))))
        if now - self._sound_started >= hold and now - self._sound_last >= 1:
            self.recorder.trigger(2, "audio")
            self._sound_last = now

    # ------------------------------------------------------------------
    def _on_event(self, name: str, payload: dict):
        """录制器事件回调 → 触发用户配置的钩子命令。"""
        self.log(f"event {name}: {payload.get('id')}")
        self.hooks.fire(name, payload)
        if name == "on_motion_end":
            if payload.get("algorithm") == "manual":
                self.hooks.fire("on_manual_end", payload)
            if payload.get("ok"):
                self.hooks.fire("on_motion_preview_save", payload)

    # ------------------------------------------------------------------
    # 内部命令（供 at-commands / FIFO / Web 调用）
    # ------------------------------------------------------------------
    def run_command(self, command: str) -> str:
        cmd = (command or "").strip()
        if not cmd:
            return ""
        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            return f"error: {exc}"
        verb = parts[0].lower()
        args = parts[1:]
        self.log(f"command: {cmd}")

        try:
            if verb == "inform":
                text = " ".join(args)[:512]
                self.state.set("inform", {"text": text, "until": time.time()+15})
                return "preview message displayed"

            if verb == "annotate" and args:
                text = " ".join(args[1:])[:160]
                current = self.config.get("web", "burn_in", "text", default="")
                if args[0] == "add":
                    current = (current+" "+text).strip()[:160]
                elif args[0] == "remove":
                    current = current.replace(text, "").strip() if text else ""
                else:
                    return "error: use annotate add/remove TEXT"
                self.config.set({"web": {"burn_in": {"text": current}}})
                return "caption updated"

            if verb == "display":
                menu = dict(self.state.get("menu", {"index": 0, "visible": False}))
                action = args[0] if args else "sel"
                menu["visible"] = action != "back"
                if action in ("<", "<<"): menu["index"] = (menu["index"]-1)%3
                if action in (">", ">>"): menu["index"] = (menu["index"]+1)%3
                self.state.set("menu", menu)
                if action == "sel":
                    paused = self.config.get("record", "paused", default=False)
                    return self.run_command(("motion_enable toggle", "record on" if paused else "record off", "still")[menu["index"]])
                return "preview menu updated"

            if verb == "record":
                action = args[0] if args else "on"
                if action in ("start", "manual"):
                    self.recorder.manual(True, float(args[1]) if len(args) > 1 else 120)
                    return "manual recording started"
                if action == "stop":
                    self.recorder.manual(False)
                    return "manual recording stopped"
                if action in ("on", "resume"):
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
                return self.capture_still()

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
                self.hooks.fire("on_motion_enable", {"id": str(cur)})
                return f"motion_enable {cur}"

            if verb == "motion" and args and args[0] == "load_regions":
                name = args[1] if len(args) > 1 else "default"
                presets = self.config.get("motion", "region_presets", default={}) or {}
                regions = presets.get(name)
                if not regions:
                    return f"no region preset {name}"
                self.config.set({"motion": {"regions": regions}})
                return f"regions loaded: {name}"

            if verb == "motion" and args and args[0] == "trigger":
                self.recorder.trigger(float(args[1]) if len(args) > 1 else 2)
                return "motion triggered"

            if verb == "motion" and args and args[0] == "limits":
                mag = float(args[1]) if len(args) > 1 else 15
                cnt = float(args[2]) if len(args) > 2 else 0.01
                self.config.set({"motion": {"algorithms": {"far": {"magnitude_limit": mag, "count_limit": cnt}}}})
                return f"motion limits {mag} {cnt}"

            if verb == "preset" and len(args) >= 2 and args[0] == "activate":
                self.presets.activate(args[1])
                return f"preset activated: {args[1]}"

            if verb == "servo":
                if args and args[0] == "step":
                    return str(self.servo.step(args[1], float(args[2]) if len(args)>2 else 1, len(args)>3 and args[3]=="multi"))
                if args and args[0] == "scan":
                    return str(self.servo.scan(len(args)<2 or args[1]!="off"))
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

            if verb == "audio":
                arg = (args[0].lower() if args else "status")
                if arg == "record":
                    return str(self.audio_recorder.start(float(args[1]) if len(args)>1 else 120))
                if arg == "record_stop":
                    return str(self.audio_recorder.stop())
                if arg == "gain" and len(args)>1:
                    self.config.set({"record": {"audio_gain_db": max(-30.,min(30.,float(args[1])))}})
                    self.apply_audio_config()
                    return "audio gain saved"
                if arg in ("on", "start", "true", "1"):
                    self.config.set({"record": {"audio_enabled": True}})
                    self.apply_audio_config()
                    return "audio on"
                if arg in ("off", "stop", "false", "0"):
                    self.config.set({"record": {"audio_enabled": False}})
                    self.apply_audio_config()
                    return "audio off"
                st = self.audio_status()
                return ("audio %s device=%s level=%.2f"
                        % (st.get("state", "?"), st.get("device", "-"),
                           float(st.get("level") or 0.0)))

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

    def capture_still(self):
        ok, reason, _ = self.config.media_write_target()
        if not ok:
            raise OSError(f"Storage unavailable: {reason}")
        size = self.config.get("camera", "stills_resolution")
        with self._still_lock:
            if size:
                frame = self.camera.high_resolution_still(size)
                self.detector.suppress(self.config.get("motion", "settle_seconds", default=1))
            else:
                frame = self.camera.latest
        if not frame:
            raise RuntimeError("No camera frame is available")
        ok, reason, _ = self.config.media_write_target()
        if not ok:
            raise OSError(f"Storage unavailable: {reason}")
        name = next_name(self.config, "still", ".jpg")
        path = self.config.media_sub("stills") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(frame)
        self.hooks.fire("on_still_capture", {"id": path.stem, "thumb": name})
        return name

    def _network_message(self, message, peer):
        self.state.set("inform", {"text": message, "until": time.time()+15, "peer": peer})
        self.hooks.fire("on_multicast_pkc_message", {"message": message, "peer": peer})
