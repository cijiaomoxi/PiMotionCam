#!/usr/bin/env python3
"""pikrellcam-lite —— 基于 libcamera/picamera2 的移动侦测录像服务。

对标官方 PiKrellCam 的全部网页功能：
  * 实时预览 + 浏览器端 OSD 叠加
  * 多运动区域图形化编辑、双算法并行灵敏度
  * 预录/补录、事件录像与缩略图（整帧 + 运动目标裁剪）
  * 命名配置预设、定时命令调度、FIFO 命令、事件钩子
  * 录像暂停、延时摄影、舵机云台
  * 媒体归档、系统日志、在线升级、密码保护

与官方的差异：官方依赖已被 Debian 13 删除的 MMAL 旧相机栈，
本实现使用 libcamera/picamera2，运动检测由帧差分替代硬件运动矢量。
"""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.app import AppService          # noqa: E402
from core.web import create_app          # noqa: E402


def _apply_model_defaults(service: AppService) -> None:
    """按树莓派型号选择合理的默认分辨率/帧率（Pi 3B 及更弱的设备自动降档）。"""
    model = ""
    try:
        model = Path("/proc/device-tree/model").read_text().strip("\x00")
    except Exception:
        pass
    model_l = model.lower()
    cfg = service.config.snapshot()
    # 用户已经自定义过就尊重用户设置
    if cfg.get("camera", {}).get("resolution") and cfg.get("camera", {}).get("_user_set"):
        return
    if "pi 3" in model_l or "pi 2" in model_l or "zero" in model_l:
        patch = {"camera": {"resolution": [640, 480], "fps": 8,
                            "detect_resolution": [320, 240], "detect_fps": 8}}
    else:
        patch = {"camera": {"resolution": [1280, 720], "fps": 10,
                            "detect_resolution": [320, 180], "detect_fps": 10}}
    service.config.set(patch)


def main() -> int:
    service = AppService()
    _apply_model_defaults(service)
    service.start()

    app = create_app(service)
    port = int(service.config.get("web", "port", default=8080))
    host = service.config.get("web", "host", default="0.0.0.0")

    def _shutdown(signum, frame):
        service.log(f"收到信号 {signum}，正在退出")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    service.log(f"web 服务启动: http://{host}:{port}")
    try:
        app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
    finally:
        service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
