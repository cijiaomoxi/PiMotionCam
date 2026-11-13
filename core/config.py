"""配置管理：默认值、加载/保存、热重载、路径解析。

配置文件为 JSON（config.json），同时兼容官方 PiKrellCam 的
~/.pikrellcam/pikrellcam.conf 风格（键值对），便于迁移用户习惯。
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import threading
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
# 版本发布目录结构：<ROOT>/releases/<版本号>/...
# 代码在 releases/ 里，但配置、媒体、日志、虚拟环境都放在 ROOT 下共享，
# 这样升级版本不会丢失录像，也不会让不同版本各写一份数据。
_PARENT = APP_DIR.parent
ROOT_DIR = _PARENT.parent if _PARENT.name == "releases" else APP_DIR

CONFIG_FILE = ROOT_DIR / "config.json"
PKC_DIR = Path.home() / ".pikrellcam"

DEFAULT_CONFIG = {
    "camera": {
        # 主码流分辨率与帧率（RGB888 主流 + 软件 JPEG 编码）
        "resolution": [1280, 720],
        "fps": 10,
        "buffer_count": 6,
        "rotation": 0,
        "flip": "none",          # none | horizontal | vertical | both
        "jpeg_quality": 72,      # 预览/录像帧的 JPEG 质量
        # 侦测用的降采样尺寸（直接从 RGB 数组步长采样得到）
        "detect_resolution": [320, 180],
        "detect_fps": 10,
        "exposure": -1,          # -1 = 自动
        # 选哪台摄像头：auto / libcamera 索引 / /dev/videoN
        "device": "auto",
        # 像素格式：auto 时按 CSI→RGB888、USB→MJPEG 的优先级自动协商
        "format": "auto",
        # CSI 也可以设为 "MJPEG"：走 rpicam-vid，由 ISP 硬件编码 JPEG，
        # 每帧编码零 CPU，JPEG 帧直接透传给预览与录像。
        # 设为 "RGB888" 则用 picamera2 取原始帧，软件编码 JPEG。
        # --- 抗"物体贴近镜头导致卡死"参数 ---
        # 取帧看门狗：超过该秒数没有新帧就重建采集管线
        "stall_timeout": 8.0,
        # 帧率下限：低于该值持续 stall_timeout 秒同样判定为卡死
        "min_fps": 0.5,
        # AE 测光模式：normal(整幅) | highlight(高光) | shadows(暗部) | custom
        # 注意 highlight 会让画面明显变暗（AE 改成按高光测光）。
        # 这里只是"安全旋钮"，真正的防卡死靠的是上面的看门狗 + 自动降级。
        "ae_constraint": "normal",
    },
    "motion": {
        "enabled": True,
        "startup_motion": True,
        # 双算法并行：far 面向远处小/慢目标，near 面向近处大目标
        "algorithms": {
            "far": {
                "enabled": True,
                "magnitude_limit": 12,   # 单像素灰度差阈值
                "count_limit": 0.006,     # 区域内变化像素占比阈值
                "consecutive_frames": 2,
                "noise_filter": 2,        # 邻域去噪半径（0 关闭）
            },
            "near": {
                "enabled": True,
                "magnitude_limit": 28,
                "count_limit": 0.02,
                "consecutive_frames": 2,
                "noise_filter": 3,
            },
        },
        # 任意数量/尺寸/位置的侦测区域，归一化 x,y,w,h
        "regions": [
            {"name": "全画面", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0, "enabled": True},
        ],
        "region_presets": {},
    },
    "record": {
        "pre_seconds": 5,
        "post_seconds": 8,
        "event_gap_seconds": 10,
        "max_event_seconds": 120,
        "max_disk_gb": 8,
        "encoder": "auto",     # auto | h264_v4l2m2m | libx264
        "quality": 23,
        "paused": False,
    },
    "timelapse": {
        "enabled": False,
        "period": 30,
        "hold": False,
    },
    "web": {
        "host": "0.0.0.0",
        "port": 8080,
        "password_hash": "",   # "sha256:<hex>"，空表示不启用密码保护
        "osd": True,
        "show_vectors": False,
        # 界面语言：auto（按浏览器 Accept-Language 自动选）/ zh-CN / en-US
        "language": "auto",
    },
    "media": {
        "dir": "",             # 空 = 使用应用目录下 media/；可改为 /mnt/usb 等
        "archive_target": "",  # 形如 user@host:/path，用于远程归档
    },
    "servo": {
        "enabled": False,
        "backend": "auto",     # auto | lgpio | rpi | servoblaster | none
        "pan_pin": 18,
        "tilt_pin": 17,
        "pan_min": 0,
        "pan_max": 180,
        "tilt_min": 0,
        "tilt_max": 180,
        "smooth_ms": 0,        # 平滑移动时间
        "positions": [
            {"name": "中", "pan": 90, "tilt": 90},
            {"name": "左", "pan": 30, "tilt": 90},
            {"name": "右", "pan": 150, "tilt": 90},
        ],
    },
    "hooks": {
        "on_motion_begin": "",
        "on_motion_end": "",
        "on_motion_preview_save": "",
        "on_timelapse_end": "",
    },
    "schedules": [],
    "presets": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """override 覆盖 base，dict 递归合并。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class Config:
    """线程安全的配置容器，支持文件热重载。"""

    def __init__(self, path: Path = CONFIG_FILE):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = copy.deepcopy(DEFAULT_CONFIG)
        self._mtime = 0.0
        self._version = 0
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> dict:
        with self._lock:
            data = {}
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text())
                except Exception:
                    data = {}
            self._data = _deep_merge(DEFAULT_CONFIG, data)
            try:
                self._mtime = self.path.stat().st_mtime
            except OSError:
                self._mtime = 0.0
            self._version += 1
            return self._data

    def reload_if_changed(self) -> bool:
        """检测到配置文件被外部修改则重载，返回是否发生重载。"""
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        if mtime and mtime != self._mtime:
            self.load()
            return True
        return False

    def save(self, patch: dict | None = None, replace: bool = False) -> dict:
        """写配置并落盘。

        replace=False（默认）→ 深合并，patch 里没提到的键保持原样。
        replace=True          → patch 里的一级键**整体替换**，不做深合并。
        """
        with self._lock:
            if patch:
                if replace:
                    for k, v in patch.items():
                        self._data[k] = copy.deepcopy(v)
                else:
                    self._data = _deep_merge(self._data, patch)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
            os.replace(tmp, self.path)
            try:
                self._mtime = self.path.stat().st_mtime
            except OSError:
                pass
            self._version += 1
            return copy.deepcopy(self._data)

    def reset(self) -> dict:
        with self._lock:
            self._data = copy.deepcopy(DEFAULT_CONFIG)
            return self.save()

    # ------------------------------------------------------------------
    def get(self, *path, default=None):
        """cfg.get("motion", "algorithms", "far") 形式取值。"""
        with self._lock:
            node = self._data
            for key in path:
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return copy.deepcopy(node) if isinstance(node, (dict, list)) else node

    def set(self, patch: dict, replace: bool = False) -> dict:
        """写配置。

        replace=True 时，patch 里的一级键整体替换而不深合并。
        """
        return self.save(patch, replace=replace)

    def replace_value(self, section: str, key: str, value) -> dict:
        """整段替换某个配置节里的某一个键（不做深合并）。

        「删除字典型配置里的某一项」必须走这里：深合并会把被删掉的键
        从旧值里合回来，导致删除接口返回成功但实际没删掉。
        """
        with self._lock:
            node = self._data.get(section)
            node = copy.deepcopy(node) if isinstance(node, dict) else {}
            node[key] = copy.deepcopy(value)
            self._data[section] = node
            return self.save()

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    @property
    def version(self) -> int:
        return self._version

    # ------------------------------------------------------------------
    def media_dir(self) -> Path:
        raw = (self.get("media", "dir") or "").strip()
        if raw:
            p = Path(raw).expanduser()
            return p if p.is_absolute() else (ROOT_DIR / p)
        return ROOT_DIR / "media"

    def media_sub(self, name: str) -> Path:
        return self.media_dir() / name

    def ensure_dirs(self) -> None:
        for sub in ("videos", "stills", "timelapse"):
            self.media_sub(sub).mkdir(parents=True, exist_ok=True)
        PKC_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------
def hash_password(password: str) -> str:
    return "sha256:" + hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_password(stored: str, password: str) -> bool:
    if not stored:
        return True
    if not password:
        return False
    return hmac.compare_digest(stored, hash_password(password))
