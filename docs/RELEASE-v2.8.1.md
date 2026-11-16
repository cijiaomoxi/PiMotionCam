# PiMotionCam v2.8.1 — 性能优化与双语说明 / Performance and bilingual documentation

## 中文

原名 pikrellcam-lite。统一项目名称、控制台与发布包，版本号保持 2.8.1；修复英文默认区域标签，配置与用户自定义名称保持原值。

保留 v2.8.0 的现有功能、配置格式和 API，继续使用 Python / Flask + 可选 C 加速架构。

- 多区域检测复用同阈值、同去噪半径的计算；小区域保持局部计算。
- 音频电平向量化；媒体统计单次扫描，状态接口共用 3 秒缓存。
- 网页轮询等待请求完成，隐藏时暂停，日志和音频按标签页刷新。
- 修复满队列丢弃最新帧、C 工作区并发冲突、JPEG 容量不足和帧率多计一次的问题。
- 2026-11-16 补充：重启后正确显示已保存的暂停录像状态；侦测总开关实际生效，重新启用时清空旧命中计数。
- 项目首页中英并列，完整中文与英文指南均保留，扩充网页双语帮助。
- 部署前编译 C 内核，只重启一次；发布包排除本机二进制、虚拟环境和运行数据。

4B 实测中位耗时：状态接口 **108 → 7.4 ms**；每算法 8 个区域 **6.53 → 1.72 ms**；音频 RMS（2048 采样）**1.263 → 0.049 ms**。小区域检测约 **0.4 ms**，没有提速。完整方法、原始数据和局限见 [性能验证](PERFORMANCE.md)。这些数字不代表整机 CPU 或摄像头帧率提升。

原有 263 项检查、新增 17 项检查和在线 64 项回归通过；C 关闭后的回退通过；USB 与 CSI OV5647 两条路径均测试。事件与循环录像为 H.264 + AAC、10 fps，完整解码无错误，测试设置已恢复。GPIO 舵机、USB 拔盘和长期运行尚未做实机验证。

**安装与升级**：下载并解压 `tar.gz` 或 `zip`，在树莓派上进入解压后的 `pimotioncam` 目录，运行 `bash install.sh`。已有安装继续使用根目录的配置、媒体和虚拟环境；历史版本保存在 `releases/`。从开发电脑部署可运行 `PKC_HOST=pi@pi.local bash deploy.sh`，回滚可运行 `PKC_HOST=pi@pi.local bash deploy.sh --rollback v2.8.0`。详见[中文指南](使用文档.md)。

## English

Formerly pikrellcam-lite. The repository, console and packages now use PiMotionCam while the version stays 2.8.1. Built-in region labels follow the UI language without changing saved configuration or custom names.

Retains v2.8.0 features, configuration format and APIs on the existing Python / Flask architecture with optional C acceleration.

- Share detection work for regions with matching magnitude/noise settings; keep local work for sparse layouts.
- Vectorize audio metering and scan media in one pass, with a shared three-second dashboard cache.
- Wait for poll completion, pause hidden pages, and poll logs/audio on their respective tabs.
- Fix newest-frame retention on full queues, concurrent C scratch, undersized JPEG output and an extra frame-rate interval.
- Follow-up on 2026-11-16: display saved recording pause correctly after restart, honor the motion master switch and clear old hit counts before re-enabling.
- Provide a bilingual project home, preserve full Chinese/English guides and extend in-app help.
- Compile before switching releases and restart once; omit local binaries, virtual environments and runtime data from packages.

Pi 4B median latency: state API **108 → 7.4 ms**; eight regions per algorithm **6.53 → 1.72 ms**; audio RMS with 2048 samples **1.263 → 0.049 ms**. Small-region detection remains around **0.4 ms**, without a speedup. See [performance validation](PERFORMANCE.md) for methods, raw results and limits. These are not whole-system CPU or camera-FPS claims.

All 263 existing checks, 17 new checks and 64 live regression checks passed, along with the C-disabled fallback. USB and both CSI OV5647 paths were exercised. Event and loop recordings contain H.264 + AAC at 10 fps and decode without errors. Test settings were restored. Physical GPIO servos, USB unplug behavior and sustained operation were not tested.

**Installation and upgrade**: download and extract the `tar.gz` or `zip`, enter the extracted `pimotioncam` directory on the Pi, and run `bash install.sh`. Existing installations retain root-level configuration, media and the virtual environment; historical versions stay in `releases/`. From a development computer, use `PKC_HOST=pi@pi.local bash deploy.sh`; to roll back, use `PKC_HOST=pi@pi.local bash deploy.sh --rollback v2.8.0`. See the [English guide](USAGE.en.md).
