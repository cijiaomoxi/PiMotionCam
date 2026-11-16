"""ALSA 音频采集与录像合流。

上游 PiKrellCam 用 ALSA 采集 + lame 编 MP3 来做"带声音的录像"，并专门算了
"音频与视频同步偏移"。本模块沿用同样的思路，但有三处调整：

1. **编码用 AAC 而不是 MP3**：MP4 容器原生支持 AAC，不必先出 MP3 再二次
   封装；浏览器与手机播放器也都能直接播。
2. **视频流零重编码**：合流时 ``-c:v copy``，只重编音频。
3. **采集与录像解耦**：麦克风常驻采集到内存环形缓冲，录像收尾时按**墙钟
   时间窗**切片对齐——这样事件录像的"预录"段也能配上正确的声音，而不只是
   从事件开始才有声。

没有麦克风的环境（CSI 树莓派、没插麦）时整个子系统自动关闭，录像主流程
完全不受影响。

上游对应的配置键是 ``audio_enable`` / ``audio_device`` / ``audio_rate`` /
``audio_channels`` / ``audio_gain_dB``，本模块沿用同样的命名思路。
"""
from __future__ import annotations

import math
import os
import re
import struct
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

try:
    import numpy as np
except ImportError:  # Keep the standalone audio tools usable without numpy.
    np = None

# ---- 默认值 -------------------------------------------------------------
# 这颗 USB 摄像头自带的麦克风原生就是 16 kHz 单声道（48 kHz 与立体声会被
# ALSA 拒绝），所以默认就用原生参数：既省 CPU，音质也不吃亏。
DEFAULT_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_BITRATE = 64          # kbps，AAC
DEFAULT_BUFFER_SECONDS = 180  # 环形缓冲保留时长（秒）
# 事件录像最长可以到 record.max_event_seconds（默认 120 秒）再加上预录段，
# 缓冲比它短就会出现音轨比视频短的情况（后面用补静音兜住，但真实声音
# 还是得够长才谈得上完整）。16 kHz 单声道 180 秒只占 5.8 MB。

SAMPLE_WIDTH = 2              # S16_LE
_READ_CHUNK = 4096            # 每次从 arecord 读的字节数（16k 单声道 ≈ 128ms）
_RETRY_DELAY = 3.0            # 麦克风掉线后的重试间隔


def apply_gain(data: bytes, gain_db: float = 0.0) -> bytes:
    """S16_LE gain with saturation; preserve channel ordering and frame size."""
    count = len(data) // 2
    if not count or not gain_db:
        return data
    factor = 10.0 ** (max(-30.0, min(30.0, float(gain_db))) / 20.0)
    if np is not None:
        samples = np.frombuffer(data, dtype="<i2", count=count).astype(np.float64)
        return np.clip(np.rint(samples * factor), -32768, 32767).astype("<i2").tobytes() + data[count*2:]
    values = [max(-32768, min(32767, round(value * factor)))
              for (value,) in struct.iter_unpack("<h", data[:count * 2])]
    return struct.pack('<%dh' % count, *values) + data[count*2:]


# ----------------------------------------------------------------------
# 设备探测
# ----------------------------------------------------------------------
@dataclass
class AudioDevice:
    """一个 ALSA 采集设备。"""

    card: int
    device: int
    name: str = ""          # "USB Audio [USB Audio]"
    card_name: str = ""     # "CAM [WEB CAM]"
    usb: str = ""           # "usb-0000:01:00.0-1.3"

    @property
    def id(self) -> str:
        """硬件设备名（hw:N,M）。"""
        return "hw:%d,%d" % (self.card, self.device)

    @property
    def plug_id(self) -> str:
        """插件设备名（plughw:N,M）：允许任意采样率，由插件负责转换。"""
        return "plughw:%d,%d" % (self.card, self.device)

    @property
    def is_usb(self) -> bool:
        return bool(self.usb)

    @property
    def port(self) -> str:
        return usb_port(self.usb)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plug_id": self.plug_id,
            "card": self.card,
            "device": self.device,
            "name": self.name,
            "card_name": self.card_name,
            "usb": self.usb,
            "is_usb": self.is_usb,
            "port": self.port,
        }


