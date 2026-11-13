"""摄像头采集层。

同时支持两类摄像头，走两条不同的采集通路：

1. **树莓派 CSI 摄像头** —— 走 libcamera / picamera2（`Picamera2Backend`）
   * Debian / Raspberry Pi OS 的 libcamera 只带 RPi 专用管线处理器，
     **不含 u8vidcam 处理器**，所以 USB 摄像头 libcamera 根本发现不了。

2. **USB (UVC) 摄像头** —— 走 ffmpeg + V4L2（`V4L2Backend`）
   * 用 ffmpeg 直接抓 /dev/videoN，输出 MJPEG 字节流。
   * 摄像头原生支持 MJPEG 时用 `-c:v copy` 零转码直通，CPU 开销几乎为零；
     只支持 YUYV 时由 ffmpeg 软件转码成 MJPEG。
   * 这样 USB 通路拿到的也是 JPEG 帧，和 CSI 的压缩格式路径完全一致，
     预览零开销、侦测用 PIL draft 缩放解码。

性能与健壮性要点（均为实机验证结论）：
  * 千万别写 np.dot(frame[..., :3], [0.299, 0.587, 0.114])：
    numpy 对 3 维数组与 1 维向量做 dot 会走批量矩阵乘路径，
    720p 下单帧要几十秒，足以把采集线程彻底卡死。
  * 侦测一律"先降采样再转灰度"。
  * 取帧走 Job.get_result(timeout=...) 硬超时，传感器异常时线程不会永久挂死。
  * CSI 有两条通路，可用 camera.format 切换：
      - "MJPEG"  → rpicam-vid + ISP 硬件 JPEG 编码，JPEG 字节直传
      - "RGB888" → picamera2 取原始帧，本地 C 内核（libjpeg-turbo）编码
  * **rpicam-vid 必须显式加 `-t 0`**：它的 `--timeout` 默认是 5 秒，
    含义是"程序最多跑 5 秒"。不加的话采集进程会在第 5 秒自行退出并打印
    "Halting: reached timeout of 5000 milliseconds."，
    看起来极像"相机管线卡死"，实际只是程序时限到了。
    加了 -t 0 实测 45 秒 436 帧、精确 10.00 fps 不间断。
"""
from __future__ import annotations

import io
import os
import queue
import shutil
import subprocess
import threading
import time
import collections

import numpy as np
from PIL import Image

from . import imaging
from . import native

try:
    from picamera2 import Picamera2
except Exception:  # noqa: BLE001
    Picamera2 = None

# CSI 摄像头优先 RGB888；USB 摄像头优先 MJPEG（硬件压缩，CPU 最低）
CSI_FORMATS = ["RGB888", "XBGR8888", "YUV420", "YUYV", "MJPEG"]
USB_FORMATS = ["MJPEG", "RGB888", "XBGR8888", "YUYV", "YUV420"]

COMPRESSED = {"MJPEG"}

# 这些是树莓派自己的媒体设备，不是 USB 摄像头
_PLATFORM_HINTS = ("bcm2835", "unicam", "rpi-hevc", "vchiq")


# ----------------------------------------------------------------------
def _v4l2_devices() -> list[dict]:
    """列出真正的 USB 摄像头节点（排除树莓派平台设备）。"""
    out = []
    if not shutil.which("v4l2-ctl"):
        return out
    try:
        r = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, timeout=8)
        text = r.stdout.decode("utf-8", "replace")
        name = ""
        for line in text.splitlines():
            if line and not line[0].isspace():
                name = line.strip()
            else:
                dev = line.strip()
                if not dev.startswith("/dev/video"):
                    continue
                if any(h in name.lower() for h in _PLATFORM_HINTS):
                    continue
                out.append({"id": dev, "model": name or dev})
    except Exception:
        pass
    return out


def _libcamera_cameras() -> list[dict]:
    out = []
    try:
        from picamera2 import Picamera2 as _P2
        for info in _P2.global_camera_info():
            cid = str(info.get("Id", ""))
            is_rpi = cid.startswith("/base/soc")
            out.append({
                "index": int(info.get("Num", len(out))),
                "id": cid,
                "model": str(info.get("Model", "") or cid),
                "type": "csi" if is_rpi else "usb",
                "backend": "libcamera",
                "device": "",
            })
    except Exception:
        pass
    return out


def list_cameras() -> list[dict]:
    """枚举全部可用摄像头：libcamera 能看到的 + 仅 V4L2 能看到的。"""
    cams = _libcamera_cameras()
    seen_v4l2 = {c["id"] for c in cams if c.get("backend") == "v4l2"}
    for dev in _v4l2_devices():
        if dev["id"] in seen_v4l2:
            continue
        cams.append({
            "index": len(cams),
            "id": dev["id"],
            "model": dev["model"],
            "type": "usb",
            "backend": "v4l2",
            "device": dev["id"],
        })
    return cams


