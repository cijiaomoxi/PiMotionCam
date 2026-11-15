"""pikrellcam-lite v2.8.0 音频子系统离线单元测试。

覆盖：ALSA 设备解析、USB 口匹配（优先用摄像头自带的麦）、WAV 打包、
环形缓冲按时间窗切片、电平换算、合流命令构造。

Mac 上没有 arecord / ffmpeg 也能跑：设备探测用假文本喂给解析函数，
合流用替身进程验证命令形状。
"""
from __future__ import annotations

import struct
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS: list = []
FAIL: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print("  ✅ %s" % name)
    else:
        FAIL.append(name)
        print("  ❌ %s   %s" % (name, detail))


def section(title: str) -> None:
    print("\n[%s]" % title)


from core import audio                       # noqa: E402

ARECORD_L = """
**** List of CAPTURE Hardware Devices ****
card 3: CAM [WEB CAM], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0

card 1: Headphones [ bcm2835 Headphones ], device 0: bcm2835 Headphones [bcm2835 Headphones]
  Subdevices: 1/1
"""

PROC_CARDS = """ 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0
                      vc4-hdmi-0
 1 [vc4hdmi1       ]: vc4-hdmi - vc4-hdmi-1
                      vc4-hdmi-1
 2 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones
                      bcm2835 Headphones
 3 [CAM            ]: USB-Audio - WEB CAM
                      WCM_USB WEB CAM at usb-0000:01:00.0-1.3, high speed
"""


# ----------------------------------------------------------------------
def test_parse_cards() -> None:
    section("ALSA 设备解析")
    cards = audio.parse_proc_cards(PROC_CARDS)
    check("只挑出带 USB 路径的声卡", len(cards) == 1, str(cards))
    check("USB 声卡的 USB 路径被提取",
          cards.get(3) == "usb-0000:01:00.0-1.3", str(cards))
    check("非 USB 声卡没有 USB 路径", cards.get(0, "") == "", str(cards))

    devs = audio.parse_arecord_list(ARECORD_L, cards)
    check("解析出 2 个采集设备", len(devs) == 2, str(devs))
    cam = devs[0]
    check("采集设备卡号正确", cam.card == 3 and cam.device == 0, str(cam))
    check("采集设备名称正确", cam.card_name == "CAM [WEB CAM]", cam.card_name)
    check("采集设备带 USB 路径", cam.usb == "usb-0000:01:00.0-1.3", cam.usb)
    check("hw 设备名正确", cam.id == "hw:3,0", cam.id)
    check("plug 设备名正确", cam.plug_id == "plughw:3,0", cam.plug_id)
    check("USB 设备被标记", cam.is_usb is True, str(cam))


def test_usb_port_match() -> None:
    section("USB 口匹配：优先用摄像头自带的麦克风")
    check("ALSA 路径归一成端口号",
          audio.usb_port("usb-0000:01:00.0-1.3") == "1.3",
          audio.usb_port("usb-0000:01:00.0-1.3"))
    check("sysfs 路径归一成端口号",
          audio.usb_port("1-1.3") == "1.3", audio.usb_port("1-1.3"))
    check("空路径返回空", audio.usb_port("") == "")

    devs = audio.parse_arecord_list(ARECORD_L, audio.parse_proc_cards(PROC_CARDS))
    # 摄像头在 1.3 口 → 应该选那颗 USB 麦
    picked = audio.pick_device(devs, "1.3")
    check("优先选中摄像头同口的麦克风",
          picked is not None and picked.id == "hw:3,0", str(picked))
    # 没有同口的 → 退到任意 USB 设备
    picked2 = audio.pick_device(devs, "2.7")
    check("没有同口设备时退到任意 USB 设备",
          picked2 is not None and picked2.is_usb, str(picked2))
    check("没有设备时返回空", audio.pick_device([], "1.3") is None)


def test_wav() -> None:
    section("WAV 打包")
    pcm = b"\x01\x02" * 16000          # 1 秒 16kHz 单声道
    data = audio.wav_bytes(pcm, 16000, 1)
    check("WAV 头是 44 字节", len(data) == 44 + len(pcm), str(len(data)))
    check("RIFF 标识正确", data[:4] == b"RIFF", repr(data[:4]))
    check("WAVE 标识正确", data[8:12] == b"WAVE", repr(data[8:12]))
    check("PCM 格式标记为 1",
          struct.unpack_from("<H", data, 20)[0] == 1, "")
    check("声道数正确", struct.unpack_from("<H", data, 22)[0] == 1, "")
    check("采样率正确", struct.unpack_from("<I", data, 24)[0] == 16000, "")
    check("字节率正确",
          struct.unpack_from("<I", data, 28)[0] == 16000 * 2, "")
    check("data 块长度正确",
          struct.unpack_from("<I", data, 40)[0] == len(pcm), "")


