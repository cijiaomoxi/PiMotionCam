"""通用小工具。"""
from __future__ import annotations

import io
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .media_stats import scan_media


def now_ts() -> float:
    return time.time()


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} PB"


def safe_filename(name: str, fallback: str = "file") -> str:
    keep = []
    for ch in str(name):
        if ch.isalnum() or ch in "-_. ":
            keep.append(ch)
        elif ch in "/\\":
            keep.append("-")
    out = "".join(keep).strip().replace(" ", "_")
    return out or fallback


def run_command(cmd: str, timeout: float = 60, cwd: str | None = None) -> tuple[int, str, str]:
    """执行 shell 命令，返回 (returncode, stdout, stderr)。"""
    if not cmd or not cmd.strip():
        return 0, "", ""
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def dir_size(path: Path) -> int:
    # Deliberately uncached: quota enforcement must use current file sizes.
    return scan_media(path)["disk_bytes"]


# ----------------------------------------------------------------------
# JPEG 相关
# ----------------------------------------------------------------------
def jpeg_size(data: bytes) -> tuple[int, int]:
    """只读 JPEG 头部取尺寸，不解码整帧。"""
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return (0, 0)


def _draft_scale(src: tuple[int, int], target: tuple[int, int]) -> tuple[int, int, int]:
    """挑一个能让 libjpeg 以缩放方式解码的最大倍率 s，返回 (s, dw, dh)。"""
    w, h = src
    tw, th = target
    for s in (8, 4, 2, 1):
        dw = -(-w // s)
        dh = -(-h // s)
        if dw >= tw and dh >= th:
            return s, dw, dh
    return 1, w, h


def jpeg_to_gray(data: bytes, target: tuple[int, int]) -> np.ndarray | None:
    """把 JPEG 字节流解码成指定尺寸的灰度 numpy 数组。

    关键优化：先 draft 让 libjpeg 直接以 1/2、1/4、1/8 比例做缩放解码，
    避免完整解码 720p。这让每帧的 CPU 开销降低一个数量级。
    """
    tw, th = target
    try:
        im = Image.open(io.BytesIO(data))
    except Exception:
        return None
    try:
        src = im.size
        _, dw, dh = _draft_scale(src, (tw, th))
        if (dw, dh) != src:
            im.draft("L", (dw, dh))
        im = im.convert("L")
        if im.size != (tw, th):
            im = im.resize((tw, th), Image.BILINEAR)
        return np.asarray(im, dtype=np.uint8)
    except Exception:
        return None
    finally:
        try:
            im.close()
        except Exception:
            pass


def jpeg_thumbnail(data: bytes, size: tuple[int, int], quality: int = 80) -> bytes | None:
    """生成缩略图 JPEG 字节。"""
    try:
        im = Image.open(io.BytesIO(data))
        im.draft("L", (size[0] * 4, size[1] * 4))
        im = im.convert("RGB")
        im.thumbnail(size, Image.BILINEAR)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception:
        return None


def jpeg_crop(data: bytes, box: tuple[int, int, int, int], out_size: tuple[int, int],
              quality: int = 85) -> bytes | None:
    """裁剪出运动目标区域并保存为 JPEG。box 为像素坐标 (x0,y0,x1,y1)。"""
    try:
        im = Image.open(io.BytesIO(data))
        x0, y0, x1, y1 = [int(v) for v in box]
        im = im.convert("RGB")
        im = im.crop((max(0, x0), max(0, y0), max(x1, x1 + 1), max(y1, y1 + 1)))
        if im.width < 8 or im.height < 8:
            return None
        im.thumbnail(out_size, Image.BILINEAR)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception:
        return None


# ----------------------------------------------------------------------
class Periodic(threading.Thread):
    """按固定间隔在后台执行回调的线程。"""

    def __init__(self, interval: float, fn, name: str = "periodic", daemon: bool = True):
        super().__init__(name=name, daemon=daemon)
        self.interval = max(0.05, interval)
        self.fn = fn
        self._stop = threading.Event()

    def run(self):
        while not self._stop.wait(self.interval):
            try:
                self.fn()
            except Exception:
                pass

    def stop(self):
        self._stop.set()


def tail_file(path: Path, lines: int = 200) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = 4096
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                step = min(block, size)
                size -= step
                fh.seek(size)
                data = fh.read(step) + data
            return data.decode("utf-8", "replace").splitlines()[-lines:]
    except Exception:
        return []
