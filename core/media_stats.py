"""Single-pass media inventory and a short-lived cache for display statistics.

Disk guards always call scan_media/dir_size directly. Cached values are for the
dashboard only; filesystem free space and mount checks remain live.
"""
from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path


def scan_media(root: Path) -> dict:
    root = Path(root)
    result = {"disk_bytes": 0, "videos": 0, "stills": 0}
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                            continue
                        info = entry.stat()
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        result["disk_bytes"] += info.st_size
                        if directory == root / "videos" and entry.name.endswith(".mp4"):
                            result["videos"] += 1
                        elif directory == root / "stills" and entry.name.endswith(".jpg"):
                            result["stills"] += 1
                    except OSError:
                        continue  # Recording cleanup/unplug can race the scan.
        except OSError:
            continue
    return result


def list_media(folder: Path, suffix: str) -> list[dict]:
    """Read each entry's metadata once, tolerating concurrent deletes/muxing."""
    items = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.name.endswith(suffix):
                    continue
                try:
                    info = entry.stat()
                    if stat.S_ISREG(info.st_mode):
                        items.append({"name": entry.name, "size": info.st_size,
                                      "mtime": info.st_mtime})
                except OSError:
                    continue
    except OSError:
        pass
    items.sort(key=lambda item: -item["mtime"])
    return items


class MediaStatsCache:
    def __init__(self, max_age: float = 3.0):
        self.max_age = max_age
        self._lock = threading.Lock()
        self._key = None
        self._expires = 0.0
        self._value = {}

    def invalidate(self):
        with self._lock:
            self._key = None

    def snapshot(self, root: Path) -> dict:
        root = Path(root)
        try:
            info = root.stat()
            key = (str(root), info.st_dev, info.st_ino)
        except OSError:
            key = (str(root), None, None)
        with self._lock:
            if self._key != key or time.monotonic() >= self._expires:
                self._value = scan_media(root)
                self._key = key
                self._expires = time.monotonic() + self.max_age
            return dict(self._value)