# ----------------------------------------------------------------------
class V4L2Backend:
    """用 ffmpeg 从 V4L2 设备读取 JPEG 帧。"""

    def __init__(self, device: str, width: int, height: int, fps: int):
        self.device = device
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: queue.Queue = queue.Queue(maxsize=30)
        self.input_format = "mjpeg"
        self.passthrough = True
        self.error = None

    # --------------------------------------------------------------
    def probe(self) -> dict:
        """查询设备支持的像素格式。"""
        info = {"formats": [], "input_format": "mjpeg", "passthrough": True}
        if not shutil.which("v4l2-ctl"):
            return info
        try:
            r = subprocess.run(["v4l2-ctl", "-d", self.device, "--list-formats-ext"],
                               capture_output=True, timeout=8)
            text = r.stdout.decode("utf-8", "replace")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("[") and "'" in line:
                    fmt = line.split("'")[1]
                    info["formats"].append(fmt)
        except Exception:
            pass
        fmts = [f.upper() for f in info["formats"]]
        if "MJPG" in fmts or "MJPEG" in fmts:
            info["input_format"] = "mjpeg"
            info["passthrough"] = True
        elif "YUYV" in fmts:
            info["input_format"] = "yuyv"
            info["passthrough"] = False
        elif "YVYU" in fmts:
            info["input_format"] = "yvyu"
            info["passthrough"] = False
        elif "UYVY" in fmts:
            info["input_format"] = "uyvy"
            info["passthrough"] = False
        return info

    # --------------------------------------------------------------
    def start(self):
        self.probe()
        self.input_format = self.probe().get("input_format", "mjpeg")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", self.input_format,
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps),
            "-i", self.device,
            "-f", "image2pipe",
        ]
        cmd += ["-c:v", "copy"] if self.passthrough else ["-c:v", "mjpeg", "-q:v", "5"]
        cmd += ["-"]
        self._stop.clear()
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._thread = threading.Thread(target=self._reader, name="v4l2-reader", daemon=True)
        self._thread.start()

    def _reader(self):
        proc = self.proc
        if not proc or not proc.stdout:
            return
        buf = bytearray()
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s == -1:
                        if len(buf) > 1 << 20:
                            del buf[:-2]
                        break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e == -1:
                        if s > 0:
                            del buf[:s]
                        break
                    frame = bytes(buf[s:e + 2])
                    del buf[:e + 2]
                    try:
                        self._q.put_nowait(frame)
                    except queue.Full:
                        try:
                            self._q.get_nowait()
                        except queue.Empty:
                            pass
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"

    def read(self, timeout: float = 8.0) -> bytes | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            if self.error:
                raise RuntimeError(self.error)
            if self.proc and self.proc.poll() is not None:
                err = ""
                try:
                    err = self.proc.stderr.read().decode("utf-8", "replace")[-300:]
                except Exception:
                    pass
                raise RuntimeError(f"ffmpeg 退出（code={self.proc.returncode}）{err}")
            raise TimeoutError(f"V4L2 取帧超时（{timeout}s）")

    def stop(self):
        self._stop.set()
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


# ----------------------------------------------------------------------
class RpiVidBackend:
    """用 rpicam-vid 采集 CSI 摄像头，由 ISP 硬件编码成 MJPEG。

    与 V4L2Backend 同构：对外只暴露 read() -> JPEG 字节。

    为什么值得多这一条通路：
      * libcamera 的 Picamera2 视频配置拒绝 JPEG 输出格式
        （"Bad format JPEG in stream main"），软件 JPEG 编码要占 12.5ms/帧；
      * rpicam-vid 是官方 app，它会正确配置 raw 副流 + lores 流，
        让 ISP 的硬件 JPEG 编码器工作，**每帧编码零 CPU**；
      * 拿到的 JPEG 帧可直接透传给网页预览与 ffmpeg 录像，
        不需要任何二次编码或色彩空间转换。

    注意：必须让 rpicam-vid 保持默认的 raw 流（不要加 --no-raw），
    否则 pipeline 前端会超时，传感器会卡死到需要断电才能复位。
    """

    def __init__(self, width: int, height: int, fps: int, quality: int = 50,
                 rotation: int = 0, flip: str = "none",
                 extra_args: list[str] | None = None):
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.quality = int(quality)
        self.rotation = int(rotation or 0) % 360
        self.flip = str(flip or "none").lower()
        # 成像参数（亮度/对比度/白平衡…）在 rpicam-vid 上是**启动参数**，
        # 只能靠命令行带进去；改参数就意味着要重建这个进程。
        self.extra_args = list(extra_args or [])
        # 成像参数是否真的被 ISP 接受了（启动失败时会退回"不带参数"）
        self.imaging_applied = bool(self.extra_args)
        self.proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._err_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._q: queue.Queue = queue.Queue(maxsize=30)
        self._stderr: collections.deque = collections.deque(maxlen=60)
        self.error = None

    # --------------------------------------------------------------
    @staticmethod
    def available() -> bool:
        return shutil.which("rpicam-vid") is not None

    def start(self, retries: int = 8, wait: float = 1.5):
        """启动 rpicam-vid。

        从 picamera2 切过来时，libcamera 的 pipeline handler 释放是异步的，
        rpicam-vid 可能在几百毫秒内报 "Pipeline handler in use by another
        process"。这里带退避重试，把切换的时序问题吃掉。

        **成像参数是启动参数**，万一某个值不被这版 rpicam-vid 接受，
        整个采集进程就起不来了——那等于把相机彻底弄死。
        所以这里再兜一层：带成像参数启动失败时，**去掉成像参数再试一次**，
        宁可少几个参数也不能没有画面。
        """
        last = ""
        for attempt in range(retries):
            self._spawn()
            time.sleep(1.2)
            if self.proc and self.proc.poll() is None:
                return
            last = self._stderr_tail()
            if "in use" in last.lower() or "another process" in last.lower():
                if attempt < retries - 1:
                    time.sleep(wait)
                    continue
            break
        if self.extra_args:
            self.extra_args = []
            self.imaging_applied = False
            self.log("rpicam-vid 带成像参数启动失败，去掉成像参数重试：%s" % last[-200:])
            self.start(retries=2, wait=wait)
            return
        raise RuntimeError(f"rpicam-vid 启动失败（code={self.proc.returncode if self.proc else '?'}）：{last[-300:]}")

    def _spawn(self):
        # 回收上一轮遗留的进程，避免留下僵尸进程占着相机
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
                except Exception:
                    pass
            self.proc = None

        cmd = [
            "rpicam-vid",
            "--codec", "mjpeg",
            "--width", str(self.width),
            "--height", str(self.height),
            "--framerate", str(self.fps),
            "--quality", str(self.quality),
            # -t 0 = 永不限时。**这一条是必须的**：rpicam-vid 的 --timeout
            # 默认值是 5 秒，含义是"程序最多跑 5 秒"。不加这个参数的话，
            # 采集进程会在第 5 秒自行退出并打印
            # "Halting: reached timeout of 5000 milliseconds."，
            # 看起来极像"相机管线卡死"，实际上只是程序时限到了。
            # 加了 -t 0 后实测 45 秒 436 帧、精确 10.00 fps 不间断。
            "-t", "0",
            # 无头运行（systemd 里没有 X/Wayland），否则会尝试开预览窗口
            "--nopreview",
            # 立刻把编码好的数据刷出去，降低预览延迟
            "--flush",
            "-o", "-",
        ]
        # 旋转 / 镜像由 ISP 直接做，不额外消耗 CPU。
        # 注意 rpicam-vid 只支持 0/180，90/270 需要 transpose（ISP 不支持），
        # 那种情况由 Camera 层改走 RGB888 通路做软件旋转。
        if self.rotation in (0, 180):
            cmd += ["--rotation", str(self.rotation)]
        if self.flip in ("horizontal", "both"):
            cmd.append("--hflip")
        if self.flip in ("vertical", "both"):
            cmd.append("--vflip")
        # 成像参数：亮度/对比度/饱和/锐度/降噪/曝光/白平衡/ISO/快门/变焦
        cmd += self.extra_args
        self._stop.clear()
        self.error = None
        self._stderr = collections.deque(maxlen=60)
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self._thread = threading.Thread(target=self._reader, name="rpivid-reader", daemon=True)
        self._thread.start()
        # rpicam-vid 每帧都会往 stderr 打一行日志，不读走的话管道缓冲满
        # 会把进程卡住，所以单独起线程消费 stderr
        self._err_thread = threading.Thread(target=self._stderr_reader, name="rpivid-stderr", daemon=True)
        self._err_thread.start()

    def _stderr_reader(self):
        proc = self.proc
        if not proc or not proc.stderr:
            return
        try:
            for line in iter(proc.stderr.readline, b""):
                self._stderr.append(line.decode("utf-8", "replace").rstrip())
        except Exception:
            pass

    def _stderr_tail(self) -> str:
        return "\n".join(self._stderr)

    def _reader(self):
        proc = self.proc
        if not proc or not proc.stdout:
            return
        buf = bytearray()
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                while True:
                    s = buf.find(b"\xff\xd8")
                    if s == -1:
                        if len(buf) > 1 << 20:
                            del buf[:-2]
                        break
                    e = buf.find(b"\xff\xd9", s + 2)
                    if e == -1:
                        if s > 0:
                            del buf[:s]
                        break
                    frame = bytes(buf[s:e + 2])
                    del buf[:e + 2]
                    try:
                        self._q.put_nowait(frame)
                    except queue.Full:
                        try:
                            self._q.get_nowait()
                        except queue.Empty:
                            pass
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            # 回收子进程，避免留下僵尸进程占着相机
            try:
                if self.proc:
                    self.proc.wait(timeout=3)
            except Exception:
                pass

    def read(self, timeout: float = 8.0) -> bytes | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            if self.error:
                raise RuntimeError(self.error)
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(
                    f"rpicam-vid 退出（code={self.proc.returncode}）{self._stderr_tail()[-300:]}")
            raise TimeoutError(f"rpicam-vid 取帧超时（{timeout}s）")

    def stop(self):
        self._stop.set()
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
                except Exception:
                    pass
            self.proc = None


