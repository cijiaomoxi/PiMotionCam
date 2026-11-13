"""成像参数矩阵：统一参数模型 + 各采集通路的落地。

为什么要单独一个模块
--------------------
「亮度/对比度/饱和/锐度/白平衡/ISO/快门/曝光补偿/变焦」这些参数，
在三条采集通路上的**名字、数值范围、单位、能不能热更新**全都不一样：

  * rpicam-vid（CSI 的 ISP 硬件 JPEG 通路）
    全部是**启动参数**，改一个值就得重建采集进程。
  * picamera2 / libcamera（CSI 的原始 RGB 通路）
    走 `set_controls()`，绝大多数能**热更新**，不用重启。
  * v4l2-ctl（USB 通路）
    走 `--set-ctrl`，热更新，但**摄像头不一定有那个控件**，
    还得先 `--list-ctrls` 探一遍才知道支持哪些、量程是多少。

所以这里做三件事：
  1. 定义一份**与通路无关**的统一参数表（SPECS），UI 直接照着它生成控件；
  2. 把统一参数**翻译**成各通路的原生形式；
  3. 报告当前通路**到底支持哪些**、改了要不要重启相机。

统一取值范围（刻意与上游 MMAL 版的语义对齐，方便迁移）：

    brightness    0..100     50 = 正常
    contrast    -100..100     0 = 正常
    saturation  -100..100     0 = 正常，-100 = 纯黑白
    sharpness   -100..100     0 = 正常
    ev           -10..10      0 = 不补偿（曝光档位）
    iso           0..3200     0 = 自动
    shutter       0..500000   微秒，0 = 自动
    zoom         100..300     百分数，100 = 不裁剪
"""
from __future__ import annotations

import re
import shutil
import subprocess

# ----------------------------------------------------------------------
# 参数表
#
# 前端照着这张表自动生成控件，所以字段含义要稳定：
#   key      配置键（camera.imaging.<key>）
#   type     number | enum
#   min/max/step/default   number 专用
#   options  [{value,label}]  enum 专用
#   unit     单位（纯展示）
#   label    i18n key
#   group    分组（前端分区显示）
#   auto     0 表示「自动」，UI 上要单独提示
# ----------------------------------------------------------------------

