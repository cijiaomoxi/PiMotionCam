"""命名配置预设（对应官方 PiKrellCam 的 settings presets）。

一个预设是一份"部分配置"，激活时合并进当前配置：
分辨率/帧率变化会重启采集，其余项热生效。
"""
from __future__ import annotations

import copy
import threading
import time


class Presets:
    def __init__(self, config, state, on_camera_changed=None, on_activate=None):
        self.config = config
        self.state = state
        self.on_camera_changed = on_camera_changed
        self.on_activate = on_activate
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
            old_camera = copy.deepcopy(self.config.get("camera"))
            self.config.set(payload)
            self.state.set("preset", name)
            if old_camera != self.config.get("camera") and self.on_camera_changed:
                try:
                    self.on_camera_changed()
                except Exception:
                    pass
            if self.on_activate:
                self.on_activate()
        return self.config.snapshot()

    def transfer(self, source, target, move=False, section=None):
        if not str(target or "").strip() or source == target:
            raise ValueError("Choose a different destination name")
        with self._lock:
            presets = copy.deepcopy(self.list())
            if source not in presets:
                raise KeyError(source)
            if section:
                if section not in presets[source]:
                    raise KeyError(section)
                presets.setdefault(target, {})[section] = copy.deepcopy(presets[source][section])
                if move:
                    del presets[source][section]
            else:
                if target in presets:
                    raise ValueError("The destination preset already exists")
                presets[target] = copy.deepcopy(presets[source])
                if move:
                    del presets[source]
            self.config.set({"presets": presets}, replace=True)
            if move and not section and self.state.get("preset") == source:
                self.state.set("preset", target)
            return presets