def usb_port(path: str) -> str:
    """从 USB 路径里取出端口号。

    ``1-1.3``（sysfs 形式）与 ``usb-0000:01:00.0-1.3``（ALSA 形式）
    都能归一成 ``1.3``，用来判断"这颗麦克风和那颗摄像头是不是同一个设备"。
    """
    if not path:
        return ""
    tail = path.rsplit("-", 1)[-1]
    return tail.split(",")[0].strip()


def video_usb_port(device: str) -> str:
    """``/dev/videoN`` → 它所在的 USB 端口号（"1.3"）；不是 USB 设备返回空。"""
    name = os.path.basename(device or "")
    if not name.startswith("video"):
        return ""
    try:
        real = os.path.realpath("/sys/class/video4linux/%s/device" % name)
    except OSError:
        return ""
    for part in reversed(real.split("/")):
        m = re.match(r"^\d+-([\d.]+)$", part)
        if m:
            return m.group(1)
    return ""


_CARD_RE = re.compile(r"^\s*(\d+)\s+\[([^\]]+)\]:\s*(.*)$")
_CARD_USB_RE = re.compile(r"at\s+(usb-[^\s,]+)")


def parse_proc_cards(text: str) -> dict:
    """解析 ``/proc/asound/cards`` → {card 序号: USB 路径}。

    ALSA 的卡片信息分两行：

        3 [CAM            ]: USB-Audio - WEB CAM
                          WCM_USB WEB CAM at usb-0000:01:00.0-1.3, high speed
    """
    out: dict[int, str] = {}
    card = None
    for line in (text or "").splitlines():
        m = _CARD_RE.match(line)
        if m:
            card = int(m.group(1))
            continue
        if card is not None:
            m2 = _CARD_USB_RE.search(line)
            if m2:
                out[card] = m2.group(1)
                card = None
    return out


def parse_arecord_list(text: str, usb_by_card: dict | None = None) -> list:
    """解析 ``arecord -l`` 的输出。

        card 3: CAM [WEB CAM], device 0: USB Audio [USB Audio]
    """
    usb_by_card = usb_by_card or {}
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^card\s+(\d+):\s*(.*?),\s*device\s+(\d+):\s*(.*)$", line.strip())
        if not m:
            continue
        card = int(m.group(1))
        card_name = m.group(2).strip()
        dev = int(m.group(3))
        name = m.group(4).strip()
        out.append(AudioDevice(card=card, device=dev, name=name,
                               card_name=card_name,
                               usb=usb_by_card.get(card, "")))
    return out


_DEV_CACHE = {"at": 0.0, "list": []}


def probe_devices(max_age: float = 10.0) -> list:
    """列出本机所有 ALSA 采集设备。

    设备列表缓存 10 秒：``arecord -l`` 是要起子进程的，界面每秒轮询一次
    状态接口，不能每次都跑一遍。
    """
    now = time.time()
    if now - _DEV_CACHE["at"] < max_age:
        return _DEV_CACHE["list"]
    usb_by_card: dict = {}
    try:
        usb_by_card = parse_proc_cards(
            Path("/proc/asound/cards").read_text())
    except Exception:
        pass
    try:
        r = subprocess.run(["arecord", "-l"], capture_output=True, timeout=8)
        text = r.stdout.decode("utf-8", "replace")
    except Exception:
        text = ""
    devs = parse_arecord_list(text, usb_by_card)
    _DEV_CACHE["at"] = now
    _DEV_CACHE["list"] = devs
    return devs


def pick_device(devices: list, prefer_port: str = "") -> object | None:
    """挑一个采集设备。

    优先选**和摄像头同一个 USB 口**的那颗麦克风（USB 摄像头自带的麦就在
    同一个口上），其次选任意 USB 设备，最后才退到别的声卡。
    """
    if not devices:
        return None
    if prefer_port:
        for dev in devices:
            if dev.port and dev.port == prefer_port:
                return dev
    for dev in devices:
        if dev.is_usb:
            return dev
    return devices[0]


