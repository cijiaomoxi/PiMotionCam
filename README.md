# pikrellcam-lite

**树莓派移动侦测录像服务 · Motion-detection recording for Raspberry Pi**

基于 libcamera / picamera2，支持 CSI 和 USB 摄像头，提供实时预览、运动事件录像、循环录像和带声音的 MP4。

Built on libcamera / picamera2, with CSI and USB camera support, live preview, motion-event recording, loop recording and MP4 recordings with sound.

**版本 / Version: v2.8.1** · **界面 / Interface: 简体中文 / English** · **许可 / License: [MIT](LICENSE)**

| 文档 / Documentation | 简体中文 | English |
| --- | --- | --- |
| 安装与使用 / Installation and usage | [使用文档](docs/使用文档.md) | [User guide](docs/USAGE.en.md) |
| 功能与技术细节 / Features and internals | [技术说明](README.zh-CN.md) | [Technical guide](README.en.md) |
| 本次优化与验证 / Optimization and validation | [性能与验证（双语）](docs/PERFORMANCE.md) | [Performance and validation (bilingual)](docs/PERFORMANCE.md) |
| 版本记录 / Release history | [更新日志 / Changelog](CHANGELOG.md) | [Releases](https://github.com/cijiaomoxi/pikrellcam_update/releases) |
| 与上游的差异 / Differences from upstream | [功能对照表](docs/上游功能对照.md) | [Limitations and coverage](README.en.md#known-limitations) |

## 功能 / Features

| 中文 | English |
| --- | --- |
| CSI：rpicam-vid 硬件 JPEG 或 picamera2；USB：V4L2 / ffmpeg MJPEG | CSI through rpicam-vid hardware JPEG or picamera2; USB through V4L2 / ffmpeg MJPEG |
| MJPEG 实时预览、浏览器 OSD、图形化多区域编辑、far / near 双算法 | MJPEG live preview, browser OSD, graphical motion regions and dual far / near detection |
| 事件预录与补录、暂停、录像倒计时、整帧与目标裁剪缩略图 | Event pre/post-roll, pause, recording countdown and full-frame/object thumbnails |
| 按时长分段的循环录像；事件录像优先 | Segmented loop recording with priority for motion events |
| 麦克风选择、预录音频缓冲、MP4 + AAC 合流、实时电平表 | Microphone selection, audio pre-roll buffer, MP4 + AAC muxing and a live level meter |
| 成像参数、配置与区域预设、延时摄影、云台舵机 | Imaging controls, settings/region presets, timelapse and pan/tilt servos |
| 定时命令、FIFO、事件钩子、媒体管理、远程归档与日志 | Scheduled commands, FIFO, event hooks, media management, remote archive and logs |
| 密码登录、中英切换、外部存储检查、容量护栏、版本回滚 | Password login, Chinese/English switch, external-storage checks, disk guards and version rollback |

## 安装 / Installation

适用 Raspberry Pi OS（Debian 13 / trixie，64 位）。安装脚本创建独立版本目录和 systemd 用户服务。

For Raspberry Pi OS (Debian 13 / trixie, 64-bit). The installer creates a versioned directory and a systemd user service.

```bash
git clone https://github.com/cijiaomoxi/pikrellcam_update.git
cd pikrellcam_update
bash install.sh
```

打开 **http://pi.local:8080/**，或把 `pi.local` 换成树莓派 IP。右上角切换 **简体中文 / English**。

Open **http://pi.local:8080/**, or replace `pi.local` with your Pi's IP address. Switch **简体中文 / English** in the top bar.

音频默认关闭；需要声音时，在「媒体 → 音频」启用并选择麦克风。

Audio is disabled by default. Enable it and select a microphone under **Media → Audio** to record sound.

## 升级与回滚 / Upgrade and rollback

已有安装的设备继续共用根目录下的配置、媒体、日志和虚拟环境。新版本保存在 `releases/`，`current` 指向运行版本。

Existing installations share configuration, media, logs and the virtual environment at the installation root. Versions are kept in `releases/`; `current` selects the running version.

```bash
# 在开发电脑部署 / Deploy from your development computer
PKC_HOST=pi@pi.local PKC_KEY="$HOME/.ssh/id_ed25519_pi_mcode" bash deploy.sh

# 查看版本 / List versions
PKC_HOST=pi@pi.local bash deploy.sh --list

# 回滚到已有版本 / Roll back to a retained version
PKC_HOST=pi@pi.local bash deploy.sh --rollback v2.8.0
```

## v2.8.1 优化 / Optimizations

同阈值和去噪半径的运动区域复用检测计算；音频 RMS 使用向量运算；媒体统计单次遍历并在状态接口缓存 3 秒；网页轮询等待上次请求完成，并在页面隐藏时暂停。磁盘剩余空间和存储安全检查继续实时执行。

Motion regions sharing a threshold and noise radius reuse detection work. Audio RMS uses vector operations. Media statistics use one directory pass and a three-second dashboard cache. Browser polls wait for completion and pause on hidden pages. Free-space and storage safety checks remain live.

保留 Python / Flask + 可选 C 加速架构；配置格式、API 和自动降级路径继续兼容 v2.8.0。检测结果与回退实现通过真实数组逐项比对。

The Python / Flask architecture and optional C acceleration are retained. Configuration, APIs and automatic fallback remain compatible with v2.8.0. Detection results are checked against the fallback implementation using real arrays.

## 已知限制 / Known limitations

浏览器实时音频流、声音触发录像、MMAL 硬件运动矢量尚未实现。USB MJPEG 通路仍不支持旋转与镜像。完整差异见[功能对照](docs/上游功能对照.md)和[技术说明](README.zh-CN.md)。

Live audio streaming, sound-triggered recording and MMAL hardware motion vectors are not implemented. Rotation and mirroring remain unsupported on the USB MJPEG path. See the [coverage table](docs/上游功能对照.md) and [technical guide](README.en.md) for details.

## 致谢与参考 / Acknowledgements and references

感谢 **Bill Wilson（[@billw2](https://github.com/billw2)）** 与 **[PiKrellCam](https://github.com/billw2/pikrellcam)** 社区的功能设计与使用经验。本项目是非官方独立实现，与 PiKrellCam 作者及 Raspberry Pi 官方无隶属或背书关系。本仓库许可见 [LICENSE](LICENSE)；上游采用 GPL-3.0。

Thanks to **Bill Wilson ([@billw2](https://github.com/billw2))** and the **[PiKrellCam](https://github.com/billw2/pikrellcam)** community for their feature design and experience. This is an unofficial, independent implementation, unaffiliated with or endorsed by PiKrellCam's author or Raspberry Pi. See [LICENSE](LICENSE) for this repository's license; upstream uses GPL-3.0.
