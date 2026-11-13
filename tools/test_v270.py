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


def build(root, values, space):
    cfg = FakeConfig(root, values)
    for sub in ("videos", "stills", "timelapse", "loop"):
        (cfg.configured / sub).mkdir(parents=True, exist_ok=True)
    cfg.internal.mkdir(parents=True, exist_ok=True)
    storage_mod.disk_usage = space.usage
    st = FakeState()
    rec = Recorder(cfg, st)
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


def main() -> int:
    print("pikrellcam-lite v2.7.0 离线单元测试")
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