def test_slice_alignment() -> None:
    section("环形缓冲：按时间窗切片")
    cap = audio.AudioCapture(state=None, log=None)
    cap._rate = 16000
    cap._channels = 1
    base = 1000.0
    # 每块 8000 字节 = 4000 采样 = 0.25 秒，时间戳就按 0.25 秒排
    for i in range(4):
        cap._push(bytes([i]) * 8000, base + i * 0.25)

    # 窗口 [1000.1, 1000.6] → 整整 0.5 秒 = 8000 采样 = 16000 字节
    wav = cap.slice_wav(base + 0.1, base + 0.6)
    check("切出指定时间窗", wav is not None, "None")
    if wav:
        body = wav[44:]
        check("切片长度与时间窗一致", len(body) == 16000,
              "%d 字节" % len(body))
        # 第 0 块贡献 0.1~0.25 秒（值 0），第 1 块整块（值 1），
        # 第 2 块贡献 0.5~0.6 秒（值 2）
        check("切片起点落在正确的块里", body[:2] == b"\x00\x00", repr(body[:2]))
        check("切片中段落在正确的块里", body[4800:4802] == b"\x01\x01",
              repr(body[4800:4802]))
        check("切片终点落在正确的块里", body[-2:] == b"\x02\x02", repr(body[-2:]))

    # 窗口起点早于缓冲 → 前面补静音（音轨仍然和视频对齐）
    wav = cap.slice_wav(base - 0.5, base + 0.25)
    check("早于缓冲的窗口也能切", wav is not None, "None")
    if wav:
        body = wav[44:]
        check("补静音后长度 = 整个时间窗",
              len(body) == int(0.75 * 16000) * 2, "%d 字节" % len(body))
        check("补的部分是静音", body[:2] == b"\x00\x00", repr(body[:2]))
        check("有数据的位置仍在原来的时间点上",
              body[int(0.5 * 16000) * 2:int(0.5 * 16000) * 2 + 2] == b"\x00\x00",
              repr(body[int(0.5 * 16000) * 2:int(0.5 * 16000) * 2 + 2]))

    check("窗口完全在缓冲之外时返回空",
          cap.slice_wav(base - 100, base - 90) is None)
    check("窗口倒挂时返回空", cap.slice_wav(base + 2, base + 1) is None)
    check("零长度窗口返回空", cap.slice_wav(base, base) is None)


def test_level() -> None:
    section("电平换算")
    cap = audio.AudioCapture(state=None, log=None)
    check("静音电平为 0", cap._rms_level(b"\x00\x00" * 1000) == 0.0)
    full = struct.pack("<h", 32767) * 1000
    check("满刻度电平为 1", abs(cap._rms_level(full) - 1.0) < 0.01,
          str(cap._rms_level(full)))
    half = struct.pack("<h", 3277) * 1000       # 约 -20 dB
    lvl = cap._rms_level(half)
    check("中等音量落在合理区间", 0.5 < lvl < 0.9, str(lvl))
    check("空数据电平为 0", cap._rms_level(b"") == 0.0)


def test_mux_command() -> None:
    section("合流：视频零重编码")
    calls = {}

    class FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        # 假装 ffmpeg 产出了输出文件
        Path(cmd[-1]).write_bytes(b"\x00" * 128)
        return FakeProc()

    orig = audio.subprocess.run
    audio.subprocess.run = fake_run
    try:
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="pkc-audio-"))
        video = tmp / "seg.mp4"
        video.write_bytes(b"\x00" * 64)
        wav = audio.wav_bytes(b"\x01\x02" * 100, 16000, 1)
        ok = audio.mux_audio(video, wav, 64, tmp)
        check("合流返回成功", ok is True)
        cmd = calls.get("cmd") or []
        joined = " ".join(cmd)
        check("调用的是 ffmpeg", cmd and cmd[0] == "ffmpeg", joined)
        check("视频零重编码（-c:v copy）", "-c:v" in cmd and "copy" in cmd, joined)
        check("音频转 AAC", "-c:a" in cmd and "aac" in cmd, joined)
        check("码率按配置下发", "64k" in cmd, joined)
        check("输出是新的 mp4", cmd and cmd[-1].endswith(".mp4"), joined)
        check("临时文件已清理",
              not list(tmp.glob("*.wav")) and not list(tmp.glob("*.audio.mp4")),
              str(list(tmp.iterdir())))
    finally:
        audio.subprocess.run = orig


def test_mux_failure_keeps_video() -> None:
    section("合流失败时不动原文件")
    import tempfile

    class FakeProc:
        returncode = 1
        stdout = b""
        stderr = b"boom"

    orig = audio.subprocess.run
    audio.subprocess.run = lambda cmd, **kw: FakeProc()
    try:
        tmp = Path(tempfile.mkdtemp(prefix="pkc-audio-fail-"))
        video = tmp / "seg.mp4"
        video.write_bytes(b"\x00" * 64)
        ok = audio.mux_audio(video, audio.wav_bytes(b"\x00" * 100, 16000, 1), 64, tmp)
        check("合流失败返回 False", ok is False)
        check("原文件仍在", video.exists() and video.stat().st_size == 64, "")
    finally:
        audio.subprocess.run = orig


def test_status_shape() -> None:
    section("状态字典")
    cap = audio.AudioCapture(state=None, log=None)
    st = cap.status()
    for key in ("state", "device", "rate", "channels", "level", "error",
                "running"):
        check("状态含 " + key, key in st, str(st))
    check("初始不是运行状态", st["running"] is False, str(st))


def main() -> int:
    print("pikrellcam-lite v2.8.0 音频子系统离线单元测试")
    test_parse_cards()
    test_usb_port_match()
    test_wav()
    test_slice_alignment()
    test_level()
    test_mux_command()
    test_mux_failure_keeps_video()
    test_status_shape()
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
