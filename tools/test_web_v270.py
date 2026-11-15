#!/usr/bin/env python3
"""v2.7.0 新端点的本地集成测试（用 Flask 测试客户端，不需要树莓派）。

验证 /api/loop 与 /api/imaging 的请求处理、参数钳制、状态回报，
以及 /api/state 里新出现的 loop 段。

用法：
    python3 tools/test_web_v270.py
    PKC_FLASK=/path/to/flask/site-packages python3 tools/test_web_v270.py

没有 flask 时直接跳过（不算失败）——树莓派上跑端到端回归才是权威验证。
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- numpy / Pillow 打桩（Mac 上没装）------------------------------------
try:
    import numpy  # noqa: F401
except Exception:  # noqa: BLE001
    np = types.ModuleType("numpy")
    np.ndarray = object
    np.uint8 = "uint8"
    np.ascontiguousarray = lambda a: a
    np.asarray = lambda a, dtype=None: a
    np.empty = lambda *a, **k: None
    np.resize = lambda a, s: a
    sys.modules["numpy"] = np
for _name in ("PIL", "PIL.Image"):
    try:
        __import__(_name)
    except Exception:  # noqa: BLE001
        sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["PIL"].Image = sys.modules["PIL.Image"]

# flask 可能装在别处（PKC_FLASK 环境变量）
_extra = os.environ.get("PKC_FLASK")
if _extra and _extra not in sys.path:
    sys.path.insert(0, _extra)
try:
    import flask  # noqa: F401
except Exception as exc:  # noqa: BLE001
    print("跳过：没有 flask（%s）" % exc)
    print("提示：pip install --target /tmp/pkc_flask 'flask<3' 后用 "
          "PKC_FLASK=/tmp/pkc_flask 运行本脚本")
    sys.exit(0)

from core import config as config_mod       # noqa: E402
from core import imaging                     # noqa: E402
from core.config import Config              # noqa: E402
from core.recorder import Recorder          # noqa: E402
from core.state import RuntimeState         # noqa: E402
from core.web import create_app             # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []
QUIET = "--quiet" in sys.argv


def check(name: str, cond: bool, detail: object = "") -> None:
    (PASS if cond else FAIL).append(name)
    if not QUIET:
        extra = ("  — " + str(detail)) if detail not in ("", None) else ""
        print(("  ✅ " if cond else "  ❌ ") + name + extra)


class StubCamera:
    """替身相机：只提供成像参数相关接口。"""

    def __init__(self, config, state, backend="rpicam"):
        self.config = config
        self.state = state
        self.camera_info = {"backend": backend, "format": "MJPEG",
                            "model": "stub", "resolution": [1280, 720]}
        self.backend = backend
        self.restarts = 0
        self._values = imaging.normalize(config.get("camera", "imaging", default={}))
        self._unsupported: list[str] = []

    @property
    def latest(self):
        return None

    def restart(self):
        self.restarts += 1

    def imaging_backend(self):
        return self.backend

    def imaging_status(self):
        backend = self.backend
        return {
            "values": dict(self._values),
            "backend": backend,
            "supported": imaging.supported_keys(backend),
            "requires_restart": imaging.requires_restart(backend),
            "unsupported": list(self._unsupported),
            "applied": True,
        }

    def apply_imaging(self, values):
        backend = self.backend
        self._values = imaging.normalize(values)
        if backend == imaging.BACKEND_RPICAM:
            return {"ok": True, "backend": backend, "applied": False,
                    "requires_restart": True, "message": "需要重启相机"}
        return {"ok": True, "backend": backend, "applied": True,
                "requires_restart": False, "message": ""}


class Service:
    """给 create_app 用的最小服务对象。"""

    def __init__(self, root: Path):
        self.config = Config(root / "config.json")
        self.config.ensure_dirs()
        self.state = RuntimeState()
        self.recorder = Recorder(self.config, self.state)
        self.camera = StubCamera(self.config, self.state)
        self.presets = types.SimpleNamespace(list=lambda: [], activate=lambda n: None,
                                             save=lambda n, c: None, delete=lambda n: True)
        self.timelapse = types.SimpleNamespace(status=lambda: {}, start=lambda p=None: {},
                                               hold=lambda o=True: {}, end=lambda: {})
        self.servo = types.SimpleNamespace(status=lambda: {}, enable=lambda: {},
                                           disable=lambda: {}, goto=lambda n: {},
                                           set_angle=lambda p, t: {})
        self.scheduler = types.SimpleNamespace(save_entry=lambda d: d,
                                               delete_entry=lambda i: True,
                                               reload=lambda: [])
        self.hooks = types.SimpleNamespace(history=lambda: [], fire=lambda *a: None)
        self.storage = types.SimpleNamespace(status=lambda: {})
        self.log = lambda *a, **k: None
        # 音频替身：只提供状态与"应用配置"这两个接口
        self.audio = types.SimpleNamespace(
            status=lambda: {"state": "idle", "device": "", "rate": 16000,
                            "channels": 1, "level": 0.0, "error": "",
                            "running": False},
            stop=lambda: {})
        self.audio_applied = 0

    def audio_status(self):
        # 真实服务里这些值来自采集器；替身直接读配置，效果一致
        d = dict(self.audio.status())
        d["enabled"] = bool(self.config.get("record", "audio_enabled", default=False))
        d["configured_device"] = str(self.config.get("record", "audio_device",
                                                     default="auto") or "auto")
        d["rate"] = int(self.config.get("record", "audio_rate", default=16000) or 16000)
        d["channels"] = int(self.config.get("record", "audio_channels", default=1) or 1)
        d["bitrate"] = int(self.config.get("record", "audio_bitrate", default=64) or 64)
        d["buffer_seconds"] = int(self.config.get("record", "audio_buffer_seconds",
                                                default=180) or 180)
        d["devices"] = []
        return d

    def apply_audio_config(self):
        self.audio_applied += 1
        return self.audio_status()

    def _restart_camera(self):
        self.camera.restart()

    def run_command(self, command):
        return "ok"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pkc-web-"))
    # 把「应用根目录」也挪到临时目录：否则 Config.internal_media_dir()
    # 会用仓库里的 media/，测试就会往工作区里写东西。
    config_mod.ROOT_DIR = tmp
    svc = Service(tmp)
    app = create_app(svc)
    client = app.test_client()

    print("pikrellcam-lite v2.8.0 本地接口集成测试")

    # ------------------------------------------------------------------
    print("\n[成像参数接口]")
    r = client.get("/api/imaging")
    check("GET /api/imaging 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("返回 values", "values" in d, list(d))
    check("返回 schema", isinstance(d.get("schema"), list))
    check("schema 有 14 项", len(d.get("schema", [])) == 14, len(d.get("schema", [])))
    check("返回 backend", d.get("backend") == "rpicam", d.get("backend"))
    check("rpicam 通路标记需要重启", d.get("requires_restart") is True)
    check("supported 覆盖全部参数",
          len(d.get("supported", {})) == 14, len(d.get("supported", {})))

    r = client.post("/api/imaging", json={"values": {"brightness": 60, "contrast": 10}})
    check("POST /api/imaging 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("亮度已保存", d["values"]["brightness"] == 60, d["values"]["brightness"])
    check("对比度已保存", d["values"]["contrast"] == 10, d["values"]["contrast"])
    check("rpicam 通路会重启相机", svc.camera.restarts == 1, svc.camera.restarts)
    check("配置里持久化了",
          svc.config.get("camera", "imaging", default={}).get("brightness") == 60)

    r = client.post("/api/imaging", json={"values": {"brightness": 9999}})
    check("越界值被钳制", r.get_json()["values"]["brightness"] == 100,
          r.get_json()["values"]["brightness"])
    r = client.post("/api/imaging", json={"values": {"awb": "乱写的模式"}})
    check("非法枚举回落默认", r.get_json()["values"]["awb"] == "auto",
          r.get_json()["values"]["awb"])
    r = client.post("/api/imaging", json={"values": {}})
    check("空提交不会炸", r.status_code == 200, str(r.status_code))

    # ------------------------------------------------------------------
    print("\n[循环录像接口]")
    r = client.get("/api/loop")
    check("GET /api/loop 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    for key in ("enabled", "recording", "segments", "bytes", "limit_bytes", "dir"):
        check("loop 状态含 " + key, key in d, list(d))
    check("默认未启用", d.get("enabled") is False, d.get("enabled"))
    check("目录指向媒体目录下的 loop", d.get("dir", "").endswith("loop"), d.get("dir"))

    r = client.post("/api/loop", json={"enabled": True, "segment_seconds": 45,
                                       "max_disk_percent": 22, "quality": 28})
    check("POST /api/loop 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("已启用", d.get("enabled") is True, d)
    check("段时长已保存", d.get("segment_seconds") == 45, d.get("segment_seconds"))
    check("磁盘上限已保存", d.get("max_disk_percent") == 22, d.get("max_disk_percent"))
    check("CRF 已保存", d.get("quality") == 28, d.get("quality"))

    r = client.post("/api/loop", json={"segment_seconds": 99999})
    check("段时长被钳制", r.get_json()["segment_seconds"] == 3600,
          r.get_json()["segment_seconds"])
    r = client.post("/api/loop", json={"max_disk_percent": 999})
    check("磁盘百分比被钳制", r.get_json()["max_disk_percent"] == 95,
          r.get_json()["max_disk_percent"])
    r = client.post("/api/loop", json={"segment_seconds": "不是数字"})
    check("非法数值不炸", r.status_code == 200, str(r.status_code))

    r = client.post("/api/loop", json={"action": "stop"})
    check("stop 动作关闭循环录像", r.get_json().get("enabled") is False, r.get_json())

    # ------------------------------------------------------------------
    print("\n[音频接口]")
    r = client.get("/api/audio")
    check("GET /api/audio 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    for k in ("enabled", "state", "device", "rate", "channels", "level",
              "devices", "configured_device", "bitrate"):
        check("返回 " + k, k in d, list(d))
    check("默认未启用音频", d.get("enabled") is False, d.get("enabled"))

    r = client.post("/api/audio", json={"enabled": True, "rate": 48000,
                                        "channels": 2, "device": "plughw:3,0"})
    check("POST /api/audio 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("音频已启用", d.get("enabled") is True, d.get("enabled"))
    check("采样率已保存", d.get("rate") == 48000, d.get("rate"))
    check("声道数已保存", d.get("channels") == 2, d.get("channels"))
    check("设备已保存", d.get("configured_device") == "plughw:3,0",
          d.get("configured_device"))
    check("应用配置被调用", svc.audio_applied == 1, svc.audio_applied)
    check("配置里持久化了",
          svc.config.get("record", "audio_enabled") is True,
          svc.config.get("record", "audio_enabled"))

    r = client.post("/api/audio", json={"rate": 999999, "channels": 9,
                                        "bitrate": 9999})
    d = r.get_json()
    check("采样率被钳制到上限", d.get("rate") == 48000, d.get("rate"))
    check("声道数被钳制到 2", d.get("channels") == 2, d.get("channels"))
    check("码率被钳制到上限", d.get("bitrate") == 256, d.get("bitrate"))

    r = client.post("/api/audio", json={"rate": "不是数字"})
    check("非法采样率回落默认", r.get_json().get("rate") == 16000,
          r.get_json().get("rate"))

    r = client.post("/api/audio", json={"buffer_seconds": 99999})
    check("缓冲时长被钳制到上限", r.get_json().get("buffer_seconds") == 900,
          r.get_json().get("buffer_seconds"))
    r = client.post("/api/audio", json={"buffer_seconds": 5})
    check("缓冲时长被钳制到下限", r.get_json().get("buffer_seconds") == 30,
          r.get_json().get("buffer_seconds"))
    r = client.post("/api/audio", json={"buffer_seconds": 240})
    check("缓冲时长已保存", r.get_json().get("buffer_seconds") == 240,
          r.get_json().get("buffer_seconds"))
    check("缓冲时长已持久化",
          svc.config.get("record", "audio_buffer_seconds") == 240,
          svc.config.get("record", "audio_buffer_seconds"))

    # ------------------------------------------------------------------
    print("\n[状态接口]")
    r = client.get("/api/state")
    check("GET /api/state 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("state 含 loop 段", "loop" in d, list(d))
    check("state.loop.enabled 可读", d["loop"].get("enabled") is False, d["loop"])
    check("state.media 仍带磁盘字段", "disk_free_bytes" in d.get("media", {}),
          list(d.get("media", {})))

    d = client.get("/api/state").get_json()
    check("state 含 audio 段", "audio" in d, list(d))
    check("state.audio 含运行状态",
          isinstance(d.get("audio"), dict) and "state" in d.get("audio", {}),
          str(d.get("audio")))
    check("state 含 record 段（录制倒计时数据）", "record" in d, list(d))
    rec = d.get("record") or {}
    check("state.record 含录制标记", "recording" in rec, str(rec))
    check("state.record 含剩余时间", "remaining" in rec, str(rec))
    check("空闲时不在录制中", rec.get("recording") is False, str(rec))

    # 静态资源不能缓存：否则升级后浏览器还拿旧的 app.js，界面上的新功能不出现
    r = client.get("/static/app.js")
    cc = (r.headers.get("Cache-Control") or "")
    check("静态资源不缓存",
          ("no-cache" in cc) or ("max-age=0" in cc) or ("no-store" in cc), cc)

    print("\n" + "=" * 52)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  ❌ " + f)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
