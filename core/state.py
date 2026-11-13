"""运行时共享状态（线程安全）。"""
from __future__ import annotations

import threading
import time


class RuntimeState:
    FIELDS = {
        "running": False,
        "camera_ready": False,
        "motion": False,
        "fps": 0.0,
        "detect_fps": 0.0,
        "frame_size": [0, 0],
        "frame_bytes": 0,
        "events_total": 0,
        "recording": False,
        "record_paused": False,
        "timelapse_running": False,
        "servo_enabled": False,
        "servo_position": {"pan": None, "tilt": None},
        "preset": "",
        "error": None,
        "started_at": None,
        "uptime": 0,
        "last_frame_at": None,
        "detection": {},
        # 媒体存储状态（外部存储拔出会把 available 置 False）
        "storage_available": True,
        "storage_fallback": False,
        "storage_path": "",
        "storage_reason": "",
        # 磁盘监测：目标文件系统的真实剩余空间
        "disk_total_bytes": 0,
        "disk_free_bytes": 0,
        "disk_used_bytes": 0,
        "disk_low": False,
        "disk_reason": "",
        # 循环录像（loop）
        "loop_recording": False,
        "loop_segments": 0,
        "loop_bytes": 0,
        "loop_yielded": False,
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(self.FIELDS)
        self._data["started_at"] = None

    def update(self, **kwargs):
        with self._lock:
            self._data.update(kwargs)
            if self._data.get("started_at"):
                self._data["uptime"] = round(time.time() - self._data["started_at"], 1)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def snapshot(self) -> dict:
        with self._lock:
            data = dict(self._data)
            if data.get("started_at"):
                data["uptime"] = round(time.time() - data["started_at"], 1)
            return data
