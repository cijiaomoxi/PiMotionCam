"""pikrellcam-lite 原生加速模块（ctypes 加载 libpkc.so）。

设计原则：**加速是可选的，不是必需的**。
- 编译产物存在且能正常加载 → 走 C 内核；
- 编译失败 / 缺 .so / 平台不兼容 → 自动回落到纯 Python + numpy 实现，
  功能完全一致，只是慢一些。

对外暴露三个函数，语义与 core/camera.py、core/detect.py 中的原始实现等价：

    gray_ds(rgb, w, h, tw, th) -> np.ndarray[uint8]   降采样灰度
    detect(cur, prev, w, h, regions) -> list[RegionResult]
    jpeg(rgb, w, h, quality) -> bytes

其中 regions / RegionResult 的字段见本文件的 PKCRegion 结构体。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

__all__ = ["available", "backend", "gray_ds", "detect", "jpeg",
           "PKCRegion", "RegionResult", "ensure_built", "build_log"]

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "_pkc_native.c"
_LIB = _HERE / "_libpkc.so"

_lib = None
_load_error = ""
_build_attempted = False


# ----------------------------------------------------------------------
# ctypes 结构体
# ----------------------------------------------------------------------
class PKCRegion(ctypes.Structure):
    """与 C 侧 pkc_region_t 严格对应（字段顺序不能改）。"""
    _fields_ = [
        ("x0", ctypes.c_int),
        ("y0", ctypes.c_int),
        ("x1", ctypes.c_int),
        ("y1", ctypes.c_int),
        ("mag_limit", ctypes.c_int),
        ("noise_k", ctypes.c_int),
        ("count_limit", ctypes.c_float),
        ("consecutive", ctypes.c_int),
        ("hit_count", ctypes.c_int),
        ("hit", ctypes.c_int),
        ("ratio", ctypes.c_float),
        ("bx0", ctypes.c_int),
        ("by0", ctypes.c_int),
        ("bx1", ctypes.c_int),
        ("by1", ctypes.c_int),
        ("has_bbox", ctypes.c_int),
    ]


class RegionResult(ctypes.Structure):
    """检测结果（Python 侧只读回这几个字段）。"""
    _fields_ = [
        ("hit", ctypes.c_bool),
        ("ratio", ctypes.c_float),
        ("bbox", ctypes.c_int * 4),
        ("has_bbox", ctypes.c_bool),
        ("hit_count", ctypes.c_int),
    ]


# ----------------------------------------------------------------------
# 编译
# ----------------------------------------------------------------------
def _compiler() -> str:
    return os.environ.get("PKC_CC", "gcc")


def _version() -> str:
    """包版本号，用于编译进 .so 的版本信息。"""
    try:
        from . import __version__
        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"


def build(force: bool = False) -> tuple[bool, str]:
    """把 _pkc_native.c 编译成 _libpkc.so。返回 (成功, 日志)。"""
    if os.environ.get("PKC_NO_NATIVE"):
        return False, "已通过 PKC_NO_NATIVE 禁用原生加速"
    if not _SRC.exists():
        return False, f"源文件不存在: {_SRC}"
    if _LIB.exists() and not force:
        # 已有产物且比源文件新，直接复用
        if _LIB.stat().st_mtime >= _SRC.stat().st_mtime:
            return True, "复用已有编译产物"

    cc = _compiler()
    cmd = [
        cc, "-O3", "-fPIC", "-shared",
        "-fno-strict-aliasing",
        "-DPKC_VERSION_STR=\"pikrellcam-lite native %s\"" % _version(),
        "-o", str(_LIB), str(_SRC),
        "-ljpeg",
    ]
    # aarch64 上显式打开 NEON；其它架构交给编译器默认
    if platform_is_neon():
        cmd.insert(1, "-march=armv8-a+simd")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return False, f"找不到编译器: {cc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"编译异常: {exc}"

    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, f"编译失败 (rc={proc.returncode})\n{log.strip()}"
    return True, log.strip() or "编译成功"


def platform_is_neon() -> bool:
    import platform
    mach = platform.machine().lower()
    return mach.startswith("arm") or mach.startswith("aarch")


# ----------------------------------------------------------------------
# 加载
# ----------------------------------------------------------------------
def _load() -> ctypes.CDLL | None:
    global _lib, _load_error
    if _lib is not None:
        return _lib
    if not _LIB.exists():
        _load_error = f"编译产物不存在: {_LIB}"
        return None
    try:
        lib = ctypes.CDLL(str(_LIB))
    except OSError as exc:
        _load_error = f"加载失败: {exc}"
        return None

    u8p = ctypes.POINTER(ctypes.c_uint8)
    lib.pkc_gray_ds.argtypes = [u8p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, u8p]
    lib.pkc_gray_ds.restype = None

    lib.pkc_detect.argtypes = [u8p, u8p, ctypes.c_int, ctypes.c_int,
                               ctypes.POINTER(PKCRegion), ctypes.c_int]
    lib.pkc_detect.restype = ctypes.c_int

    lib.pkc_jpeg.argtypes = [u8p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             u8p, ctypes.c_int]
    lib.pkc_jpeg.restype = ctypes.c_int

    lib.pkc_native_version.restype = ctypes.c_char_p

    _lib = lib
    return _lib


def ensure_built() -> bool:
    """确保 .so 存在且已加载。返回是否可用。"""
    global _build_attempted
    if os.environ.get("PKC_NO_NATIVE"):
        return False
    if _lib is not None:
        return True
    if _build_attempted:
        return False
    _build_attempted = True
    ok, _log = build()
    if ok:
        return _load() is not None
    return False


def available() -> bool:
    """原生加速是否可用。"""
    return ensure_built()


def backend() -> str:
    """当前生效的后端名：native / python。"""
    return "native" if available() else "python"


def build_log() -> str:
    """最近一次编译/加载的诊断信息。"""
    if _lib is not None:
        try:
            return _lib.pkc_native_version().decode()
        except Exception:  # noqa: BLE001
            return "native"
    if _load_error:
        return _load_error
    ok, log = build()
    return log if not ok else "native"


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
def _ptr(arr: np.ndarray):
    return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))


def gray_ds(rgb: np.ndarray, w: int, h: int, tw: int, th: int) -> np.ndarray | None:
    """RGB888 -> (th, tw) uint8 灰度图。"""
    if not ensure_built():
        return None
    lib = _load()
    if lib is None:
        return None
    out = np.empty((th, tw), dtype=np.uint8)
    try:
        lib.pkc_gray_ds(_ptr(rgb), w, h, tw, th, _ptr(out))
    except Exception:  # noqa: BLE001
        return None
    return out


def detect(cur: np.ndarray, prev: np.ndarray, w: int, h: int,
           regions: list[dict]) -> list[RegionResult] | None:
    """
    批量检测。regions 每项形如：
        {x0, y0, x1, y1, mag_limit, noise_k, count_limit, consecutive, hit_count}
    返回与输入等长的结果列表；失败返回 None。
    """
    if not ensure_built():
        return None
    lib = _load()
    if lib is None:
        return None
    n = len(regions)
    if n == 0:
        return []

    arr = (PKCRegion * n)()
    for i, r in enumerate(regions):
        arr[i].x0 = int(r["x0"]); arr[i].y0 = int(r["y0"])
        arr[i].x1 = int(r["x1"]); arr[i].y1 = int(r["y1"])
        arr[i].mag_limit = int(r["mag_limit"])
        arr[i].noise_k = int(r["noise_k"])
        arr[i].count_limit = float(r["count_limit"])
        arr[i].consecutive = int(r["consecutive"])
        arr[i].hit_count = int(r.get("hit_count", 0))

    try:
        rc = lib.pkc_detect(_ptr(cur), _ptr(prev), w, h, arr, n)
    except Exception:  # noqa: BLE001
        return None
    if rc < 0:
        return None

    out: list[RegionResult] = []
    for i in range(n):
        a = arr[i]
        res = RegionResult()
        res.hit = bool(a.hit)
        res.ratio = float(a.ratio)
        res.has_bbox = bool(a.has_bbox)
        res.hit_count = int(a.hit_count)
        res.bbox = (int(a.bx0), int(a.by0), int(a.bx1), int(a.by1))
        out.append(res)
    return out


def jpeg(rgb: np.ndarray, w: int, h: int, quality: int) -> bytes | None:
    """RGB888 -> JPEG 字节。"""
    if not ensure_built():
        return None
    lib = _load()
    if lib is None:
        return None
    cap = w * h * 3 // 2 + 4096
    buf = np.empty(cap, dtype=np.uint8)
    try:
        n = lib.pkc_jpeg(_ptr(rgb), w, h, quality, _ptr(buf), cap)
    except Exception:  # noqa: BLE001
        return None
    if n <= 0:
        # 缓冲区不够，扩容重试一次
        cap = w * h * 3 + 65536
        buf = np.empty(cap, dtype=np.uint8)
        try:
            n = lib.pkc_jpeg(_ptr(rgb), w, h, quality, _ptr(buf), cap)
        except Exception:  # noqa: BLE001
            return None
        if n <= 0:
            return None
    return buf[:n].tobytes()
