"""事件钩子：在运动开始/结束、延时摄影结束等时机执行外部命令。

对应官方 PiKrellCam 的 on_motion_begin / on_motion_end /
on_motion_preview_save / on_timelapse_end 事件命令。

命令里可以用占位符：
  {id} {video} {thumb} {time} {date} {duration} {algorithm} {region}
  {media_dir} {stills_dir} {videos_dir}
"""
from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .util import run_command


class Hooks:
    def __init__(self, config, log=None):
        self.config = config
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._history: list[dict] = []

    # ------------------------------------------------------------------
    def _render(self, cmd: str, payload: dict) -> str:
        media = self.config.media_dir()
        mapping = {
            "id": payload.get("id", ""),
            "video": payload.get("video", ""),
            "thumb": payload.get("thumb", ""),
            "duration": payload.get("duration", ""),
            "algorithm": payload.get("algorithm", ""),
            "region": payload.get("region", ""),
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "media_dir": str(media),
            "stills_dir": str(media / "stills"),
            "videos_dir": str(media / "videos"),
        }
        try:
            return cmd.format(**mapping)
        except Exception:
            return cmd

    def fire(self, name: str, payload: dict | None = None) -> None:
        cmd = (self.config.get("hooks", name, default="") or "").strip()
        if not cmd:
            return
        payload = payload or {}
        rendered = self._render(cmd, payload)
        entry = {"hook": name, "command": rendered, "time": time.time(), "status": "running"}
        with self._lock:
            self._history.insert(0, entry)
            del self._history[50:]

        def worker():
            rc, out, err = run_command(rendered, timeout=120)
            entry["status"] = "ok" if rc == 0 else "error"
            entry["rc"] = rc
            entry["stdout"] = out[-2000:]
            entry["stderr"] = err[-2000:]
            self.log(f"hook {name}: rc={rc} cmd={rendered}")

        threading.Thread(target=worker, name=f"hook-{name}", daemon=True).start()

    # ------------------------------------------------------------------
    def history(self) -> list[dict]:
        with self._lock:
            return list(self._history)
