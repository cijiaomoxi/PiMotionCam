# PiMotionCam

**树莓派摄像头监测与自动录像工具。** 支持 CSI / USB 摄像头、运动侦测、循环录像和音频。

**Camera monitoring and automatic recording for Raspberry Pi.** Supports CSI / USB cameras, motion detection, loop recording and audio.

**v2.8.2** · Raspberry Pi OS / Debian 13（64-bit） · 简体中文 / English · [MIT](LICENSE)

| 中文 | English |
| --- | --- |
| MJPEG 实时预览、可编辑侦测区域、far / near 双算法 | MJPEG preview, editable detection regions and dual far / near detection |
| 事件预录与补录、手动录像、运动抓拍、事件缩略图 | Event pre/post-roll, manual recording, motion photos and thumbnails |
| 分段循环录像、事件优先、MP4 + AAC 音轨 | Segmented loop recording, event priority and MP4 + AAC sound |
| 浏览器实时音频、麦克风增益、声音触发、独立 MP3 录制 | Live browser audio, microphone gain, sound triggers and audio-only MP3 |
| CSI / USB 旋转与镜像；可选软件方向分析、矢量显示和统计 | CSI / USB rotation and mirroring; optional software direction, vectors and statistics |
| 延时摄影、云台与位置预设、日出日落及定时命令 | Timelapse, pan/tilt presets, solar schedules and scheduled commands |
| 配置预设、事件钩子、FIFO、可选签名 TCP / 组播控制 | Settings presets, hooks, FIFO and optional signed TCP / multicast control |
| USB / 外部存储、日历归档、空间保护、密码与中英界面 | External storage, calendar archives, disk guards, password protection and bilingual UI |

## 安装 / Install

```bash
git clone https://github.com/cijiaomoxi/PiMotionCam.git
cd PiMotionCam
bash install.sh
```

打开 / Open **`http://<树莓派IP / Pi-IP>:8080`**。安装器沿用 `pikrellcam-lite.service` 和 `~/pikrellcam-lite`，以便保留原配置、媒体及历史版本。

The installer retains `pikrellcam-lite.service` and `~/pikrellcam-lite` for existing configurations, recordings and release history.

```bash
systemctl --user status pikrellcam-lite
journalctl --user -u pikrellcam-lite -f
```

升级现有设备 / Upgrade an existing device:

```bash
PKC_HOST=pi@<Pi-IP> bash deploy.sh
```

## 文档 / Documentation

- [中文说明](README.zh-CN.md) · [English overview](README.en.md)
- [中文使用手册](docs/使用文档.md) · [English guide](docs/USAGE.en.md)
- [2.8.2 新功能与操作 / New features and controls](docs/V2.8.2.md)
- [上游功能与差异 / Upstream coverage and differences](docs/上游功能对照.md)
- [更新日志 / Changelog](CHANGELOG.md) · [发布 / Releases](https://github.com/cijiaomoxi/PiMotionCam/releases)
- [性能与验证 / Performance and validation](docs/PERFORMANCE.md) · [2.8.2 验证记录 / Validation record](docs/V2.8.2-VALIDATION.md)

## 兼容性 / Compatibility

保留 libcamera / picamera2、Python / Flask 和可选 C 加速。USB 无变换时继续使用 MJPEG 直通；旋转、软件效果、防抖和录像内字幕会增加处理开销，均可按需启用。实时音频需要可用的 ALSA 采集设备，先启用监听，再点击播放。

Uses libcamera / picamera2, Python / Flask and optional C acceleration. USB MJPEG remains passthrough when no transform is requested. Rotation, effects, stabilization and burned-in captions add processing and are optional. Live audio requires a working ALSA capture device; enable monitoring, then click Listen live.

本项目为参考 [Bill Wilson 的 PiKrellCam](https://github.com/billw2/pikrellcam) 功能设计的独立实现。现代系统不支持旧 MMAL 硬件运动矢量；软件方向分析、效果和签名网络协议不宣称与旧实现完全相同。新功能的实机验证状态见验证记录。

An independent implementation inspired by [Bill Wilson’s PiKrellCam](https://github.com/billw2/pikrellcam). Modern systems do not provide legacy MMAL hardware vectors. Software analysis/effects and the signed network protocol do not claim exact equivalence. See the validation record for hardware testing status. PiMotionCam uses MIT; upstream uses GPL-3.0.
