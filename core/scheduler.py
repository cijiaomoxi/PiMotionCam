"""定时命令调度 + FIFO 命令接口。

对应官方 PiKrellCam 的 at-commands.conf：
  * 命令可按"星期 + 时刻"触发，也可按固定分钟间隔触发
  * 命令可以是内部命令（@record on）、FIFO 命令或任意 shell 命令
  * 列表热重载，改完文件立即生效，无需重启
  * 外部脚本可以通过 FIFO 写入命令
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .config import PKC_DIR

WEEKDAYS = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def _parse_days(spec: str) -> set[int]:
    """解析 'Mon-Fri' / 'Mon,Wed' / '*' → 星期集合。"""
    spec = (spec or "*").strip().lower()
    if spec in ("*", "all", "daily", "每天"):
        return set(range(7))
    out: set[int] = set()
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ia, ib = WEEKDAYS.get(a.strip()[:3]), WEEKDAYS.get(b.strip()[:3])
            if ia is None or ib is None:
                continue
            if ia <= ib:
                out.update(range(ia, ib + 1))
            else:
                out.update(range(ia, 7))
                out.update(range(0, ib + 1))
        else:
            v = WEEKDAYS.get(part[:3])
            if v is not None:
                out.add(v)
    return out or set(range(7))


class Scheduler:
    def __init__(self, config, command_handler, log=None, fifo_path: Path | None = None):
        self.config = config
        self.command_handler = command_handler
        self.log = log or (lambda *a, **k: None)
        self.fifo_path = Path(fifo_path) if fifo_path else (PKC_DIR / "commands.fifo")
        self._thread: threading.Thread | None = None
        self._fifo_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_runs: dict[str, str] = {}
        self._entries: list[dict] = []
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> list[dict]:
        """从配置与 at-commands.conf 重新载入命令表。"""
        entries: list[dict] = []
        for e in self.config.get("schedules", default=[]) or []:
            if isinstance(e, dict) and e.get("command"):
                entries.append(dict(e))
        entries.extend(self._load_conf_file())
        with self._lock:
            self._entries = entries
        self.log(f"scheduler: loaded {len(entries)} entries")
        return entries

    def _load_conf_file(self) -> list[dict]:
        path = PKC_DIR / "at-commands.conf"
        if not path.exists():
            return []
        out = []
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue
                days, when, command = parts[0], parts[1], parts[2].strip().strip('"')
                entry = {"days": days, "time": when, "command": command, "source": str(path)}
                if ":" not in when:
                    entry["interval_minutes"] = int(when) if when.isdigit() else 1
                out.append(entry)
        except Exception:
            pass
        return out

    def entries(self) -> list[dict]:
        with self._lock:
            items = list(self._entries)
        # 统一带上 index 与 uid，方便前端按位置删除/更新
        for i, e in enumerate(items):
            e.setdefault("index", i)
            e.setdefault("uid", f"e{i}")
        return items

    # ------------------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self._start_fifo()

    def stop(self):
        self._stop.set()

    def _start_fifo(self):
        try:
            PKC_DIR.mkdir(parents=True, exist_ok=True)
            if not self.fifo_path.exists():
                os.mkfifo(self.fifo_path, 0o660)
            self._fifo_thread = threading.Thread(target=self._fifo_loop, name="fifo", daemon=True)
            self._fifo_thread.start()
        except Exception as exc:
            self.log(f"fifo setup failed: {exc}")

    def _fifo_loop(self):
        while not self._stop.is_set():
            try:
                with open(self.fifo_path, "r") as fh:
                    for line in fh:
                        if self._stop.is_set():
                            break
                        cmd = line.strip()
                        if cmd:
                            self.execute(cmd)
            except Exception:
                time.sleep(2)

    # ------------------------------------------------------------------
    def execute(self, command: str) -> str:
        cmd = (command or "").strip()
        if not cmd:
            return ""
        if cmd.startswith("@"):
            cmd = cmd[1:]
        try:
            res = self.command_handler(cmd)
            return res if isinstance(res, str) else ("ok" if res is not None else "")
        except Exception as exc:  # noqa: BLE001
            self.log(f"command failed: {cmd}: {exc}")
            return f"error: {exc}"

    # ------------------------------------------------------------------
    def _loop(self):
        while not self._stop.wait(10):
            try:
                self.config.reload_if_changed()
                self.reload()
                self._tick()
            except Exception:
                pass

    def _tick(self):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        now_min = now.hour * 60 + now.minute
        with self._lock:
            entries = list(self._entries)
        for idx, e in enumerate(entries):
            if e.get("enabled") is False:
                continue
            key = f"{idx}:{e.get('command')}"
            if "interval_minutes" in e:
                interval = max(1, int(e.get("interval_minutes", 1)))
                last = self._last_runs.get(key)
                last_min = None
                if last:
                    try:
                        lt = datetime.strptime(last, "%Y-%m-%d %H:%M")
                        last_min = lt.hour * 60 + lt.minute
                    except Exception:
                        last_min = None
                if last_min is None or (now_min - last_min) >= interval:
                    self._last_runs[key] = now.strftime("%Y-%m-%d %H:%M")
                    self.execute(e["command"])
                continue
            when = str(e.get("time", ""))
            if ":" not in when:
                continue
            try:
                hh, mm = [int(x) for x in when.split(":")[:2]]
            except Exception:
                continue
            if now.hour != hh or now.minute != mm:
                continue
            if now.weekday() not in _parse_days(e.get("days", "*")):
                continue
            if self._last_runs.get(key) == today:
                continue
            self._last_runs[key] = today
            self.execute(e["command"])

    # ------------------------------------------------------------------
    def save_entry(self, entry: dict) -> list[dict]:
        entries = self.config.get("schedules", default=[]) or []
        entries = [e for e in entries if isinstance(e, dict)]
        uid = entry.get("uid")
        idx = entry.get("index")
        clean = {k: v for k, v in entry.items() if k not in ("index",)}
        if not clean.get("uid"):
            clean["uid"] = uid or uuid.uuid4().hex[:8]
        target = None
        if uid:
            for i, e in enumerate(entries):
                if e.get("uid") == uid:
                    target = i
                    break
        if target is None and idx is not None:
            try:
                target = int(idx)
                if target < 0 or target >= len(entries):
                    target = None
            except Exception:
                target = None
        if target is None:
            entries.append(clean)
        else:
            entries[target] = {**entries[target], **clean}
        self.config.set({"schedules": entries})
        self.reload()
        return self.entries()

    def delete_entry(self, index) -> bool:
        """index 可以是数组下标，也可以是稳定的 uid。"""
        entries = self.config.get("schedules", default=[]) or []
        target = None
        if isinstance(index, str) and not index.isdigit():
            for i, e in enumerate(entries):
                if e.get("uid") == index:
                    target = i
                    break
        if target is None:
            try:
                target = int(index)
            except Exception:
                return False
        if target < 0 or target >= len(entries):
            return False
        entries.pop(target)
        self.config.set({"schedules": entries})
        self.reload()
        return True
