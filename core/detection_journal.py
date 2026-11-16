"""Bounded, asynchronous detection statistics and nonblocking FIFO output."""

from __future__ import annotations
import csv
import json
import os
import queue
import stat
import threading
import time


class DetectionJournal:
    def __init__(self, config, log=None):
        self.config, self.log = config, log or (lambda *a: None)
        self._queue = queue.Queue(maxsize=32)
        self._thread = None
        self._last = False
        self._stamp = 0.0
        self._lock = threading.Lock()

    def publish(self, detection):
        options = self.config.get("motion", "output", default={}) or {}
        if not any(options.values()):
            return
        now = time.time()
        changed = detection.motion != self._last
        if not changed and now - self._stamp < 1:
            return
        self._last, self._stamp = detection.motion, now
        row = {
            "time": now,
            "motion": detection.motion,
            "algorithm": detection.algorithm,
            "region": detection.region,
            "ratio": detection.ratio,
            "analysis": detection.analysis,
        }
        try:
            self._queue.put_nowait((row, options, changed))
        except queue.Full:
            return
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._worker, daemon=True, name="detection-output"
                )
                self._thread.start()

    def _worker(self):
        while True:
            try:
                row, options, changed = self._queue.get(timeout=2)
            except queue.Empty:
                return
            try:
                folder = self.config.path.parent / "logs"
                folder.mkdir(parents=True, exist_ok=True)
                encoded = (json.dumps(row, ensure_ascii=False) + "\n").encode()
                if options.get("csv"):
                    p = folder / "motion.csv"
                    self._rotate(p)
                    fresh = not p.exists()
                    with open(p, "a", newline="") as fh:
                        writer = csv.writer(fh)
                        if fresh:
                            writer.writerow(
                                [
                                    "time",
                                    "motion",
                                    "algorithm",
                                    "region",
                                    "ratio",
                                    "direction",
                                    "rejected_pixels",
                                ]
                            )
                        writer.writerow(
                            [
                                row["time"],
                                row["motion"],
                                row["algorithm"],
                                row["region"],
                                row["ratio"],
                                row["analysis"].get("direction", ""),
                                row["analysis"].get("rejected_pixels", 0),
                            ]
                        )
                if options.get("events") and changed:
                    p = folder / "motion-events.jsonl"
                    self._rotate(p)
                    with open(p, "ab") as fh:
                        fh.write(encoded)
                if options.get("fifo"):
                    p = folder / "motion.fifo"
                    if not p.exists():
                        os.mkfifo(p, 0o600)
                    if stat.S_ISFIFO(p.stat().st_mode):
                        fd = os.open(p, os.O_WRONLY | os.O_NONBLOCK)
                        try:
                            os.write(fd, encoded[:4095])
                        finally:
                            os.close(fd)
            except OSError as exc:
                # ENXIO means there is no FIFO reader; it is not an error.
                if exc.errno not in (6, 11, 32):
                    self.log("detection output: %s" % exc)
            finally:
                self._queue.task_done()

    @staticmethod
    def _rotate(path):
        if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
            path.replace(path.with_suffix(path.suffix + ".1"))