# ----------------------------------------------------------------------
class FrameAdapter:
    """把不同像素格式的采集帧统一成 JPEG 字节 + 小灰度图。"""

    def __init__(self, fmt: str, width: int, height: int, quality: int = 72):
        self.fmt = (fmt or "RGB888").upper()
        self.width = int(width)
        self.height = int(height)
        self.quality = int(quality)

    @property
    def compressed(self) -> bool:
        return self.fmt in COMPRESSED

    # --------------------------------------------------------------
    def to_jpeg(self, frame) -> bytes:
        if self.compressed:
            return bytes(frame) if isinstance(frame, (bytes, bytearray)) else b""
        rgb = self._to_rgb(frame)
        if rgb is None:
            return b""
        # 原生内核：libjpeg-turbo 直接编码，省掉 Python 层的数组转换开销
        if native.available() and rgb.dtype == np.uint8:
            out = native.jpeg(rgb, rgb.shape[1], rgb.shape[0], self.quality)
            if out:
                return out
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=self.quality)
        return buf.getvalue()

    def to_gray(self, frame, tw: int, th: int) -> np.ndarray | None:
        """返回 th×tw 的 uint8 灰度图，用于帧差分。"""
        if self.compressed:
            try:
                im = Image.open(io.BytesIO(frame))
            except Exception:
                return None
            try:
                sw, sh = im.size
                for s in (8, 4, 2, 1):
                    if sw // s >= tw and sh // s >= th:
                        im.draft("L", (tw, th))
                        break
                im = im.convert("L")
                if im.size != (tw, th):
                    im = im.resize((tw, th), Image.BILINEAR)
                return np.asarray(im, dtype=np.uint8)
            except Exception:
                return None

        # 原生内核：只在降采样后的目标像素上算灰度，
        # 避免旧实现"先算全图 float32 灰度再降采样"的巨大浪费
        if native.available() and self.fmt in ("RGB888", "XBGR8888"):
            try:
                if frame.ndim == 3 and frame.shape[2] >= 3:
                    rgb = np.ascontiguousarray(frame[..., :3])
                    out = native.gray_ds(rgb, rgb.shape[1], rgb.shape[0], tw, th)
                    if out is not None:
                        return out
            except Exception:
                pass

        gray_full = self._to_gray_full(frame)
        if gray_full is None:
            return None
        h, w = gray_full.shape[:2]
        sh = max(1, h // th)
        sw = max(1, w // tw)
        small = gray_full[::sh, ::sw][:th, :tw]
        if small.shape != (th, tw):
            small = np.resize(small, (th, tw))
        return small.astype(np.uint8)

    # --------------------------------------------------------------
    def _to_gray_full(self, frame):
        try:
            if self.fmt in ("RGB888", "XBGR8888"):
                if frame.ndim != 3 or frame.shape[2] < 3:
                    return None
                rgb = frame[..., :3]
                return (rgb[..., 0].astype(np.float32) * 0.299
                        + rgb[..., 1].astype(np.float32) * 0.587
                        + rgb[..., 2].astype(np.float32) * 0.114)
            if self.fmt == "YUYV":
                return frame[:, 0::2].astype(np.float32)
            if self.fmt == "YUV420":
                return frame[:self.height].astype(np.float32)
        except Exception:
            return None
        return None

    def _to_rgb(self, frame):
        try:
            if self.fmt in ("RGB888", "XBGR8888"):
                return np.ascontiguousarray(frame[..., :3])
            if self.fmt == "YUYV":
                im = Image.frombuffer("YCbCr", (self.width, self.height),
                                      bytes(frame), "raw", "YUYV", 0, 1)
                return np.asarray(im.convert("RGB"))
            if self.fmt == "YUV420":
                return self._yuv420_to_rgb(frame)
        except Exception:
            return None
        return None

    @staticmethod
    def _yuv420_to_rgb(frame):
        """BT.601 全范围 YUV420 → RGB（numpy 实现）。"""
        try:
            h = int(frame.shape[0] * 2 / 3)
            w = int(frame.shape[1])
            y = frame[:h].astype(np.float32)
            u = frame[h::2, 0::2].astype(np.float32)
            v = frame[h::2, 1::2].astype(np.float32)
            u = np.repeat(np.repeat(u, 2, axis=0), 2, axis=1)[:h, :w]
            v = np.repeat(np.repeat(v, 2, axis=0), 2, axis=1)[:h, :w]
            c = y - 16.0
            d = u - 128.0
            e = v - 128.0
            r = (1.164 * c + 1.596 * e).clip(0, 255)
            g = (1.164 * c - 0.392 * d - 0.813 * e).clip(0, 255)
            b = (1.164 * c + 2.017 * d).clip(0, 255)
            return np.stack([r, g, b], axis=-1).astype(np.uint8)
        except Exception:
            return None


# ----------------------------------------------------------------------
class Camera:
    def __init__(self, config, state, detector, recorder, log=None):
        self.config = config
        self.state = state
        self.detector = detector
        self.recorder = recorder
        # 日志回调：降级/自愈路径要靠它把现场信息写进日志。
        # 没有它的话 self.log(...) 会抛 AttributeError，
        # 而这条路径恰恰只在相机出故障时才走 —— 等于自愈自己先崩。
        self.log = log or (lambda *_a, **_k: None)
        self.cam = None
        self.v4l2: V4L2Backend | None = None
        self.rpivid: RpiVidBackend | None = None
        self.thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._seq = 0
        self._frames = 0
        self._fps_mark = time.time()
        self._motion = False
        self._bbox = None
        self._algo = None
        self._region = None
        self._jpeg_ms = 0.0
        self._last_tick: float | None = None
        self.adapter: FrameAdapter | None = None
        self.camera_info: dict = {}
        self.backend = "libcamera"
        # 是否需要软件做旋转/镜像（ISP 能力不足时）
        self._software_transform = False
        self._rot = 0
        self._flip = "none"
        # 成像参数（亮度/对比度/白平衡/ISO…）：随配置走，三条通路的应用方式不同
        self._imaging: dict = imaging.defaults()
        self._imaging_unsupported: list[str] = []

    # ------------------------------------------------------------------
    @property
    def latest(self) -> bytes | None:
        with self._lock:
            return self._latest

    @property
    def seq(self) -> int:
        return self._seq

    def wait_for_frame(self, timeout: float = 10.0) -> bytes | None:
        start_seq = self._seq
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._seq != start_seq:
                data = self.latest
                if data:
                    return data
            time.sleep(0.01)
        return self.latest

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if Picamera2 is None and self.backend == "libcamera":
            self.state.set("error", "未安装 picamera2")
            return
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=8)
        self._release()

    def restart(self) -> None:
        self.stop()
        time.sleep(1.0)
        self.start()

    def _release_camera_handle(self) -> None:
        """彻底释放 Picamera2 句柄。

        只 close() 不够：libcamera 的 camera manager 会继续持有 /dev/media*，
        必须让 Picamera2 对象走完 stop()+close()，否则下一次打开相机会报
        "Pipeline handler in use by another process"。
        """
        cam = self.cam
        self.cam = None
        if cam is None:
            return
        try:
            cam.stop()
        except Exception:
            pass
        try:
            cam.close()
        except Exception:
            pass

    def _release(self) -> None:
        if self.v4l2:
            self.v4l2.stop()
            self.v4l2 = None
        if self.rpivid:
            self.rpivid.stop()
            self.rpivid = None
        self._release_camera_handle()
        self._last_tick = None
        self.state.update(camera_ready=False, running=False)

    # ------------------------------------------------------------------
    def _resolve_device(self) -> tuple[str, dict]:
        """决定用哪个后端与哪台设备。

        camera.device 支持：
          auto / <libcamera 索引> / <libcamera id> / /dev/videoN
        """
        dev = str(self.config.get("camera", "device", default="auto") or "auto").strip()
        cams = list_cameras()
        csi = [c for c in cams if c.get("type") == "csi"]
        usb = [c for c in cams if c.get("type") == "usb"]

        chosen = None
        if dev.startswith("/dev/video"):
            chosen = next((c for c in cams if c.get("id") == dev), None)
            if chosen is None:
                chosen = {"index": 0, "id": dev, "model": dev, "type": "usb",
                          "backend": "v4l2", "device": dev}
        elif dev.isdigit():
            idx = int(dev)
            chosen = next((c for c in cams if c.get("index") == idx), None)
        elif dev not in ("auto", ""):
            chosen = next((c for c in cams if dev in (c.get("id"), c.get("model"))), None)

        if chosen is None:
            chosen = (csi or usb or [None])[0]

        if chosen is None:
            return "libcamera", {"index": 0, "model": "未检测到摄像头", "type": "csi",
                                 "backend": "libcamera", "device": ""}
        self.camera_info = dict(chosen)
        backend = chosen.get("backend") or ("libcamera" if chosen.get("type") == "csi" else "v4l2")
        return backend, chosen

    # ------------------------------------------------------------------
    def _transform_params(self) -> tuple[int, str]:
        """读取配置里的旋转 / 镜像参数。"""
        try:
            rot = int(self.config.get("camera", "rotation", default=0) or 0) % 360
        except (TypeError, ValueError):
            rot = 0
        if rot not in (0, 90, 180, 270):
            rot = 0
        flip = str(self.config.get("camera", "flip", default="none") or "none").lower()
        if flip not in ("none", "horizontal", "vertical", "both"):
            flip = "none"
        return rot, flip

    # ------------------------------------------------------------------
    def _apply_transform(self, frame):
        """软件旋转 / 镜像（只在 ISP 做不了时用：90/270 旋转）。

        变换后必须保持 C 连续，否则原生 JPEG 内核会拒绝非连续内存。
        """
        rot, flip = self._rot, self._flip
        if rot == 0 and flip == "none":
            return frame
        try:
            if rot:
                frame = np.rot90(frame, {90: 1, 180: 2, 270: 3}[rot])
            if flip in ("horizontal", "both"):
                frame = frame[:, ::-1]
            if flip in ("vertical", "both"):
                frame = frame[::-1, :]
            return np.ascontiguousarray(frame)
        except Exception as exc:  # noqa: BLE001
            self.log(f"软件旋转/镜像失败: {exc}")
            return frame

    # ------------------------------------------------------------------
    # 成像参数
    #
    # 三条通路的落地方式完全不同：
    #   rpicam-vid  参数是**启动参数** → 改参数必须重建采集进程
    #   libcamera    走 set_controls()   → 多数能热更新
    #   v4l2-ctl     走 --set-ctrl       → 热更新，但控件得现查现用
    # ------------------------------------------------------------------
    def _load_imaging(self) -> dict:
        """从配置里读成像参数（顺带做范围钳制）。"""
        raw = self.config.get("camera", "imaging", default={}) or {}
        return imaging.normalize(raw)

    def imaging_backend(self) -> str:
        """当前采集通路对应的成像参数后端。"""
        b = (self.camera_info or {}).get("backend") or self.backend
        if b == "rpicam":
            return imaging.BACKEND_RPICAM
        if b == "v4l2":
            return imaging.BACKEND_V4L2
        return imaging.BACKEND_LIBCAMERA

    def imaging_status(self) -> dict:
        """成像参数的完整状态（给 /api/imaging 用）。"""
        backend = self.imaging_backend()
        names = None
        if backend == imaging.BACKEND_V4L2:
            dev = (self.camera_info or {}).get("device") or ""
            names = list(imaging.v4l2_controls(dev).keys())
        # rpicam-vid 启动失败时会退回"不带成像参数"，这时要如实告诉界面
        applied = True
        if backend == imaging.BACKEND_RPICAM and self.rpivid is not None:
            applied = bool(self.rpivid.imaging_applied)
        return {
            "values": dict(self._imaging),
            "backend": backend,
            "supported": imaging.supported_keys(backend, names),
            "requires_restart": imaging.requires_restart(backend),
            "unsupported": list(self._imaging_unsupported),
            "applied": applied,
        }

    @staticmethod
    def _filter_libcamera_controls(cam, controls: dict) -> dict:
        """只保留相机真正支持、且取值落在合法范围内的控制项。

        libcamera 对不支持的控制项会直接抛异常，对越界的值会打断言——
        这里先按 camera_controls 的 min/max 过滤一遍，避免整条管线崩掉。
        """
        try:
            avail = cam.camera_controls
        except Exception:
            return dict(controls or {})
        out: dict = {}
        for name, val in (controls or {}).items():
            ctrl = avail.get(name)
            if ctrl is None:
                continue
            if isinstance(val, (tuple, list)):
                # 数组型控制（ScalerCrop）：只做基本合法性检查
                if (len(val) == 4 and val[0] >= 0 and val[1] >= 0
                        and val[2] > 0 and val[3] > 0):
                    out[name] = tuple(val)
                continue
            try:
                lo, hi = ctrl.min, ctrl.max
            except Exception:
                out[name] = val
                continue
            if lo is not None and hi is not None:
                if not (float(lo) <= float(val) <= float(hi)):
                    continue
            out[name] = val
        return out

    def apply_imaging(self, values: dict) -> dict:
        """应用成像参数。

        返回 {ok, backend, applied, requires_restart, message, unsupported}。
        requires_restart=True 表示调用方要重启相机才能让参数生效。
        """
        backend = self.imaging_backend()
        norm = imaging.normalize(values)

        if backend == imaging.BACKEND_LIBCAMERA:
            if self.cam is None:
                self._imaging = norm
                return {"ok": True, "backend": backend, "applied": False,
                        "requires_restart": True,
                        "message": "相机尚未就绪，参数将在下次启动时生效"}
            w, h = self.config.get("camera", "resolution", default=[1280, 720])
            controls = self._filter_libcamera_controls(
                self.cam, imaging.libcamera_controls(norm, int(w), int(h)))
            try:
                self.cam.set_controls(controls)
            except Exception as exc:  # noqa: BLE001
                self.log(f"成像参数热更新失败: {exc}")
                return {"ok": False, "backend": backend, "applied": False,
                        "requires_restart": False,
                        "message": f"热更新失败：{exc}"}
            self._imaging = norm
            self._imaging_unsupported = []
            return {"ok": True, "backend": backend, "applied": True,
                    "requires_restart": False, "message": ""}

        if backend == imaging.BACKEND_V4L2:
            return self._apply_v4l2_imaging(norm)

        # rpicam-vid：成像参数只能带在启动命令行上
        self._imaging = norm
        return {"ok": True, "backend": backend, "applied": False,
                "requires_restart": True,
                "message": "该通路的成像参数在采集进程启动时生效，需要重启相机"}

    def _apply_v4l2_imaging(self, values: dict) -> dict:
        """把成像参数下发到 USB 摄像头。"""
        dev = (self.camera_info or {}).get("device") or ""
        result = {"ok": True, "backend": imaging.BACKEND_V4L2, "applied": True,
                  "requires_restart": False, "message": "",
                  "unsupported": []}
        if not dev:
            result.update(ok=False, applied=False,
                          message="未找到 USB 摄像头设备节点")
            return result
        controls = imaging.v4l2_controls(dev)
        args, unsupported = imaging.v4l2_set_args(values, controls)
        self._imaging = imaging.normalize(values)
        self._imaging_unsupported = unsupported
        result["unsupported"] = list(unsupported)
        if not args:
            result["message"] = "该摄像头没有可用的成像控件，参数未生效"
            return result
        cmd = ["v4l2-ctl", "-d", str(dev), "--set-ctrl"] + args
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=8)
        except Exception as exc:  # noqa: BLE001
            result.update(ok=False, applied=False,
                          message=f"下发失败：{exc}")
            return result
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip()[:200]
            result.update(ok=False, applied=False,
                          message=f"下发失败：{err or 'v4l2-ctl 返回码 %d' % proc.returncode}")
            return result
        return result

    def _build_config(self):
        backend, chosen = self._resolve_device()
        self.backend = backend
        w, h = self.config.get("camera", "resolution", default=[1280, 720])
        fps = max(1, int(self.config.get("camera", "fps", default=10)))
        self._imaging = self._load_imaging()

        # 切换采集模式前，先把上一轮的相机句柄彻底释放。
        # 否则 Picamera2 / rpicam-vid 的残留句柄会一直占着 /dev/media*，
        # 新后端启动时就会报 "Pipeline handler in use by another process"，
        # 表现为画面卡死或黑屏。
        self._release_camera_handle()

        if backend == "v4l2":
            device = chosen.get("device") or chosen.get("id") or ""
            self.v4l2 = V4L2Backend(device, int(w), int(h), fps)
            self.adapter = FrameAdapter("MJPEG", int(w), int(h),
                                        int(self.config.get("camera", "jpeg_quality", default=72)))
            rot0, flip0 = self._transform_params()
            self._rot, self._flip = rot0, flip0
            self._software_transform = False
            if rot0 or flip0 != "none":
                # USB 通路是 MJPEG 直通，旋转/镜像需要解码重编码，暂不支持
                self.log(f"USB 摄像头暂不支持旋转/镜像（当前 {rot0}° / {flip0}），已忽略")
            self.camera_info.update({"backend": "v4l2", "format": "MJPEG",
                                     "resolution": [int(w), int(h)],
                                     "rotation": rot0, "flip": flip0})
            return None

        is_rpi = chosen.get("type") == "csi"
        want = (self.config.get("camera", "format", default="auto") or "auto").upper()
        rot, flip = self._transform_params()
        # rpicam-vid 只能做 0/180 旋转；90/270 需要 transpose（ISP 不支持）
        rpicam_can_transform = rot in (0, 180)

        # ---- CSI 走 rpicam-vid 的 ISP 硬件 MJPEG 通路 ----
        # 由 ISP 硬件编码 JPEG，每帧编码零 CPU，且 JPEG 帧可直接透传给
        # 预览与录像。注意：这条分支不能创建 Picamera2，否则会占住相机。
        #
        # 实测（Pi 4 / ov5647 / 1280x720@10）：
        #   MJPEG  采集链路总 CPU ≈ 29.9%   jpeg_ms = 0.00
        #   RGB888 采集链路总 CPU ≈ 33.7%   jpeg_ms = 20.37
        # 所以 CSI 的 auto 优先选 MJPEG。
        use_rpicam = is_rpi and want in ("AUTO", "MJPEG") and rpicam_can_transform
        if is_rpi and want in ("AUTO", "MJPEG") and not rpicam_can_transform:
            # 90/270 旋转必须软件 transpose，改走 RGB888 通路
            self.log(f"旋转 {rot}° 需软件 transpose，CSI 采集通路改用 RGB888")
        if use_rpicam:
            if not RpiVidBackend.available():
                if want == "MJPEG":
                    raise RuntimeError("camera.format=MJPEG 需要 rpicam-vid，"
                                       "请安装 rpicam-apps 或改回 RGB888")
                # auto 且没装 rpicam-vid：继续往下走 libcamera 通路
            else:
                quality = int(self.config.get("camera", "jpeg_quality", default=72))
                # 成像参数是 rpicam-vid 的启动参数，只能带在命令行上。
                # 改参数 = 重建这个进程（调用方负责重启相机）。
                self.rpivid = RpiVidBackend(int(w), int(h), fps, quality, rot, flip,
                                           extra_args=imaging.rpicam_args(self._imaging))
                self.adapter = FrameAdapter("MJPEG", int(w), int(h), quality)
                self._software_transform = False
                self._imaging_unsupported = []
                self.camera_info.update({"backend": "rpicam", "format": "MJPEG",
                                         "resolution": [int(w), int(h)], "is_rpi": True,
                                         "rotation": rot, "flip": flip,
                                         "imaging": dict(self._imaging),
                                         "imaging_applied": bool(self.rpivid.imaging_applied)})
                return None

        # ---- libcamera 通路 ----
        idx = int(chosen.get("index", 0) or 0)
        cam = Picamera2(camera_num=idx)
        try:
            has_ctrl = "FrameDurationLimits" in cam.camera_controls
        except Exception:
            has_ctrl = False
        controls = {}
        if has_ctrl:
            controls["FrameDurationLimits"] = (int(1_000_000 / fps), int(1_000_000 / fps))

        # AE（自动曝光）设置。
        #
        # 这里踩过两个很深的坑，务必保留这段注释：
        #
        # 1) libcamera 的控制项分「标量」和「数组」两类，类型错了会直接
        #    触发 C++ 断言把整个进程打挂（signal=ABRT）：
        #       ExposureTime       标量 int    (1..66666 µs)
        #       AnalogueGain       标量 float  (1.0..16.0)
        #       AeConstraintMode   标量 int    (0..3)
        #       FrameDurationLimits 数组        ← 只有它是数组
        #    给标量控制项传元组，值会变成数组，libcamera 内部按 int 读取时
        #    命中 Assertion `!isArray_' failed，进程当场 abort。
        #
        # 2) libcamera **没有「给曝光/增益封顶」这种语义**：
        #       给 ExposureTime / AnalogueGain 赋一个标量 = 锁死成手动曝光，
        #       自动曝光从此失效，暗光下画面会明显变暗；
        #       给 ExposureTime 传区间元组 = 直接崩溃（见第 1 点）。
        #    所以真正的防护不是"限制 AE"，而是采集看门狗 + 自动降级：
        #    管线一僵死就重建（见 _capture_loop / _degrade）。
        #
        # 唯一安全的 AE 旋钮是 AeConstraintMode（测光模式）：
        #       0=Normal(整幅) 1=Highlight(高光) 2=Shadows(暗部) 3=Custom
        # 注意之前误设成 1(Highlight)，AE 改成按高光测光，画面会明显变暗。
        if is_rpi:
            try:
                cur = cam.camera_controls
                ae_mode = str(self.config.get("camera", "ae_constraint",
                                             default="normal")).strip().lower()
                ae_map = {"normal": 0, "highlight": 1, "shadows": 2, "custom": 3}
                if "AeConstraintMode" in cur and ae_mode in ae_map:
                    controls["AeConstraintMode"] = ae_map[ae_mode]
            except Exception:
                pass

        # 成像参数走 libcamera 控制项。测光模式由成像参数里的 metering 决定，
        # 会覆盖上面那个旧的 ae_constraint 旋钮。
        controls.update(self._filter_libcamera_controls(
            cam, imaging.libcamera_controls(self._imaging, int(w), int(h))))

        order = [want] if want != "AUTO" else list(CSI_FORMATS if is_rpi else USB_FORMATS)
        buffer_count = max(3, int(self.config.get("camera", "buffer_count", default=6)))
        last_err = None
        for fmt in order:
            try:
                cfg = cam.create_video_configuration(
                    main={"size": (int(w), int(h)), "format": fmt},
                    buffer_count=buffer_count,
                    controls=controls,
                )
                cam.configure(cfg)
                # 再下发一次 set_controls：让这些控制项变成可热更新的动态控制，
                # 之后改成像参数不必重建管线。
                try:
                    cam.set_controls({k: v for k, v in controls.items()
                                      if k != "FrameDurationLimits"})
                except Exception:
                    pass
                self.adapter = FrameAdapter(fmt, int(w), int(h),
                                            int(self.config.get("camera", "jpeg_quality", default=72)))
                self._rot, self._flip = rot, flip
                # libcamera 通路拿不到 Transform 控制项，旋转/镜像一律软件做
                self._software_transform = (rot != 0) or (flip != "none")
                self._imaging_unsupported = []
                self.camera_info.update({"backend": "libcamera", "format": fmt,
                                         "resolution": [int(w), int(h)], "is_rpi": is_rpi,
                                         "rotation": rot, "flip": flip,
                                         "imaging": dict(self._imaging)})
                return cam
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                try:
                    cam.close()
                except Exception:
                    pass
                cam = Picamera2(camera_num=idx)
        raise RuntimeError(f"没有可用的像素格式（尝试 {order}）：{last_err}")

    def _run(self) -> None:
        backoff = 2.0
        failures = 0
        while not self._stop.is_set():
            try:
                self.cam = self._build_config()
                if self.v4l2:
                    self.v4l2.start()
                    # USB 摄像头的成像控件要在流起来之后再下发：
                    # 设备被占用时 v4l2-ctl 改不了控制项。
                    self._apply_v4l2_imaging(self._imaging)
                elif self.rpivid:
                    self.rpivid.start()
                else:
                    self.cam.start()
                time.sleep(1.5)
                self.state.update(running=True, camera_ready=True, error=None,
                                  started_at=self.state.get("started_at") or time.time(),
                                  camera=self.camera_info)
                backoff = 2.0
                failures = 0
                self._capture_loop()
            except Exception as exc:  # noqa: BLE001
                msg = f"{type(exc).__name__}: {exc}"
                failures += 1
                self.state.update(error=msg, running=False, camera_ready=False)
                self._release()
                if self._stop.is_set():
                    break
                # 连续失败时逐级降级：先降分辨率（I2C/MIPI 带宽更小，
                # pipeline 更稳），再降帧率。极端亮度突变（例如手贴近镜头）
                # 会让 ov5647 的自动曝光/增益震荡，帧读出超过帧间隔，
                # libcamera pipeline 会僵死不再出帧；降档往往能救回来。
                self._degrade(failures)
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 15.0)

    # ------------------------------------------------------------------
    def _degrade(self, failures: int) -> None:
        """连续失败后的降级策略：分辨率 → 帧率。"""
        try:
            res = list(self.config.get("camera", "resolution", default=[1280, 720]))
            fps = int(self.config.get("camera", "fps", default=10))
            if failures >= 2 and res[0] > 640:
                new_res = [640, max(240, int(res[1] * 640 / res[0]))]
                self.config.set({"camera": {"resolution": new_res}})
                self.log(f"连续 {failures} 次取帧失败，降级分辨率至 {new_res[0]}x{new_res[1]}")
            elif failures >= 3 and fps > 5:
                new_fps = max(5, fps // 2)
                self.config.set({"camera": {"fps": new_fps}})
                self.log(f"连续 {failures} 次取帧失败，降级帧率至 {new_fps}")
            elif failures >= 5:
                # 兜底：彻底放弃当前后端，切回最保守的 RGB888 通路
                if self.config.get("camera", "format", default="auto") != "RGB888":
                    self.config.set({"camera": {"format": "RGB888"}})
                    self.log("连续取帧失败，回退到 RGB888 采集通路")
        except Exception as exc:  # noqa: BLE001
            self.log(f"降级处理失败: {exc}")

    # ------------------------------------------------------------------
    def _capture_loop(self) -> None:
        adapter = self.adapter
        detect_w, detect_h = self.config.get("camera", "detect_resolution", default=[320, 180])
        detect_w, detect_h = int(detect_w), int(detect_h)
        detect_fps = max(1, int(self.config.get("camera", "detect_fps", default=10)))
        detect_interval = 1.0 / detect_fps
        # 用"距上次检测的时间"而不是"下一个绝对时刻"来节流：
        # 后者会因为帧到达时刻的抖动而漂移，导致本该每帧检测的场合
        # 变成隔帧检测，侦测帧率凭空腰斩。
        last_detect = 0.0

        # 取帧看门狗：连续 stall_timeout 秒拿不到新帧就判定采集链路僵死，
        # 主动抛错让外层重建管线（而不是让画面一直黑着）。
        stall_timeout = float(self.config.get("camera", "stall_timeout",
                                              default=8.0))
        last_frame = time.time()
        slow_since = None

        while not self._stop.is_set():
            if self.v4l2 is not None:
                frame = self.v4l2.read(timeout=stall_timeout)
            elif self.rpivid is not None:
                frame = self.rpivid.read(timeout=stall_timeout)
            else:
                job = (self.cam.capture_buffer(wait=False) if adapter.compressed
                       else self.cam.capture_array(wait=False))
                try:
                    frame = job.get_result(timeout=stall_timeout)
                except Exception as exc:  # noqa: BLE001
                    raise TimeoutError(f"取帧超时（{stall_timeout:g}s）："
                                       f"{type(exc).__name__}") from exc
            if frame is None:
                continue
            # 旋转/镜像：MJPEG 通路由 ISP 直接做（零成本），
            # 原始 RGB 通路没有 Transform 控制项，只能在这里软件做。
            if (self._software_transform and self.adapter is not None
                    and not self.adapter.compressed):
                frame = self._apply_transform(frame)
            now = time.time()

            # 看门狗 1：整帧停更
            if now - last_frame > stall_timeout:
                raise TimeoutError(f"采集链路停滞（{stall_timeout:g}s 无新帧）")
            last_frame = now

            # 看门狗 2：帧还在来，但速率极低（例如只剩 1fps 以下）。
            # 这种情况画面看上去就是"卡住"，同样需要重建管线。
            min_fps = float(self.config.get("camera", "min_fps", default=0.5))
            if min_fps > 0:
                gap = now - (self._last_tick or now)
                if gap > 1.0 / min_fps:
                    if slow_since is None:
                        slow_since = now
                    elif now - slow_since > stall_timeout:
                        raise TimeoutError(
                            f"采集速率过低（<{min_fps:g} fps 持续 "
                            f"{now - slow_since:.1f}s）")
                else:
                    slow_since = None
            self._last_tick = now

            t0 = time.perf_counter()
            jpeg = adapter.to_jpeg(frame)
            self._jpeg_ms = (time.perf_counter() - t0) * 1000

            with self._lock:
                self._latest = jpeg
                self._seq += 1

            if now - last_detect >= detect_interval * 0.95:
                last_detect = now
                gray = adapter.to_gray(frame, detect_w, detect_h)
                if gray is not None:
                    det = self.detector.process(gray)
                    self._motion = det.motion
                    self._bbox = det.bbox
                    self._algo = det.algorithm
                    self._region = det.region
                    self.state.update(
                        motion=det.motion,
                        detection={
                            "motion": det.motion,
                            "algorithm": det.algorithm,
                            "region": det.region,
                            "ratio": det.ratio,
                            "ratios": det.ratios,
                            "bbox": list(det.bbox) if det.bbox else None,
                        },
                    )

            self.recorder.on_frame(jpeg, now, self._motion, self._bbox,
                                   self._algo, self._region)

            self._frames += 1
            if self._frames >= 10:
                el = time.time() - self._fps_mark
                self.state.update(
                    fps=round(self._frames / el, 1) if el > 0 else 0.0,
                    detect_fps=self.detector.detect_fps,
                    last_frame_at=now,
                    jpeg_ms=round(self._jpeg_ms, 1),
                )
                self._frames = 0
                self._fps_mark = time.time()
            else:
                self.state.update(last_frame_at=now)