SPECS: list[dict] = [
    {
        "key": "brightness", "type": "number", "group": "tone",
        "min": 0, "max": 100, "step": 1, "default": 50, "unit": "",
        "label": "imaging.brightness",
        "help": "hint.imagingBrightness",
    },
    {
        "key": "contrast", "type": "number", "group": "tone",
        "min": -100, "max": 100, "step": 1, "default": 0, "unit": "",
        "label": "imaging.contrast",
        "help": "hint.imagingContrast",
    },
    {
        "key": "saturation", "type": "number", "group": "tone",
        "min": -100, "max": 100, "step": 1, "default": 0, "unit": "",
        "label": "imaging.saturation",
        "help": "hint.imagingSaturation",
    },
    {
        "key": "sharpness", "type": "number", "group": "tone",
        "min": -100, "max": 100, "step": 1, "default": 0, "unit": "",
        "label": "imaging.sharpness",
        "help": "hint.imagingSharpness",
    },
    {
        "key": "denoise", "type": "enum", "group": "tone",
        "default": "auto",
        "options": [
            {"value": "auto", "label": "imaging.denoiseAuto"},
            {"value": "off", "label": "imaging.denoiseOff"},
            {"value": "cdn_off", "label": "imaging.denoiseCdnOff"},
            {"value": "cdn_fast", "label": "imaging.denoiseCdnFast"},
            {"value": "cdn_hq", "label": "imaging.denoiseCdnHq"},
        ],
        "label": "imaging.denoise",
        "help": "hint.imagingDenoise",
    },
    {
        "key": "exposure", "type": "enum", "group": "exposure",
        "default": "normal",
        "options": [
            {"value": "normal", "label": "imaging.expNormal"},
            {"value": "sport", "label": "imaging.expSport"},
        ],
        "label": "imaging.exposure",
        "help": "hint.imagingExposure",
    },
    {
        "key": "metering", "type": "enum", "group": "exposure",
        "default": "centre",
        "options": [
            {"value": "centre", "label": "imaging.meterCentre"},
            {"value": "spot", "label": "imaging.meterSpot"},
            {"value": "average", "label": "imaging.meterAverage"},
            {"value": "custom", "label": "imaging.meterCustom"},
        ],
        "label": "imaging.metering",
        "help": "hint.imagingMetering",
    },
    {
        "key": "ev", "type": "number", "group": "exposure",
        "min": -10, "max": 10, "step": 1, "default": 0, "unit": "EV",
        "label": "imaging.ev",
        "help": "hint.imagingEv",
    },
    {
        "key": "iso", "type": "number", "group": "exposure",
        "min": 0, "max": 3200, "step": 10, "default": 0, "unit": "ISO",
        "auto": 0,
        "label": "imaging.iso",
        "help": "hint.imagingIso",
    },
    {
        "key": "shutter", "type": "number", "group": "exposure",
        "min": 0, "max": 500000, "step": 1000, "default": 0, "unit": "µs",
        "auto": 0,
        "label": "imaging.shutter",
        "help": "hint.imagingShutter",
    },
    {
        "key": "awb", "type": "enum", "group": "color",
        "default": "auto",
        "options": [
            {"value": "auto", "label": "imaging.awbAuto"},
            {"value": "incandescent", "label": "imaging.awbIncandescent"},
            {"value": "tungsten", "label": "imaging.awbTungsten"},
            {"value": "fluorescent", "label": "imaging.awbFluorescent"},
            {"value": "indoor", "label": "imaging.awbIndoor"},
            {"value": "daylight", "label": "imaging.awbDaylight"},
            {"value": "shade", "label": "imaging.awbShade"},
            {"value": "cloudy", "label": "imaging.awbCloudy"},
            {"value": "greysworld", "label": "imaging.awbGreysworld"},
        ],
        "label": "imaging.awb",
        "help": "hint.imagingAwb",
    },
    {
        "key": "awb_r_gain", "type": "number", "group": "color",
        "min": 0, "max": 3, "step": 0.1, "default": 0, "unit": "",
        "auto": 0,
        "label": "imaging.awbRGain",
        "help": "hint.imagingAwbGains",
    },
    {
        "key": "awb_b_gain", "type": "number", "group": "color",
        "min": 0, "max": 3, "step": 0.1, "default": 0, "unit": "",
        "auto": 0,
        "label": "imaging.awbBGain",
        "help": "hint.imagingAwbGains",
    },
    {
        "key": "zoom", "type": "number", "group": "color",
        "min": 100, "max": 300, "step": 10, "default": 100, "unit": "%",
        "label": "imaging.zoom",
        "help": "hint.imagingZoom",
    },
]

SPEC_BY_KEY = {s["key"]: s for s in SPECS}
KEYS = [s["key"] for s in SPECS]

# 采集通路标识
BACKEND_RPICAM = "rpicam"      # CSI + rpicam-vid（ISP 硬件 JPEG）
BACKEND_LIBCAMERA = "libcamera"  # CSI + picamera2（原始 RGB）
BACKEND_V4L2 = "v4l2"          # USB 摄像头

# 固定白平衡模式 → 色温（K）。rpicam 与 libcamera 用的名字不一样，
# 但语义可以靠色温对齐。
AWB_KELVIN = {
    "incandescent": 2800,
    "tungsten": 3200,
    "fluorescent": 4000,
    "indoor": 4500,
    "daylight": 5500,
    "shade": 7000,
    "cloudy": 6500,
    "greysworld": 5000,
}

# libcamera 的 AeConstraintMode
LIBCAMERA_AE_CONSTRAINT = {
    "centre": 0,    # Normal（整幅测光）
    "spot": 1,      # Highlight（高光优先，近似点测光）
    "average": 0,
    "custom": 3,    # Custom
}

# libcamera 的 NoiseReductionMode
LIBCAMERA_DENOISE = {
    "off": 0,
    "cdn_fast": 1,
    "cdn_hq": 2,
}

# ----------------------------------------------------------------------


def defaults() -> dict:
    """一份全新的默认成像参数。"""
    return {s["key"]: s["default"] for s in SPECS}


