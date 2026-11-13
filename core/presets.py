"""命名配置预设（对应官方 PiKrellCam 的 settings presets）。

一个预设是一份"部分配置"，激活时合并进当前配置：
分辨率/帧率变化会重启采集，其余项热生效。
"""
from __future__ import annotations

import copy
import threading
import time


class Presets:
    def __init__(self, config, state, on_camera_changed=None):
        self.config = config
        self.state = state
        self.on_camera_changed = on_camera_changed
        self._lock = threading.Lock()

    def list(self) -> dict:
        return self.config.get("presets", default={}) or {}

    def names(self) -> list[str]:
        return sorted(self.list().keys())

    def get(self, name: str):
        return self.list().get(name)

    def save(self, name: str, payload: dict) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("预设名称不能为空")
        presets = dict(self.list())
        presets[name] = copy.deepcopy(payload or {})
        # 整段替换：深合并会让被删掉/改小的旧预设内容残留下来
        self.config.set({"presets": presets}, replace=True)
        return presets

    def delete(self, name: str) -> bool:
        presets = dict(self.list())
        if name not in presets:
            return False
        presets.pop(name)
        # 整段替换：深合并会把刚删掉的预设从旧值里合回来（删除根本没生效）
        self.config.set({"presets": presets}, replace=True)
        if self.state.get("preset") == name:
            self.state.set("preset", "")
        return True

    def activate(self, name: str) -> dict:
        presets = self.list()
        if name not in presets:
            raise KeyError(f"预设不存在: {name}")
        payload = presets[name]
        with self._lock:
            old_res = self.config.get("camera", "resolution")
            old_fps = self.config.get("camera", "fps")
            self.config.set(payload)
            new_res = self.config.get("camera", "resolution")
            new_fps = self.config.get("camera", "fps")
            self.state.set("preset", name)
            if (old_res, old_fps) != (new_res, new_fps) and self.on_camera_changed:
                try:
                    self.on_camera_changed()
                except Exception:
                    pass
        return self.config.snapshot()