# ----------------------------------------------------------------------
# WAV
# ----------------------------------------------------------------------
def wav_bytes(pcm: bytes, rate: int, channels: int) -> bytes:
    """把裸 PCM 打包成 WAV（内存里直接生成，不落盘）。"""
    byte_rate = rate * channels * SAMPLE_WIDTH
    block_align = channels * SAMPLE_WIDTH
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels,
                                    rate, byte_rate, block_align,
                                    SAMPLE_WIDTH * 8)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


# ----------------------------------------------------------------------
# 采集
# ----------------------------------------------------------------------
@dataclass
class AudioCapture:
    """常驻的 ALSA 采集：arecord → PCM → 内存环形缓冲。

    环形缓冲按"块"存放，每块带一个墙钟时间戳。录像收尾时按时间窗切片，
    得到与视频严格对齐的一段 WAV。
    """

    state: object = None
    log: object = None
    _chunks: deque = field(default_factory=deque, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _proc: object = field(default=None, init=False)
    _thread: object = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _level: float = field(default=0.0, init=False)
    _status: str = field(default="idle", init=False)
    _error: str = field(default="", init=False)
    _device: str = field(default="", init=False)
    _rate: int = field(default=DEFAULT_RATE, init=False)
    _channels: int = field(default=DEFAULT_CHANNELS, init=False)
    _buffer_seconds: int = field(default=DEFAULT_BUFFER_SECONDS, init=False)
    _gain_db: float = field(default=0.0, init=False)
    _live: deque = field(default_factory=lambda: deque(maxlen=8), init=False)
    _live_sequence: int = field(default=0, init=False)
    _live_epoch: int = field(default=0, init=False)

    def __post_init__(self):
        self._live_condition = threading.Condition(self._lock)

    # ------------------------------------------------------------------
    def start(self, device: str = "auto", rate: int = DEFAULT_RATE,
              channels: int = DEFAULT_CHANNELS,
              buffer_seconds: int = DEFAULT_BUFFER_SECONDS,
              prefer_port: str = "", gain_db: float = 0.0) -> dict:
        """开始采集。返回状态字典。"""
        self.stop()
        self._rate = max(4000, min(48000, int(rate or DEFAULT_RATE)))
        self._channels = 1 if int(channels or 1) <= 1 else 2
        self._gain_db = max(-30.0, min(30.0, float(gain_db or 0.0)))
        self._buffer_seconds = max(10, min(600, int(buffer_seconds or
                                                     DEFAULT_BUFFER_SECONDS)))

        devs = probe_devices()
        chosen = None
        if device and device != "auto":
            for dev in devs:
                if device in (dev.id, dev.plug_id):
                    chosen = dev
                    break
            if chosen is None:
                self._status = "error"
                self._error = "找不到音频设备 %s" % device
                self._publish()
                return self.status()
        else:
            chosen = pick_device(devs, prefer_port)
        if chosen is None:
            self._status = "error"
            self._error = "没有找到 ALSA 采集设备"
            self._publish()
            return self.status()

        # 用 plughw：硬件只支持原生采样率，插件负责转换，
        # 这样即使用户把采样率调成 48k 也能录（上游也是这么做的）。
        self._device = chosen.plug_id
        self._status = "starting"
        self._error = ""
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pkc-audio",
                                        args=(chosen,), daemon=True)
        self._thread.start()
        self._publish()
        return self.status()

    def stop(self) -> dict:
        """停止采集。"""
        self._stop.set()
        proc = self._proc
        self._proc = None
        if proc is not None:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        th = self._thread
        self._thread = None
        if th is not None and th.is_alive():
            th.join(timeout=3)
        self._status = "idle"
        self._error = ""
        self._level = 0.0
        with self._lock:
            self._chunks.clear()
            self._live.clear()
            self._live_epoch += 1
            self._live_condition.notify_all()
        self._publish()
        return self.status()

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._status == "running"

    def level(self) -> float:
        """当前电平（0..1）。"""
        return self._level

    def status(self) -> dict:
        return {
            "state": self._status,
            "device": self._device,
            "rate": self._rate,
            "channels": self._channels,
            "buffer_seconds": self._buffer_seconds,
            "level": round(self._level, 3),
            "error": self._error,
            "running": self.running,
            "gain_db": self._gain_db,
        }

    def _publish(self) -> None:
        if self.state is None:
            return
        try:
            self.state.update(audio_state=self._status,
                              audio_level=round(self._level, 3),
                              audio_device=self._device,
                              audio_error=self._error)
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        if callable(self.log):
            try:
                self.log(msg)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _run(self, dev) -> None:
        """采集线程：起 arecord，读 PCM，丢进环形缓冲。"""
        cmd = ["arecord", "-q", "-D", dev.plug_id, "-f", "S16_LE",
               "-r", str(self._rate), "-c", str(self._channels),
               "-t", "raw"]
        while not self._stop.is_set():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0)
            except Exception as exc:  # noqa: BLE001
                self._status = "error"
                self._error = "无法启动麦克风采集：%s" % exc
                self._publish()
                self._stop.wait(_RETRY_DELAY)
                continue
            self._proc = proc
            self._status = "running"
            self._error = ""
            self._publish()
            self._log("麦克风已开始采集：%s（%d Hz / %d 声道）"
                      % (dev.plug_id, self._rate, self._channels))
            try:
                pending = b""
                while not self._stop.is_set():
                    chunk = proc.stdout.read(_READ_CHUNK)
                    t1 = time.time()
                    if not chunk:
                        break
                    pending += chunk
                    frame_bytes = self._channels*SAMPLE_WIDTH
                    count = len(pending)-len(pending)%frame_bytes
                    data, pending = pending[:count], pending[count:]
                    if not data:
                        continue
                    # 这一块样本覆盖的是"读到它之前的那段时间"：
                    # arecord 按采样率匀速出样本，所以块起点 = 读完时刻 - 块时长。
                    dur = len(data) / float(self._rate * self._channels * SAMPLE_WIDTH)
                    self._push(data, t1 - dur)
            except Exception:
                pass
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=3)
                except Exception:
                    pass
                self._proc = None
            if not self._stop.is_set():
                self._status = "error"
                self._error = "麦克风采集中断，正在重试"
                self._publish()
                self._log("麦克风采集中断，%g 秒后重试" % _RETRY_DELAY)
                self._stop.wait(_RETRY_DELAY)

    def _push(self, data: bytes, ts: float) -> None:
        """把一块 PCM 存进环形缓冲，并更新电平。"""
        data = apply_gain(data, self._gain_db)
        with self._lock:
            self._chunks.append((ts, data))
            cutoff = ts - self._buffer_seconds
            while self._chunks and self._chunks[0][0] < cutoff:
                self._chunks.popleft()
            self._live_sequence += 1
            self._live.append((self._live_sequence, data))
            self._live_condition.notify_all()
        self._level = self._rms_level(data)
        callback = getattr(self, "on_level", None)
        if callback:
            try:
                callback(self._level)
            except Exception:
                pass
        self._publish()

    def live_pcm(self, idle_timeout=10.0):
        """Fan out current PCM without reopening ALSA or replaying old audio.

        At most eight recent chunks are retained. A slow browser skips old
        chunks instead of applying backpressure to recording or capture.
        """
        with self._lock:
            cursor, epoch = self._live_sequence, self._live_epoch
        received_at = time.monotonic()
        while True:
            with self._live_condition:
                self._live_condition.wait_for(
                    lambda: self._live_sequence > cursor or self._stop.is_set()
                    or self._live_epoch != epoch, timeout=2.0)
                if self._stop.is_set() or self._live_epoch != epoch:
                    return
                pending = [(seq, pcm) for seq, pcm in self._live if seq > cursor]
                if not pending and time.monotonic() - received_at >= idle_timeout:
                    return
            for cursor, pcm in pending:
                received_at = time.monotonic()
                yield pcm

    def _rms_level(self, data: bytes) -> float:
        """RMS 电平映射到 0..1（-60 dB ~ 0 dB）。"""
        n = len(data) // 2
        if n <= 0:
            return 0.0
        if np is not None:
            samples = np.frombuffer(data, dtype="<i2", count=n)
            # Widen before squaring: int16 multiplication overflows even at
            # ordinary microphone levels. int64 preserves the scalar result.
            total = int(np.square(samples, dtype=np.int64).sum(dtype=np.int64))
        else:
            total = sum(v * v for (v,) in struct.iter_unpack("<h", data[:n * 2]))
        rms = (total / n) ** 0.5
        if rms <= 0:
            return 0.0
        db = 20.0 * math.log10(rms / 32768.0)
        db = max(-60.0, min(0.0, db))
        return round((db + 60.0) / 60.0, 3)

    # ------------------------------------------------------------------
    def slice_wav(self, t0: float, t1: float) -> bytes | None:
        """按墙钟时间窗切出一段 WAV（与视频时间轴对齐用）。

        返回的音频**长度恰好等于这个时间窗**：缓冲里没覆盖到的部分
        （事件录像比环形缓冲还长、或者中途麦克风重启过）补静音。这样音轨
        的起点永远和视频第一帧对齐，不会出现"声音晚了半分钟"。整段都没
        有数据时返回 None（不给视频加空音轨）。
        """
        if not t1 or t1 <= t0:
            return None
        with self._lock:
            chunks = list(self._chunks)
        bpf = SAMPLE_WIDTH * self._channels
        rate = self._rate
        total = int(round((t1 - t0) * rate))
        if total <= 0:
            return None
        buf = bytearray(total * bpf)        # 缺的部分保持静音
        copied = 0
        for ts, data in chunks:
            dur = len(data) / float(rate * self._channels * SAMPLE_WIDTH)
            if ts + dur <= t0 or ts >= t1:
                continue
            start = max(0, int(round((t0 - ts) * rate)))
            end = min(len(data) // bpf, int(round((t1 - ts) * rate)))
            if end <= start:
                continue
            src = data[start * bpf:end * bpf]
            off = max(0, int(round((ts - t0) * rate))) * bpf
            if off + len(src) > len(buf):
                src = src[:max(0, len(buf) - off)]
            if not src:
                continue
            buf[off:off + len(src)] = src
            copied += len(src)
        if copied == 0:
            return None
        return wav_bytes(bytes(buf), rate, self._channels)


# ----------------------------------------------------------------------
# 合流
# ----------------------------------------------------------------------
def _log(log, msg: str) -> None:
    if callable(log):
        try:
            log(msg)
        except Exception:
            pass



def mux_audio(video: Path, wav: bytes, bitrate: int = DEFAULT_BITRATE,
              workdir: Path | None = None, log=None) -> bool:
    """把 WAV 音轨合进已有的 MP4（视频零重编码）。

    成功时**原地替换** video 文件；失败时原文件保持不变，
    并把 ffmpeg 的报错写进日志（否则只能看到"合流失败"四个字）。
    """
    work = Path(workdir or "/tmp/pikrellcam-lite")
    try:
        work.mkdir(parents=True, exist_ok=True)
    except OSError:
        work = Path("/tmp")
    stem = "%s_%d" % (video.stem, os.getpid())
    wav_path = work / (stem + ".wav")
    # 输出文件必须和视频**在同一个文件系统里**：树莓派的 /tmp 是 tmpfs，
    # 而视频在 SD 卡上，跨文件系统的 rename 会直接报 EXDEV（Invalid
    # cross-device link），合流就会莫名其妙地失败。
    out_path = video.with_name(video.stem + ".audio.mp4")
    try:
        wav_path.write_bytes(wav)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", str(video), "-i", str(wav_path),
               "-c:v", "copy", "-c:a", "aac", "-b:a", "%dk" % int(bitrate),
               "-movflags", "+faststart", str(out_path)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180)
        except Exception as exc:  # noqa: BLE001
            _log(log, "ffmpeg 调用失败：%s" % exc)
            return False
        if r.returncode != 0 or not out_path.exists():
            err = (r.stderr or b"").decode("utf-8", "replace").strip()
            _log(log, "ffmpeg 合流失败（rc=%s）：%s" % (r.returncode, err[-400:]))
            return False
        if out_path.stat().st_size == 0:
            _log(log, "ffmpeg 合流产出了空文件")
            return False
        os.replace(out_path, video)
        return True
    except Exception as exc:  # noqa: BLE001
        _log(log, "音轨合流出错：%s" % exc)
        return False
    finally:
        for p in (wav_path, out_path):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