def normalize(values: dict | None) -> dict:
    """把外部传入的值钳制到合法范围，返回干净的参数字典。

    未知键一律丢弃；枚举值不合法时回落到默认值；
    数值越界时钳制（而不是报错）——网页滑块和手工改配置文件都走这里。
    """
    src = values or {}
    out: dict = {}
    for spec in SPECS:
        key = spec["key"]
        if key not in src:
            out[key] = spec["default"]
            continue
        val = src[key]
        if spec["type"] == "enum":
            allowed = [o["value"] for o in spec["options"]]
            out[key] = val if val in allowed else spec["default"]
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            out[key] = spec["default"]
            continue
        if spec.get("step"):
            # 对齐到步长，避免出现 0.30000000000000004 这种值
            num = round(round((num - spec["min"]) / spec["step"]) * spec["step"]
                        + spec["min"], 6)
        num = max(float(spec["min"]), min(float(spec["max"]), num))
        if float(num).is_integer():
            num = int(num)
        out[key] = num
    return out


def changed(a: dict, b: dict) -> list[str]:
    """两份参数里不同的键。"""
    keys = set(a or {}) | set(b or {})
    out = []
    for k in sorted(keys):
        if (a or {}).get(k) != (b or {}).get(k):
            out.append(k)
    return out


# ----------------------------------------------------------------------
# rpicam-vid（CSI 的 ISP 硬件 JPEG 通路）
#
# 这些全是**启动参数**：改完必须重建采集进程，
# 所以调用方要负责触发相机重启。
# ----------------------------------------------------------------------
def rpicam_args(values: dict) -> list[str]:
    """把统一参数翻译成 rpicam-vid 的命令行参数。"""
    v = normalize(values)
    args: list[str] = []

    # 亮度：0..100（50 正常）→ -1.0..1.0
    args += ["--brightness", "%.3f" % ((float(v["brightness"]) - 50.0) / 50.0)]
    # 对比度/饱和/锐度：-100..100（0 正常）→ 0.0..2.0（1.0 正常）
    for key, flag in (("contrast", "--contrast"),
                      ("saturation", "--saturation"),
                      ("sharpness", "--sharpness")):
        args += [flag, "%.3f" % (1.0 + float(v[key]) / 100.0)]
    # 降噪
    args += ["--denoise", str(v["denoise"])]
    # 曝光模式
    args += ["--exposure", str(v["exposure"])]
    # 测光
    args += ["--metering", str(v["metering"])]
    # 曝光补偿
    if int(v["ev"]) != 0:
        args += ["--ev", str(int(v["ev"]))]
    # 白平衡
    args += ["--awb", str(v["awb"])]
    r_gain, b_gain = float(v["awb_r_gain"]), float(v["awb_b_gain"])
    if r_gain > 0 or b_gain > 0:
        # 显式增益会关掉自动白平衡
        args += ["--awbgains", "%.3f,%.3f" % (r_gain or 1.0, b_gain or 1.0)]
    # ISO（模拟增益，ISO 100 ≡ gain 1.0）
    if int(v["iso"]) > 0:
        gain = max(1.0, min(16.0, float(v["iso"]) / 100.0))
        args += ["--analoggain", "%.3f" % gain]
    # 快门
    if int(v["shutter"]) > 0:
        args += ["--shutter", str(int(v["shutter"]))]
    # 数字变焦：中心裁剪
    zoom = max(1.0, float(v["zoom"]) / 100.0)
    if zoom > 1.001:
        w = 1.0 / zoom
        args += ["--roi", "%.4f,%.4f,%.4f,%.4f" % ((1.0 - w) / 2.0, (1.0 - w) / 2.0, w, w)]
    return args


