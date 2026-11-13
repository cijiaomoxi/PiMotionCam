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

    print("pikrellcam-lite v2.7.0 本地接口集成测试")

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
    print("\n[状态接口]")
    r = client.get("/api/state")
    check("GET /api/state 返回 200", r.status_code == 200, str(r.status_code))
    d = r.get_json()
    check("state 含 loop 段", "loop" in d, list(d))
    check("state.loop.enabled 可读", d["loop"].get("enabled") is False, d["loop"])
    check("state.media 仍带磁盘字段", "disk_free_bytes" in d.get("media", {}),
          list(d.get("media", {})))

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
