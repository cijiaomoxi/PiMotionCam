# PiMotionCam

**树莓派摄像头监测与自动录像工具。** 基于 libcamera / picamera2，支持 CSI / USB 摄像头、运动侦测、循环录像和音频录制。

**Camera monitoring and automatic recording for Raspberry Pi.** Built on libcamera / picamera2, with CSI / USB cameras, motion detection, loop recording and audio.

**v2.8.1** · Raspberry Pi OS / Debian 13（64-bit） · 简体中文 / English · [MIT](LICENSE)

## 功能 / Features

| 中文 | English |
| --- | --- |
| MJPEG 实时预览、浏览器 OSD、多区域编辑、far / near 双算法 | MJPEG live preview, browser OSD, editable regions and dual far / near detection |
| 事件预录与补录、暂停、倒计时、整帧与目标缩略图 | Event pre/post-roll, pause, countdown and full-frame/object thumbnails |
| 分段循环录像、事件优先、MP4 + AAC 音频与电平表 | Segmented loop recording, event priority, MP4 + AAC audio and level meter |
| 成像调节、配置与区域预设、延时摄影、云台舵机 | Imaging controls, settings/region presets, timelapse and pan/tilt servos |
| 定时命令、FIFO、事件钩子、媒体管理、归档与日志 | Scheduled commands, FIFO, event hooks, media management, archiving and logs |
| 密码登录、中英切换、外部存储检查、容量护栏、版本回滚 | Password login, language switch, external-storage checks, disk guards and rollback |

## 安装与访问 / Install and open

在树莓派上执行 / Run on your Raspberry Pi:

```bash
git clone https://github.com/cijiaomoxi/PiMotionCam.git
cd PiMotionCam
bash install.sh
```

打开 **http://pi.local:8080/**，或使用树莓派 IP。右上角切换语言。音频默认关闭，可在「媒体 → 音频」启用并选择麦克风。

Open **http://pi.local:8080/** or your Pi's IP address. Switch languages in the top bar. Audio is off by default; enable it and select a microphone under **Media → Audio**.

## 升级与回滚 / Upgrade and rollback

已有安装沿用原配置、媒体、日志和虚拟环境；每个版本保存在 `releases/`，由 `current` 选择。以下命令在开发电脑执行，SSH 密钥路径按实际情况填写。

Existing installs retain configuration, media, logs and the virtual environment. Versions stay in `releases/`, selected by `current`. Run these on your development computer with your SSH key path.

```bash
export PKC_HOST=pi@pi.local PKC_KEY="$HOME/.ssh/id_ed25519"
bash deploy.sh
bash deploy.sh --list
bash deploy.sh --rollback v2.8.0
```

## 文档与版本 / Documentation and release

- 使用 / Usage：[中文手册](docs/使用文档.md) · [English guide](docs/USAGE.en.md)
- 技术 / Technical：[中文](README.zh-CN.md) · [English](README.en.md)
- 更新 / Updates：[更新日志 / Changelog](CHANGELOG.md) · [发布包 / Releases](https://github.com/cijiaomoxi/PiMotionCam/releases)
- 验证 / Validation：[性能与实机验证 / Performance and hardware checks](docs/PERFORMANCE.md) · [上游功能对照 / Upstream coverage](docs/上游功能对照.md)

v2.8.1 优化多区域检测、音频电平、媒体统计和网页轮询，修复录像时序及暂停控制；保留 Python / Flask + 可选 C 加速，兼容原配置与 API。

v2.8.1 improves multi-region detection, audio metering, media statistics and browser polling, and fixes recording timing and pause controls while retaining Python / Flask, optional C acceleration and configuration/API compatibility.

## 已知限制 / Limitations

尚不支持浏览器实时音频、声音触发录像和 MMAL 硬件运动矢量；USB MJPEG 通路不支持旋转与镜像。

Live audio streaming, sound-triggered recording and MMAL motion vectors are not implemented. USB MJPEG capture does not support rotation or mirroring.

参考 **Bill Wilson** 的 [PiKrellCam](https://github.com/billw2/pikrellcam) 功能设计，本项目为非官方独立实现。PiMotionCam 使用 MIT 许可，上游使用 GPL-3.0。

Inspired by **Bill Wilson's** [PiKrellCam](https://github.com/billw2/pikrellcam). This is an unofficial, independent implementation. PiMotionCam uses MIT; upstream uses GPL-3.0.