# ----------------------------------------------------------------------
# picamera2 / libcamera（CSI 的原始 RGB 通路）
#
# set_controls() 是**运行时**调用：绝大多数参数热更新即可，
# 不用重启相机。只有裁剪（ScalerCrop）偶尔需要重新配置管线。
# ----------------------------------------------------------------------
def libcamera_controls(values: dict, width: int = 1280, height: int = 720) -> dict:
    """把统一参数翻译成 libcamera 控制项字典。"""
    v = normalize(values)
    c: dict = {}

    c["Brightness"] = round((float(v["brightness"]) - 50.0) / 50.0, 3)
    for key, name in (("contrast", "Contrast"),
                      ("saturation", "Saturation"),
                      ("sharpness", "Sharpness")):
        c[name] = round(1.0 + float(v[key]) / 100.0, 3)

    mode = LIBCAMERA_DENOISE.get(str(v["denoise"]))
    if mode is not None:
        c["NoiseReductionMode"] = mode

    c["AeConstraintMode"] = LIBCAMERA_AE_CONSTRAINT.get(str(v["metering"]), 0)

    # 快门 / ISO：非自动时才显式下发
    shutter = int(v["shutter"])
    if shutter > 0:
        c["ExposureTime"] = shutter
    iso = int(v["iso"])
    if iso > 0:
        c["AnalogueGain"] = round(max(1.0, min(16.0, iso / 100.0)), 3)

    # 曝光补偿：libcamera 用绝对 EV 值
    ev = int(v["ev"])
    if ev != 0:
        c["ExposureValue"] = float(ev)

    # 白平衡
    awb = str(v["awb"])
    r_gain, b_gain = float(v["awb_r_gain"]), float(v["awb_b_gain"])
    if r_gain > 0 or b_gain > 0:
        c["AwbEnable"] = False
        c["ColourTemperature"] = AWB_KELVIN.get(awb, 5000)
    elif awb == "auto":
        c["AwbEnable"] = True
    else:
        c["AwbEnable"] = False
        c["ColourTemperature"] = AWB_KELVIN.get(awb, 5000)

    # 数字变焦：中心裁剪
    zoom = max(1.0, float(v["zoom"]) / 100.0)
    if zoom > 1.001:
        cw = max(16, int(width / zoom))
        ch = max(16, int(height / zoom))
        c["ScalerCrop"] = ((width - cw) // 2, (height - ch) // 2, cw, ch)

    return c


def libcamera_needs_reconfigure(values: dict, width: int, height: int,
                                old_values: dict | None) -> bool:
    """判断是否必须重建管线（而不是 set_controls 热更新）。

    只有**裁剪区域**的变化需要重新配置视频管线；
    其余控制项都可以热更新。
    """
    if old_values is None:
        return False
    try:
        new_crop = libcamera_controls(values, width, height).get("ScalerCrop")
        old_crop = libcamera_controls(old_values, width, height).get("ScalerCrop")
    except Exception:
        return False
    return new_crop != old_crop


# ----------------------------------------------------------------------
# v4l2-ctl（USB 摄像头）
#
# USB 摄像头到底有哪些控件、量程多大，必须现查：
# `v4l2-ctl -d /dev/videoN --list-ctrls`
# ----------------------------------------------------------------------
_CTRL_RE = re.compile(
    r"^\s*(?P<name>[\w-]+)\s+0x[0-9a-fA-F]+\s+\((?P<type>[^)]+)\)\s*:\s*(?P<rest>.*)$")


def v4l2_controls(device: str) -> dict:
    """列出设备支持的控制项。返回 {name: {type,min,max,step,default,value}}。"""
    out: dict = {}
    if not device or not shutil.which("v4l2-ctl"):
        return out
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", str(device), "--list-ctrls"],
            capture_output=True, timeout=8)
    except Exception:
        return out
    text = proc.stdout.decode("utf-8", "replace")
    for line in text.splitlines():
        m = _CTRL_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        info: dict = {"type": m.group("type").strip()}
        for k, v in re.findall(r"(\w+)=(-?[\d.]+)", m.group("rest")):
            try:
                info[k] = float(v) if "." in v else int(v)
            except ValueError:
                continue
        out[name] = info
    return out


def _scale_to_range(value: float, src_min: float, src_max: float,
                    dst: dict) -> float:
    """把统一参数的值线性映射到某个 V4L2 控件的量程。"""
    lo = dst.get("min")
    hi = dst.get("max")
    if lo is None or hi is None or hi == lo:
        return value
    if src_max == src_min:
        return float(lo)
    ratio = (value - src_min) / (src_max - src_min)
    return float(lo) + ratio * (float(hi) - float(lo))


