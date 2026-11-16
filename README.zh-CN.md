# PiMotionCam v2.8.2

[中英首页](README.md) · [English](README.en.md)

PiMotionCam 是用于树莓派的摄像头监测与自动录像工具，基于 libcamera / picamera2，支持 CSI 和 USB 摄像头，并提供简体中文、英文网页。

- 实时预览、检测区域编辑、far / near 双算法、软件运动方向与矢量分析。
- 预录与补录、手动录像、运动抓拍、循环录像、整帧与目标缩略图。
- 带声音的 MP4、实时监听、麦克风增益、声音触发和独立 MP3 录制。
- CSI / USB 旋转和镜像，可选裁剪、软件效果、防抖与录像内字幕。
- 延时摄影、云台预设与巡航、配置预设复制 / 移动、定时与日出日落调度。
- FIFO、事件钩子、可选的签名 TCP / 组播控制、日历归档、外部存储及磁盘保护。

推荐 Raspberry Pi 4B 和 64 位 Raspberry Pi OS / Debian 13。保留 Python / Flask 与可选 C 加速，无需重装系统。运行期依赖沿用系统的 numpy、Pillow、ffmpeg、ALSA 与相机工具。

```bash
git clone https://github.com/cijiaomoxi/PiMotionCam.git
cd PiMotionCam
bash install.sh
```

安装后访问 `http://<树莓派IP>:8080`。默认未设置网页密码，可在“系统”页设置。实时监听默认关闭，需在“媒体”页启用并点击“监听声音”。

现有设备可运行 `PKC_HOST=pi@<树莓派IP> bash deploy.sh`。程序目录仍为 `~/pikrellcam-lite`，服务仍为 `pikrellcam-lite.service`；共享配置、媒体与历史版本沿用原路径。升级保留旧版本，支持回退。

详细操作见 [使用手册](docs/使用文档.md) 和 [2.8.2 新功能](docs/V2.8.2.md)，功能差异见 [上游对照](docs/上游功能对照.md)。2.8.2 当前的测试和部署进度见 [验证记录](docs/V2.8.2-VALIDATION.md)。

软件方向分析替代旧 MMAL 运动矢量；旧硬件专有曝光模式、完整 OSD 菜单树及网络原始协议不宣称兼容。USB 旋转、裁剪、软件效果、防抖和录像内字幕会解码、重编码，启用时需要预留 CPU 资源。无变换的 USB MJPEG 保持直通。

本项目以 MIT 许可独立实现，功能设计参考 GPL-3.0 许可的 [Bill Wilson / PiKrellCam](https://github.com/billw2/pikrellcam)。
