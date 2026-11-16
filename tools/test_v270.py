#!/usr/bin/env python3
"""v2.7.0 新功能的离线单元测试：成像参数矩阵 + 循环录像。

覆盖两大块：
  * core/imaging.py —— 参数钳制、三条采集通路的映射、能力报告
  * core/recorder.py 的循环录像 —— 分段轮换、与事件录像互斥让位、
    磁盘百分比护栏、全局配额护栏的回收顺序

用法：
    python3 tools/test_v270.py          # 在项目根目录跑
    python3 tools/test_v270.py --quiet  # 只看结果汇总

在 Mac 上没装 numpy / Pillow 时会自动打桩（这两个只用于图像处理，
本测试用不到）；在树莓派上跑的是真库。
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- Mac 上没有 numpy / Pillow，打桩让模块能导入 -------------------------
if "numpy" not in sys.modules:
    try:
        import numpy  # noqa: F401
    except Exception:  # noqa: BLE001
        sys.modules["numpy"] = types.ModuleType("numpy")
        sys.modules["numpy"].ndarray = object
        sys.modules["numpy"].uint8 = "uint8"
        sys.modules["numpy"].ascontiguousarray = lambda a: a
        sys.modules["numpy"].asarray = lambda a, dtype=None: a
        sys.modules["numpy"].empty = lambda *a, **k: None
        sys.modules["numpy"].resize = lambda a, s: a
for _name in ("PIL", "PIL.Image"):
    try:
        __import__(_name)
    except Exception:  # noqa: BLE001
        sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules["PIL"].Image = sys.modules["PIL.Image"]

from core import imaging, storage as storage_mod          # noqa: E402
from core.recorder import Recorder                        # noqa: E402
from core.util import dir_size                           # noqa: E402

GB = 1024 ** 3
MB = 1024 ** 2

PASS: list[str] = []
FAIL: list[str] = []
QUIET = "--quiet" in sys.argv


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    if not QUIET:
        print(("  ✅ " if cond else "  ❌ ") + name + (("  — " + detail) if detail else ""))


def section(title: str) -> None:
    if not QUIET:
        print("\n[%s]" % title)


# ======================================================================
# 成像参数矩阵
# ======================================================================
def test_normalize() -> None:
    section("成像参数：取值规范化")
    v = imaging.normalize({"brightness": 999, "contrast": -500, "awb": "不存在的模式"})
    check("越界数值被钳制到上限", v["brightness"] == 100, "brightness=%s" % v["brightness"])
    check("越界数值被钳制到下限", v["contrast"] == -100, "contrast=%s" % v["contrast"])
    check("非法枚举回落默认值", v["awb"] == "auto", "awb=%s" % v["awb"])

    v2 = imaging.normalize(None)
    check("缺省时补齐全部键", set(v2) == set(imaging.KEYS))
    check("默认值与规格一致",
          all(v2[s["key"]] == s["default"] for s in imaging.SPECS))

    v3 = imaging.normalize({"unknown_key": 1, "brightness": 60})
    check("未知键被丢弃", "unknown_key" not in v3)
    check("合法值原样保留", v3["brightness"] == 60)

    v4 = imaging.normalize({"iso": "abc"})
    check("非数值回落默认值", v4["iso"] == 0)


def test_rpicam() -> None:
    section("成像参数：rpicam-vid 通路")
    args = imaging.rpicam_args(imaging.defaults())
    joined = " ".join(args)
    check("默认亮度映射为 0", "--brightness 0.000" in joined, joined)
    check("默认对比度映射为 1.0", "--contrast 1.000" in joined, joined)
    check("默认饱和度映射为 1.0", "--saturation 1.000" in joined, joined)
    check("默认锐度映射为 1.0", "--sharpness 1.000" in joined, joined)
    check("默认不设 ISO", "--analoggain" not in joined, joined)
    check("默认不设快门", "--shutter" not in joined, joined)
    check("默认不裁剪", "--roi" not in joined, joined)

    v = imaging.normalize({"brightness": 75, "contrast": 50, "saturation": -100,
                           "sharpness": -50, "iso": 800, "shutter": 20000,
                           "zoom": 200, "ev": -3, "awb": "daylight",
                           "awb_r_gain": 1.5, "awb_b_gain": 2.0})
    joined = " ".join(imaging.rpicam_args(v))
    check("亮度 75 → 0.5", "--brightness 0.500" in joined, joined)
    check("对比度 50 → 1.5", "--contrast 1.500" in joined, joined)
    check("饱和度 -100 → 0（纯黑白）", "--saturation 0.000" in joined, joined)
    check("锐度 -50 → 0.5", "--sharpness 0.500" in joined, joined)
    check("ISO 800 → 增益 8.0", "--analoggain 8.000" in joined, joined)
    check("快门直接透传微秒", "--shutter 20000" in joined, joined)
    check("曝光补偿透传", "--ev -3" in joined, joined)
    check("白平衡模式透传", "--awb daylight" in joined, joined)
    check("显式白平衡增益", "--awbgains 1.500,2.000" in joined, joined)
    check("数字变焦转成中心裁剪 ROI",
          "--roi 0.2500,0.2500,0.5000,0.5000" in joined, joined)


def test_libcamera() -> None:
    section("成像参数：libcamera / picamera2 通路")
    c = imaging.libcamera_controls(imaging.defaults(), 1280, 720)
    check("默认亮度 0", c["Brightness"] == 0.0, str(c))
    check("默认对比度 1.0", c["Contrast"] == 1.0, str(c))
    check("默认饱和度 1.0", c["Saturation"] == 1.0, str(c))
    check("默认锐度 1.0", c["Sharpness"] == 1.0, str(c))
    check("默认自动白平衡", c.get("AwbEnable") is True, str(c))
    check("默认不锁快门", "ExposureTime" not in c, str(c))
    check("默认不裁剪", "ScalerCrop" not in c, str(c))

    v = imaging.normalize({"brightness": 100, "contrast": -50, "iso": 400,
                           "shutter": 5000, "zoom": 200, "awb": "daylight",
                           "metering": "spot", "denoise": "cdn_hq"})
    c = imaging.libcamera_controls(v, 1280, 720)
    check("亮度 100 → 1.0", c["Brightness"] == 1.0, str(c))
    check("对比度 -50 → 0.5", c["Contrast"] == 0.5, str(c))
    check("ISO 400 → 增益 4.0", c["AnalogueGain"] == 4.0, str(c))
    check("快门透传", c["ExposureTime"] == 5000, str(c))
    check("点测光 → 高光约束", c["AeConstraintMode"] == 1, str(c))
    check("降噪 cdn_hq → 模式 2", c["NoiseReductionMode"] == 2, str(c))
    check("固定白平衡 → 关闭 AWB", c["AwbEnable"] is False, str(c))
    check("固定白平衡 → 色温 5500", c["ColourTemperature"] == 5500, str(c))
    check("变焦 200% → 640x360 裁剪", c["ScalerCrop"] == (320, 180, 640, 360), str(c))

    # 裁剪变化需要重建管线，其它参数热更新即可
    check("裁剪变化需要重建管线",
          imaging.libcamera_needs_reconfigure(v, 1280, 720, imaging.defaults()))
    check("仅亮度变化不需重建",
          not imaging.libcamera_needs_reconfigure(
              imaging.normalize({"brightness": 80}), 1280, 720, imaging.defaults()))


def test_v4l2() -> None:
    section("成像参数：USB / v4l2-ctl 通路")
    fake = (
        "                     brightness 0x00980900 (int)    : "
        "min=0 max=255 step=1 default=128 value=128\n"
        "                       contrast 0x00980901 (int)    : "
        "min=0 max=255 step=1 default=128 value=128\n"
        "                     saturation 0x00980902 (int)    : "
        "min=0 max=255 step=1 default=128 value=128\n"
        "                      sharpness 0x00980903 (int)    : "
        "min=0 max=255 step=1 default=128 value=128\n"
        "                           gain 0x0098090c (int)    : "
        "min=0 max=255 step=1 default=0 value=0\n"
        "                exposure_absolute 0x009a0901 (int)    : "
        "min=1 max=10000 step=1 default=166 value=166\n"
        "         white_balance_temperature 0x009a090c (int) : "
        "min=2800 max=8000 step=10 default=4000 value=4000\n"
        "                           zoom_absolute 0x009a0910 (int) : "
        "min=100 max=400 step=1 default=100 value=100\n"
    )
    orig_run = subprocess.run
    orig_which = imaging.shutil.which

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "--list-ctrls" in cmd:
            return subprocess.CompletedProcess(cmd, 0, fake.encode(), b"")
        return orig_run(cmd, *a, **kw)

    imaging.subprocess.run = fake_run
    # Mac 上没有 v4l2-ctl，假装它装了
    imaging.shutil.which = lambda name: "/usr/bin/v4l2-ctl" if name == "v4l2-ctl" else orig_which(name)
    try:
        ctrls = imaging.v4l2_controls("/dev/video9")
        check("解析出控件数量", len(ctrls) == 8, str(sorted(ctrls)))
        check("解析控件量程", ctrls["brightness"]["max"] == 255, str(ctrls.get("brightness")))
        check("解析控件类型", ctrls["brightness"]["type"] == "int", str(ctrls.get("brightness")))

        v = imaging.normalize({"brightness": 50, "contrast": 0, "saturation": 0,
                               "sharpness": 0, "iso": 0, "shutter": 0})
        args, unsupported = imaging.v4l2_set_args(v, ctrls)
        check("亮度映射进控件量程", "brightness=128" in args, str(args))
        check("默认档位不报缺失", "sharpness" not in unsupported, str(unsupported))
        check("默认 AWB auto 不报缺失", "awb" not in unsupported, str(unsupported))

        # 非默认值才需要报"这个摄像头不支持"
        v_ev = imaging.normalize({"ev": 2, "denoise": "off"})
        _args2, unsupported_ev = imaging.v4l2_set_args(v_ev, ctrls)
        check("曝光补偿在 USB 上不支持", "ev" in unsupported_ev, str(unsupported_ev))
        check("降噪在 USB 上不支持", "denoise" in unsupported_ev, str(unsupported_ev))

        v2 = imaging.normalize({"awb": "daylight", "zoom": 200})
        args2, unsupported2 = imaging.v4l2_set_args(v2, ctrls)
        check("固定白平衡转色温", any(a.startswith("white_balance_temperature=")
                                      for a in args2), str(args2))
        check("变焦用 zoom_absolute", any(a.startswith("zoom_absolute=")
                                           for a in args2), str(args2))
    finally:
        imaging.subprocess.run = orig_run
        imaging.shutil.which = orig_which

    sup = imaging.supported_keys(imaging.BACKEND_V4L2,
                                  ["brightness", "contrast", "gain"])
    check("USB 只报告真实存在的控件",
          sup["brightness"] and sup["contrast"] and sup["iso"]
          and not sup["saturation"] and not sup["zoom"], str(sup))


def test_schema() -> None:
    section("成像参数：规格表自洽")
    schema = imaging.schema()
    check("规格表非空", len(schema) >= 14, "共 %d 项" % len(schema))
    check("每项都有 i18n key",
          all(s.get("label") for s in schema))
    check("每项都有分组", all(s.get("group") for s in schema))
    check("枚举项的选项合法",
          all(o.get("value") and o.get("label")
              for s in schema if s["type"] == "enum" for o in s["options"]))
    check("数值项范围合法",
          all(s["min"] <= s["max"] for s in schema if s["type"] == "number"))
    check("rpicam 通路支持全部参数",
          all(imaging.supported_keys(imaging.BACKEND_RPICAM).values()))
    check("rpicam 需要重启相机", imaging.requires_restart(imaging.BACKEND_RPICAM))
    check("libcamera 不需要重启", not imaging.requires_restart(imaging.BACKEND_LIBCAMERA))
    check("v4l2 不需要重启", not imaging.requires_restart(imaging.BACKEND_V4L2))


# ======================================================================
# 循环录像
# ======================================================================
class FakeConfig:
    """Recorder 需要的最小 Config 接口（含 loop 目录解析）。"""

    def __init__(self, root, values=None):
        self.root = Path(root)
        self.path = self.root / "config.json"
        self.internal = self.root / "internal"
        self.configured = self.root / "internal"
        self.values = values or {}
        self.runtime = {}

    def internal_media_dir(self):
        return self.internal

    def media_dir_configured(self):
        return self.configured

    def media_dir(self):
        return self.configured

    def media_sub(self, sub):
        return self.configured / sub

    def loop_dir(self):
        name = str(self.values.get("loop", {}).get("dir", "loop") or "loop")
        return self.configured / os.path.basename(name)

    def get(self, section, key, default=None):
        return self.values.get(section, {}).get(key, default)

    def set(self, patch, replace=False):
        for sec, vals in (patch or {}).items():
            self.values.setdefault(sec, {}).update(vals or {})
        return self.values

    def replace_value(self, section, key, value):
        self.values.setdefault(section, {})[key] = value
        return self.values

    def set_media_runtime(self, **kw):
        self.runtime.update(kw)

    def media_write_target(self):
        return (True, "", self.configured)


class FakeState:
    def __init__(self):
        self.data = {}

    def set(self, k, v):
        self.data[k] = v

    def update(self, **kw):
        self.data.update(kw)

    def get(self, k, default=None):
        return self.data.get(k, default)


class FakeProc:
    """ffmpeg 进程的替身：把"录出来的东西"写成一个带 moov atom 的最小 MP4。"""

    def __init__(self, cmd):
        self.cmd = cmd
        self.path = Path(cmd[-1])
        self.stdin = io.BytesIO()
        self.returncode = 0
        self._done = False

    def poll(self):
        return None

    def wait(self, timeout=None):
        self._flush()
        return 0

    def terminate(self):
        self._flush()

    def kill(self):
        self._flush()

    def _flush(self):
        if self._done:
            return
        self._done = True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "wb") as fh:
                fh.write(b"\x00\x00\x00\x08ftyp")
                fh.write(b"\x00\x00\x00\x10mdat")
                fh.write(b"\x00\x00\x00\x08moov")
        except OSError:
            pass


class Space:
    """可编程的 statvfs 替身。"""

    def __init__(self, total, free):
        self.total = total
        self.base_free = free
        self.media_dir = None
        self.base_used = 0

    def bind(self, media_dir):
        self.media_dir = media_dir
        self.base_used = dir_size(media_dir)

    def usage(self, path):
        if self.media_dir is None:
            return (self.total, self.base_free)
        now = dir_size(self.media_dir)
        freed = max(0, self.base_used - now)
        return (self.total, self.base_free + freed)


class FakeAudio:
    """录像器依赖的最小音频接口。"""

    def __init__(self, running=True):
        self.running = running
        self.windows = []      # 被请求切片的时间窗
        self.sliced = 0

    def slice_wav(self, t0, t1):
        self.windows.append((t0, t1))
        self.sliced += 1
        return b"RIFF" + b"\x00" * 40

    def status(self):
        return {"state": "running" if self.running else "idle"}


def build(root, values, space, audio=None):
    cfg = FakeConfig(root, values)
    for sub in ("videos", "stills", "timelapse", "loop"):
        (cfg.configured / sub).mkdir(parents=True, exist_ok=True)
    cfg.internal.mkdir(parents=True, exist_ok=True)
    storage_mod.disk_usage = space.usage
    st = FakeState()
    rec = Recorder(cfg, st, audio=audio)
    rec._spawn_encoder = lambda cmd: FakeProc(cmd)   # 替掉真的 ffmpeg
    return cfg, st, rec


def loop_files(cfg):
    d = cfg.loop_dir()
    return sorted(d.glob("*.mp4")) if d.exists() else []


def test_loop_basic() -> None:
    section("循环录像：开关与分段")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-loop-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "a", {"loop": {"enabled": False, "segment_seconds": 5}}, space)
    space.bind(cfg.media_dir())

    rec.on_frame(b"x" * 100, time.time())
    check("关闭时循环录像不产生文件", not loop_files(cfg), str(loop_files(cfg)))
    check("关闭时状态为未录制", not st.get("loop_recording"))

    cfg.set({"loop": {"enabled": True}})
    rec.on_frame(b"x" * 100, time.time())
    check("开启后开始写循环录像段", rec._loop_active is True)
    check("状态标记为正在录制", st.get("loop_recording") is True)

    # 段轮换：把时间往前推过一个段长
    now = time.time()
    rec.on_frame(b"x" * 100, now)
    rec.on_frame(b"x" * 100, now + 6)
    check("超过段长后轮换出第二段", rec.loop_stats()["segments"] == 2,
          str(rec.loop_stats()))
    check("轮换后前一段已落盘", len(loop_files(cfg)) == 1, str(loop_files(cfg)))

    rec.set_loop_enabled(False)
    check("关闭后当前段收尾", st.get("loop_recording") is False)
    check("关闭后不再有活动段", rec._loop_active is False)


def test_loop_yield() -> None:
    section("循环录像：与事件录像互斥让位")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-loop-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "b", {
        "loop": {"enabled": True, "segment_seconds": 60},
        "record": {"pre_seconds": 0, "post_seconds": 1, "event_gap_seconds": 0,
                   "max_event_seconds": 60},
    }, space)
    space.bind(cfg.media_dir())

    now = time.time()
    rec.on_frame(b"x" * 100, now)
    check("循环录像先跑起来", rec._loop_active is True)

    # 出现移动 → 事件录像接管，循环录像让位
    rec.on_frame(b"x" * 100, now + 1, motion=True)
    check("事件开始后循环录像让位", st.get("loop_recording") is False)
    check("让位状态被标记", st.get("loop_yielded") is True)
    check("事件录像正在录制", rec._in_event is True)

    # 事件结束（连续几帧没有移动）→ 循环录像恢复
    rec.on_frame(b"x" * 100, now + 2, motion=False)
    rec.on_frame(b"x" * 100, now + 4, motion=False)
    check("事件结束后循环录像恢复", rec._loop_active is True)
    check("让位状态已清除", st.get("loop_yielded") is False)
    check("事件录像文件已生成",
          len(list(cfg.media_sub("videos").glob("*.mp4"))) == 1,
          str(list(cfg.media_sub("videos").glob("*.mp4"))))


def test_loop_disk_guard() -> None:
    section("循环录像：磁盘百分比护栏")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-loop-"))
    space = Space(10 * GB, 8 * GB)
    cfg, st, rec = build(tmp / "c", {
        "loop": {"enabled": True, "segment_seconds": 5, "max_disk_percent": 1},
    }, space)
    space.bind(cfg.media_dir())

    # 造 3 个各 40MB 的旧段（10GB 的 1% = 100MB，超了就该删）
    d = cfg.loop_dir()
    for i in range(3):
        p = d / ("loop_old_%d.mp4" % i)
        with open(p, "wb") as fh:
            fh.truncate(40 * MB)
        t = time.time() - 300 + i
        os.utime(p, (t, t))

    removed = rec._loop_check_disk()
    check("超出百分比时删除最旧的段", removed >= 1, "removed=%d" % removed)
    check("删完之后占用回到限额内",
          dir_size(d) <= int(10 * GB * 0.01), "占用 %d MB" % (dir_size(d) // MB))


def test_global_guard_order() -> None:
    section("磁盘护栏：回收顺序（循环段 → 事件录像）")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-loop-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "d", {
        "record": {"max_disk_gb": 0.05, "min_free_gb": 0},
        "loop": {"enabled": False, "segment_seconds": 60},
    }, space)

    # 循环段 30MB + 事件录像 30MB，总量超过 50MB 配额
    lp = cfg.loop_dir() / "loop_a.mp4"
    with open(lp, "wb") as fh:
        fh.truncate(30 * MB)
    os.utime(lp, (time.time() - 500, time.time() - 500))
    vp = cfg.media_sub("videos") / "event_a.mp4"
    with open(vp, "wb") as fh:
        fh.truncate(30 * MB)
    os.utime(vp, (time.time() - 100, time.time() - 100))
    space.bind(cfg.media_dir())

    rec.check_disk()
    check("循环段先被回收", not lp.exists(), "loop 段仍在")
    check("事件录像被保留", vp.exists(), "事件录像被误删")


def test_loop_stats() -> None:
    section("循环录像：状态统计")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-loop-"))
    space = Space(20 * GB, 15 * GB)
    cfg, st, rec = build(tmp / "e", {
        "loop": {"enabled": True, "segment_seconds": 30, "max_disk_percent": 20},
    }, space)
    space.bind(cfg.media_dir())

    rec.on_frame(b"x" * 100, time.time())
    s = rec.loop_stats()
    check("统计包含 enabled", s["enabled"] is True)
    check("统计包含录制状态", s["recording"] is True)
    check("统计包含段数", s["segments"] >= 1, str(s))
    check("统计包含配额", s["limit_bytes"] > 0, str(s))
    check("统计包含磁盘总量", s["disk_total_bytes"] == 20 * GB, str(s))
    check("目录指向媒体目录下的 loop",
          s["dir"].endswith("loop"), s["dir"])


def test_video_fps() -> None:
    section("录像帧率：编码器按实测帧率打时间戳")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-fps-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "f", {
        "camera": {"fps": 10},
        "loop": {"enabled": False, "segment_seconds": 60},
    }, space)
    space.bind(cfg.media_dir())

    check("还没测量时退回配置帧率", rec._video_fps() == 10, str(rec._video_fps()))

    # 设备无视请求帧率：配置 10fps，设备实给 30fps。
    # 编码器若按 10fps 打时间戳，20 秒墙钟会录成 60 秒视频（3 倍慢放）。
    now = time.time()
    for i in range(75):                       # 2.5 秒 @30fps
        rec.on_frame(b"x" * 100, now + i / 30.0)
    check("实测帧率接近 30", abs(rec._rate_fps - 30) < 2, "measured=%s" % rec._rate_fps)
    check("录像帧率取实测值", 28 <= rec._video_fps() <= 31, str(rec._video_fps()))

    cmd, enc = rec._encoder_cmd(tmp / "x.mp4")
    joined = " ".join(cmd)
    check("ffmpeg 按实测帧率打时间戳",
          ("-framerate %d" % rec._video_fps()) in joined, joined)

    # 设备比要求的还慢时也要用实测值，否则视频会快放
    rec._rate_fps = 7.4
    check("设备更慢时用实测帧率", rec._video_fps() == 7, str(rec._video_fps()))
    rec._rate_fps = 999.0
    check("实测帧率被限制在合理上限", rec._video_fps() == 120, str(rec._video_fps()))


def test_loop_reports_paused() -> None:
    section("循环录像：如实上报暂停状态与实际帧率")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-looppause-"))
    space = Space(20 * GB, 15 * GB)
    cfg, st, rec = build(tmp / "g", {
        "loop": {"enabled": True, "segment_seconds": 30},
    }, space)
    space.bind(cfg.media_dir())

    rec.on_frame(b"x" * 100, time.time())
    s = rec.loop_stats()
    check("统计含 paused 字段", "paused" in s, str(s))
    check("未暂停时 paused 为 False", s["paused"] is False, str(s))
    check("统计含实际帧率", s["fps"] > 0, str(s))

    # 录像被暂停 → 循环录像不再开段（上游 pause 语义同样如此）
    cfg.set({"record": {"paused": True}})
    rec.on_frame(b"x" * 100, time.time() + 1)
    s = rec.loop_stats()
    check("暂停后 paused 为 True", s["paused"] is True, str(s))
    check("暂停后循环录像不再录制", s["recording"] is False, str(s))


def test_camera_record_throttle() -> None:
    section("采集：录像按配置帧率节流")
    from core.camera import Camera

    class FakeBackend:
        """假装是一个无视请求帧率的 USB 相机：一直给 30fps。"""

        def __init__(self, n, interval):
            self.n = n
            self.interval = interval

        def read(self, timeout=None):
            if self.n <= 0:
                raise RuntimeError("no more frames")
            self.n -= 1
            time.sleep(self.interval)
            return b"raw"

    class FakeAdapter:
        def to_jpeg(self, frame):
            return b"jpeg"

        def to_gray(self, frame, w, h):
            return None                 # 不做检测，省掉 numpy 依赖

    class FakeRecorder:
        def __init__(self):
            self.frames = 0

        def on_frame(self, jpeg, now, motion=False, bbox=None,
                     algorithm=None, region=None):
            self.frames += 1

    class FakeDetector:
        detect_fps = 10.0

        def process(self, gray):
            raise AssertionError("本测试不做检测")

    class FakeCamConfig:
        def get(self, section, key, default=None):
            table = {
                "camera": {"fps": 10, "detect_fps": 10,
                           "detect_resolution": [320, 180],
                           "stall_timeout": 8.0, "min_fps": 0.0},
            }
            return table.get(section, {}).get(key, default)

    cam = Camera.__new__(Camera)
    cam.config = FakeCamConfig()
    cam.state = FakeState()
    cam.recorder = FakeRecorder()
    cam.adapter = FakeAdapter()
    cam.detector = FakeDetector()
    cam.v4l2 = FakeBackend(60, 1 / 30.0)      # 设备给 30fps
    cam.rpivid = None
    cam.cam = None
    cam._software_transform = False
    cam._stop = threading.Event()
    cam._lock = threading.Lock()
    cam._latest = None
    cam._seq = 0
    cam._frames = 0
    cam._fps_mark = time.time()
    cam._motion = False
    cam._bbox = None
    cam._algo = None
    cam._region = None
    cam._last_tick = None
    cam._jpeg_ms = 0.0

    try:
        cam._capture_loop()
    except RuntimeError:
        pass
    delivered = cam.recorder.frames
    check("设备 30fps 时只按配置的 10fps 交付给录像器",
          12 <= delivered <= 26, "2 秒内交付了 %d 帧" % delivered)
    check("预览仍然是设备的原始帧率（不被节流影响）",
          cam._seq >= 50, "预览更新了 %d 次" % cam._seq)


def test_audio_windows() -> None:
    section("音频：音轨时间窗与事件/循环段的合流")
    import core.recorder as rec_mod

    tmp = Path(tempfile.mkdtemp(prefix="pkc-audio-rec-"))
    space = Space(30 * GB, 20 * GB)
    audio = FakeAudio()
    cfg, st, rec = build(tmp / "i", {
        "loop": {"enabled": False, "segment_seconds": 60},
        "record": {"pre_seconds": 5, "post_seconds": 1, "event_gap_seconds": 0,
                   "max_event_seconds": 60},
    }, space, audio=audio)
    space.bind(cfg.media_dir())

    # 没有音频对象时什么都不做
    rec.audio = None
    check("没有音频对象时不算开段", rec._audio_enabled() is False)
    rec.audio = audio
    rec.config.values.setdefault("record", {})["audio_enabled"] = True
    check("音频在跑且录像声音启用时算开段", rec._audio_enabled() is True)

    # 合流用替身：记录它被怎么调用
    calls = []
    orig = rec_mod.mux_audio

    def fake_mux(video, wav, bitrate, workdir, log=None):
        calls.append({"video": str(video), "wav": len(wav),
                      "bitrate": bitrate})
        return True

    rec_mod.mux_audio = fake_mux
    try:
        # 喂几帧形成预录缓冲，然后触发一个事件
        base = time.time()
        for i in range(12):
            rec.on_frame(b"x" * 100, base + i * 0.1)
        rec.on_frame(b"x" * 100, base + 1.3, motion=True)
        check("事件已开始", rec._in_event is True)
        check("音轨起点 = 预录缓冲里最早那一帧",
              abs(rec._event_audio_start - base) < 0.02,
              "start=%s base=%s" % (rec._event_audio_start, base))

        # 事件结束 → 自动排队并由后台 worker 合流
        rec.on_frame(b"x" * 100, base + 3.0, motion=False)
        check("事件结束", rec._in_event is False)
        for _ in range(60):
            if calls:
                break
            time.sleep(0.05)
        check("事件结束后自动合流了", bool(calls), str(calls))
        check("合流用的是事件录像文件",
              calls and calls[0]["video"].endswith(".mp4"), str(calls))
        check("合流拿到了音频数据", calls and calls[0]["wav"] > 0, str(calls))
        check("音轨切片起点 = 预录起点",
              audio.windows and abs(audio.windows[0][0] - base) < 0.02,
              str(audio.windows))
        # 音轨终点按**视频自己的时间轴**算（帧数 ÷ 编码帧率），不是收尾墙钟：
        # ffmpeg 收尾要花几百毫秒到一秒，按墙钟切会让音轨比视频长一截。
        want_end = base + rec._event_frames / max(1, rec._event_fps)
        check("音轨切片终点 = 视频时间轴终点",
              audio.windows and abs(audio.windows[0][1] - want_end) < 0.02,
              str(audio.windows))

        # 循环段也要能合流
        audio.windows.clear()
        calls.clear()
        cfg.set({"loop": {"enabled": True, "segment_seconds": 5}})
        rec.on_frame(b"x" * 100, base + 10.0)
        check("循环段已开", rec._loop_active is True)
        rec.on_frame(b"x" * 100, base + 16.0)      # 超过段长 → 轮换
        for _ in range(60):
            if calls:
                break
            time.sleep(0.05)
        check("循环段轮换后也合流了", bool(calls), str(calls))
        check("循环段合流用的是段文件",
              calls and calls[0]["video"].endswith(".mp4")
              and "loop_" in calls[0]["video"], str(calls))
        check("循环段音轨起点 = 段开始时刻",
              audio.windows and abs(audio.windows[0][0] - (base + 10.0)) < 0.02,
              str(audio.windows))
    finally:
        rec_mod.mux_audio = orig


def test_fps_sampling_robust() -> None:
    section("帧率采样抗噪：摄像头刚出流时不能把视频录成慢放")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-fps2-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "f", {
        "camera": {"fps": 10},
        "loop": {"enabled": False, "segment_seconds": 60},
    }, space)
    space.bind(cfg.media_dir())

    # 真机场景：服务启动后摄像头过了很久才出流，第一个 2 秒窗口里只有
    # 零星几帧。旧算法拿"服务启动到现在"的空窗算帧率 → 0.03fps →
    # 被 max(1) 钳成 1fps，整个事件视频慢放十几倍。
    t0 = time.time()
    rec.on_frame(b"x", t0 + 30.0)
    check("第一帧重置计时窗口",
          abs(rec._rate_mark - (t0 + 30.0)) < 0.01,
          str(rec._rate_mark - (t0 + 30.0)))

    # 接下来 2 秒只来 2 帧：样本太少，不该拿它当实测帧率
    rec.on_frame(b"x", t0 + 31.0)
    rec.on_frame(b"x", t0 + 32.1)
    check("样本太少时不更新实测帧率", rec._rate_fps == 0.0, str(rec._rate_fps))
    check("此时退回配置帧率而不是 1", rec._video_fps() == 10, str(rec._video_fps()))

    # 稳定跑起来后实测值照常采纳
    for i in range(40):
        rec.on_frame(b"x", t0 + 32.2 + i / 10.0)
    check("正常帧率被采纳", abs(rec._rate_fps - 10) < 2, str(rec._rate_fps))

    # 明显不合理的实测值一律不信，退回配置帧率
    rec._rate_fps = 0.05
    check("0.05fps 实测值被拒", rec._video_fps() == 10, str(rec._video_fps()))
    rec._rate_fps = 1.0
    check("1fps 实测值被拒", rec._video_fps() == 10, str(rec._video_fps()))
    rec._rate_fps = 1.9
    check("1.9fps 实测值被拒", rec._video_fps() == 10, str(rec._video_fps()))
    rec._rate_fps = 2.0
    check("2fps 以上才采信", rec._video_fps() == 2, str(rec._video_fps()))


def test_audio_end_aligns_with_video() -> None:
    section("音轨终点按视频时间轴算：音画严格对齐")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-align-"))
    space = Space(30 * GB, 20 * GB)
    audio = FakeAudio(running=True)
    cfg, st, rec = build(tmp / "a", {
        "camera": {"fps": 10},
        "record": {"pre_seconds": 0, "post_seconds": 0,
                   "max_event_seconds": 999, "event_gap_seconds": 0},
        "loop": {"enabled": False, "segment_seconds": 60},
    }, space, audio=audio)
    space.bind(cfg.media_dir())

    # 模拟一次事件：10fps 写 50 帧 = 5 秒视频
    rec._event_fps = 10
    rec._event_audio_start = 1000.0
    rec._event_frames = 50
    rec._in_event = False
    rec._event_id = "20260101_000000"
    out = cfg.media_sub("videos") / "20260101_000000.mp4"
    # 最小合法 MP4：ftyp + moov（_finish_event 会校验 moov 是否完整）
    ftyp = b"\x00\x00\x00\x18ftyp" + b"isom" + b"\x00" * 12
    moov = b"\x00\x00\x00\x10moov" + b"\x00" * 8
    out.write_bytes(ftyp + moov)
    rec._queue_mux = lambda path, t0, t1: audio.windows.append((t0, t1))
    rec._finish_event(1005.4)          # 收尾墙钟比视频晚 0.4 秒

    check("音轨窗口终点按帧数算而不是收尾墙钟",
          audio.windows and abs(audio.windows[-1][1] - 1005.0) < 0.01,
          str(audio.windows))
    check("音轨窗口起点不变",
          audio.windows and abs(audio.windows[-1][0] - 1000.0) < 0.01,
          str(audio.windows))


def test_record_countdown() -> None:
    section("录制倒计时：事件录像剩余时间与循环段剩余")
    tmp = Path(tempfile.mkdtemp(prefix="pkc-count-"))
    space = Space(30 * GB, 20 * GB)
    cfg, st, rec = build(tmp / "c", {
        "record": {"post_seconds": 20, "max_event_seconds": 120},
        "loop": {"enabled": False, "segment_seconds": 15},
    }, space)
    space.bind(cfg.media_dir())

    stt = rec.record_status()
    check("没在录像时不算录制中", stt["recording"] is False, str(stt))
    check("没在录像时没有剩余时间", stt["remaining"] is None, str(stt))
    check("没在录像时没有循环段剩余", stt["loop_remaining"] is None, str(stt))

    # 一个进行中的事件：最后一次移动在 5 秒前，补录 20 秒 → 还剩约 15 秒
    now = time.time()
    rec._in_event = True
    rec._event_start = now - 30
    rec._event_audio_start = now - 40        # 含 10 秒预录
    rec._last_motion_at = now - 5
    stt = rec.record_status()
    check("事件录像中标记为录制中", stt["recording"] is True, str(stt))
    check("剩余时间按补录时长算", abs(stt["remaining"] - 15.0) < 0.5, str(stt))
    check("已录时长含预录", abs(stt["elapsed"] - 40.0) < 0.5, str(stt))

    # 单事件时长上限先到时，剩余时间取上限那个（先到先算）
    rec._event_start = now - 118
    stt = rec.record_status()
    check("时长上限先到时取上限", abs(stt["remaining"] - 2.0) < 0.5, str(stt))

    # 循环段：15 秒一段，已经录了 6 秒 → 还剩约 9 秒
    rec._in_event = False
    rec._loop_active = True
    rec._loop_start = now - 6
    stt = rec.record_status()
    check("循环段在录", stt["loop_recording"] is True, str(stt))
    check("循环段剩余时间正确", abs(stt["loop_remaining"] - 9.0) < 0.5, str(stt))

    # 两者都不在录时，剩余时间必须为空（前端据此隐藏倒计时）
    rec._loop_active = False
    stt = rec.record_status()
    check("空闲时没有循环段剩余", stt["loop_remaining"] is None, str(stt))
    check("空闲时不算录制中", stt["recording"] is False, str(stt))


def main() -> int:
    print("PiMotionCam v2.7.0 离线单元测试")
    test_normalize()
    test_rpicam()
    test_libcamera()
    test_v4l2()
    test_schema()
    test_loop_basic()
    test_loop_yield()
    test_loop_disk_guard()
    test_global_guard_order()
    test_loop_stats()
    test_video_fps()
    test_fps_sampling_robust()
    test_loop_reports_paused()
    test_camera_record_throttle()
    test_audio_windows()
    test_audio_end_aligns_with_video()
    test_record_countdown()

    print("\n" + "=" * 52)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        for f in FAIL:
            print("  ❌ " + f)
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