def v4l2_set_args(values: dict, controls: dict) -> tuple[list[str], list[str]]:
    """生成 `v4l2-ctl --set-ctrl` 参数。

    返回 (参数列表, 不支持的参数键列表)。
    控件缺失的项会被跳过——USB 摄像头的控件集差别很大，
    缺哪个就当哪个没开，而不是让整条命令失败。
    """
    v = normalize(values)
    args: list[str] = []
    unsupported: list[str] = []

    def put(key: str, ctrl: str, raw, src_min: float, src_max: float):
        if ctrl not in controls:
            unsupported.append(key)
            return
        val = _scale_to_range(float(raw), src_min, src_max, controls[ctrl])
        step = controls[ctrl].get("step") or 1
        if isinstance(step, int):
            val = int(round(val / step) * step)
        args.append("%s=%d" % (ctrl, int(val)))

    put("brightness", "brightness", v["brightness"], 0, 100)
    put("contrast", "contrast", v["contrast"], -100, 100)
    put("saturation", "saturation", v["saturation"], -100, 100)
    put("sharpness", "sharpness", v["sharpness"], -100, 100)
    put("iso", "gain", v["iso"], 0, 3200)
    put("shutter", "exposure_absolute", v["shutter"], 0, 500000)

    # 曝光补偿：USB 摄像头一般没有独立的 EV 控件，
    # 只能靠 exposure_absolute 平移，这里明确标为不支持。
    if int(v["ev"]) != 0:
        unsupported.append("ev")

    # 白平衡：色温控件存在时用色温，否则不支持
    if str(v["awb"]) != "auto":
        kelvin = AWB_KELVIN.get(str(v["awb"]))
        if "white_balance_temperature" in controls and kelvin:
            args.append("white_balance_temperature=%d" % kelvin)
        else:
            unsupported.append("awb")
    if float(v["awb_r_gain"]) > 0 or float(v["awb_b_gain"]) > 0:
        unsupported.append("awb_r_gain")
        unsupported.append("awb_b_gain")

    # 变焦：USB 摄像头常见 zoom / zoom_absolute
    if float(v["zoom"]) != 100:
        zoom = float(v["zoom"]) / 100.0
        if "zoom_absolute" in controls:
            z = controls["zoom_absolute"]
            val = _scale_to_range(zoom, 1.0, 3.0, z)
            args.append("zoom_absolute=%d" % int(val))
        elif "zoom" in controls:
            args.append("zoom=%d" % int(round(zoom * 100)))
        else:
            unsupported.append("zoom")

    # 降噪 / 曝光模式 / 测光：USB 摄像头基本没有对应控件
    if str(v["denoise"]) != "auto":
        unsupported.append("denoise")
    if str(v["exposure"]) != "normal":
        unsupported.append("exposure")
    if str(v["metering"]) != "centre":
        unsupported.append("metering")

    return args, unsupported


# ----------------------------------------------------------------------
# 能力报告
# ----------------------------------------------------------------------
def supported_keys(backend: str, v4l2_control_names: list[str] | None = None) -> dict:
    """当前通路下每个参数是否可用。"""
    if backend == BACKEND_RPICAM:
        keys = set(KEYS)
    elif backend == BACKEND_LIBCAMERA:
        keys = set(KEYS)
    elif backend == BACKEND_V4L2:
        names = set(v4l2_control_names or [])
        keys = set()
        for key, ctrl in (("brightness", "brightness"), ("contrast", "contrast"),
                          ("saturation", "saturation"), ("sharpness", "sharpness"),
                          ("iso", "gain"), ("shutter", "exposure_absolute")):
            if ctrl in names:
                keys.add(key)
        if "white_balance_temperature" in names:
            keys.add("awb")
        if "zoom_absolute" in names or "zoom" in names:
            keys.add("zoom")
    else:
        keys = set()
    return {k: (k in keys) for k in KEYS}


def requires_restart(backend: str) -> bool:
    """改参数是否必须重启采集进程。

    rpicam-vid 的成像参数全是启动参数 → 必须重启；
    libcamera / v4l2 都是运行时控制 → 不用重启。
    """
    return backend == BACKEND_RPICAM


def schema() -> list[dict]:
    """给前端的参数表（去掉内部字段）。"""
    out = []
    for spec in SPECS:
        item = {k: v for k, v in spec.items() if k != "default"}
        item["default"] = spec["default"]
        out.append(item)
    return out
