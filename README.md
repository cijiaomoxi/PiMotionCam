# pikrellcam-lite v2

在 Raspberry Pi OS（Debian 13 / trixie，64 位）上运行的**移动侦测录像服务**，
对标官方 [PiKrellCam](https://github.com/billw2/pikrellcam) 的全部网页功能，
使用官方新相机栈 **libcamera / picamera2** 实现，并额外支持 **USB 摄像头**。

访问地址：**http://pi.local:8080/**

当前版本：**v2.5.0**

> [!NOTE]
> **本项目是非官方独立实现**，与 [PiKrellCam](https://github.com/billw2/pikrellcam) 的作者、
> 与 Raspberry Pi 官方均无隶属或背书关系。项目在功能与交互上对标 PiKrellCam，
> 代码为全新实现，详见[致谢与参考](#致谢与参考)。

---

## 致谢与参考

本项目 **pikrellcam-lite**（GitHub 仓库：`pikrellcam_update`）
是在 **[PiKrellCam](https://github.com/billw2/pikrellcam)** 的功能设计与使用体验之上重新实现的多语言版本。
在此向原作者 **Bill Wilson（[@billw2](https://github.com/billw2)）** 及 PiKrellCam 社区致以诚挚的谢意。

| 参考项目 | 作者 | 链接 | 上游许可 |
| --- | --- | --- | --- |
| PiKrellCam | Bill Wilson ([@billw2](https://github.com/billw2)) | <https://github.com/billw2/pikrellcam> | GPL-3.0 |

- **对标的功能面**：复刻了 PiKrellCam 的网页功能、配置项、定时命令与操作流程；
  并在其基础上新增 **简体中文 / English 双语界面**、**原生加速内核**、**USB 摄像头支持**、
  **版本化部署与一键安装/回滚**。
- **实现方式不同**：PiKrellCam 建立在 Debian 13 已移除的私有 MMAL 相机栈上，
  本项目改用官方 **libcamera / picamera2** 新栈重写采集与运动检测链路
  （见「为什么不是官方 PiKrellCam」）。技术栈也完全不同：上游为 C + PHP，本项目为 Python / Flask。
- **代码来源声明**：本项目为**独立实现**，仓库中**不包含 PiKrellCam 的源代码**，也**不是其 fork**；
  仅参考上游的功能设计、交互流程与文档表述。本仓库以 **MIT** 许可发布（见 [LICENSE](LICENSE)），
  上游 PiKrellCam 遵循 **GPL-3.0**。
- **命令名引用**：文中出现的 `tl_start` / `on_motion_begin` 等为上游的功能性命令标识符，
  引用它们**仅用于说明配置与命令的兼容关系**，不代表复制了上游实现。
- **商标声明**：PiKrellCam、Raspberry Pi、Raspberry Pi OS 均为其各自权利人的商标或注册商标，
  此处仅作致谢性引用，与权利人无隶属或背书关系。
- **上游链接**：<https://github.com/billw2/pikrellcam>

> 如果你认为这里的致谢信息需要补充或更正，欢迎提交 issue 或 PR。

---

## 为什么不是官方 PiKrellCam

官方 PiKrellCam 最后一次提交停在 2020-06-08，构建在已被 Debian 13 删除的旧相机栈之上：

| 官方依赖 | 当前系统状态 |
| --- | --- |
| `/opt/vc` + `libbrcmmmal-dev` / `libbcm-host-dev` | 仓库中已下架，`/opt/vc` 不存在 |
| 预编译二进制 ELF 32-bit ARM (armhf) | 系统无 `/lib/ld-linux-armhf.so.3`，无法执行 |
| MMAL 硬件运动矢量 | 属于旧私有栈，新 libcamera 栈不向用户态暴露 |

源码里 163 处 `mmal_` 调用无法在纯新栈下直接编译运行。

本实现保留 PiKrellCam 的**使用体验**，把运动检测从**硬件运动矢量**换成**帧差分**，
从而在保留中文环境与 Raspberry Pi Connect 的前提下正常工作。

---

## 功能对照

| 官方 PiKrellCam | 本实现 |
| --- | --- |
| MJPEG 网页预览 + OSD 叠加 | ✅ `/video_feed` multipart MJPEG 流 + 浏览器端 HTML OSD 叠加（零 CPU 成本） |
| MMAL 运动矢量检测 | ✅ 帧差分 + 邻域密度去噪，等效官方的 "sparkle" 过滤 |
| 预录 / 补录 / 事件间隔 | ✅ `pre_seconds` / `post_seconds` / `event_gap_seconds` |
| 多个运动区域，任意数量/尺寸/位置 | ✅ 归一化矩形，预览图上拖拽绘制 |
| 区域图形化实时编辑 | ✅ 在预览上拖拽绘制、右键选中后可移动/缩放、双击重命名 |
| 区域配置按名称保存/载入 | ✅ 区域预设 |
| 双运动检测算法并行（远/近） | ✅ `far`（远处小慢目标）/ `near`（近处大目标），灵敏度分别可调 |
| 设置预设（settings presets） | ✅ 命名配置预设，一键激活，可绑定舵机位置 |
| 缩略图 = 运动目标裁剪 | ✅ 同时生成整帧缩略图与运动目标包围盒裁剪图 |
| 运动开始/结束/抓图事件命令 | ✅ `on_motion_begin` / `on_motion_end` / `on_motion_preview_save` 钩子 |
| 命令调度（时间 + 频率） | ✅ `at-commands.conf` + 网页表格，支持星期区间与固定间隔 |
| FIFO 命令接口 | ✅ `~/.pikrellcam/commands.fifo` |
| 录像暂停 | ✅ `POST /api/record {action:"pause"}` |
| 延时摄影 + hold | ✅ `tl_start` / `tl_hold` / `tl_end`，自动合成 MP4 |
| 舵机控制（PWX GPIO / ServoBlaster） | ✅ RPi.GPIO / ServoBlaster 自动探测，位置预设、平移俯仰限位、平滑移动 |
| 密码保护 | ✅ 会话登录，可随时开关 |
| 一键升级 | ✅ `git pull` + 重启 |
| USB 摄像头 | ✅ ffmpeg + V4L2 双后端，网页随时切换 CSI / USB（v2.1.0+） |
| 多版本共存与回滚 | ✅ `releases/` 逐版本独立目录 + `current` 软链，历史版本全部保留（v2.1.0+） |
| 原生加速 | ✅ 帧处理 C 扩展（ctypes 加载），全链路 4.71x，CPU 减半（v2.2.0+） |
| ISP 硬件 JPEG 直通 | ✅ CSI 走 `rpicam-vid`，软件 JPEG 编码归零（`jpeg_ms=0`），总 CPU 再降 11%（v2.3.0+） |
| 采集通路可切换 | ✅ 网页上随时在 ISP 硬件 JPEG / 原始 RGB 之间切换，无需重启服务（v2.3.0+） |
| 画面旋转 / 镜像 | ✅ 0/180 由 ISP 零成本完成，90/270 自动软件旋转（v2.4.0+） |
| 卡死自愈 | ✅ 取帧看门狗 + 自动降级（分辨率→帧率→回退 RGB888），管线僵死自动重建（v2.3.0+） |
| 多语言界面 | ✅ 简体中文 / English 双语，前后端共用同一份语言包，顶栏一键切换（v2.5.0+） |
| 视频/抓拍/延时/归档页面 | ✅ 媒体标签页 + 远程归档（scp） |
| 系统日志页面 | ✅ 实时滚动日志 |
| 帮助页面 | ✅ 内置说明 |
| 音频流 | ⚠️ 需 USB 声卡，未实现 |
| 硬件运动矢量 | ❌ 新栈不提供，改用帧差分 |

---

## 性能设计（面向树莓派 3B 及更新设备）

这是本次重写的重点。实测瓶颈不是语言，而是**每帧的重复工作**。

| 优化点 | 说明 |
| --- | --- |
| **原生加速内核（C 扩展）** | v2.2.0 起，帧处理最耗时的三个环节改由 `core/_pkc_native.c` 编译成 `.so`、用 ctypes 加载，见下方「原生加速」 |
| **一次编码，多处复用** | 每帧只做一次 JPEG 编码，结果同时供网页预览、录像帧、缩略图使用；旧版每帧重复解码/编码 |
| **先降采样再转灰度** | 侦测只在 320×180 的目标像素上算灰度，**绝不能**写 `np.dot(frame[..., :3], [0.299,0.587,0.114])`——numpy 对 3 维数组与 1 维向量做 dot 会走批量矩阵乘路径，720p 下单帧要几十秒，足以卡死采集线程 |
| **浏览器端 OSD** | 时间戳、状态、FPS、区域框全部由 HTML 叠加，不在图像上烧字 |
| **流式预览** | multipart MJPEG 长连接，取代旧版每 200ms 轮询一次完整 JPEG |
| **边录边编码** | ffmpeg 以 `image2pipe` 边收帧边编码，不落中间文件、不二次读盘 |
| **按型号降档** | Pi 3/3B/Zero 自动切到 640×480 @8fps，Pi 4/5 用 1280×720 @10fps |
| **取帧硬超时** | `Job.get_result(timeout=8)`，传感器异常时线程不会永久挂死 |
| **硬件 H.264 编码** | Pi 4/5 优先用 `h264_v4l2m2m`，失败自动回退 `libx264` |

---

## 原生加速（v2.2.0+）

把帧处理链路里最耗时的三段从 Python/numpy 挪进 C，编译成 `core/_libpkc.so`、用 ctypes 加载。

### 实测数据（树莓派 4，1280×720，检测分辨率 320×180）

| 环节 | 纯 Python | 原生 C | 加速比 |
| --- | --- | --- | --- |
| 灰度降采样 | 35.77 ms | **0.85 ms** | 42.1x |
| 双算法运动检测 | 22.76 ms | **2.26 ms** | 10.1x |
| JPEG 编码 | 18.62 ms | **13.29 ms** | 1.4x |
| **单帧全链路** | **77.16 ms** | **16.40 ms** | **4.71x** |

服务端端到端（同一台机器 A/B 对照）：

| 后端 | 单核 CPU 占用 | jpeg_ms |
| --- | --- | --- |
| 纯 Python | 42.3% | 17.3 ms |
| 原生 C | **20.7%** | **12.7 ms** |

**这正是树莓派 3B 能流畅运行的钥匙**：3B 的单核性能约为 4 的 1/2.5～1/3，
纯 Python 后端在 3B 上光帧处理就要占满单核（42.3% × ~2.7 ≈ 114%），
而原生内核折算后约 55%，10fps 有充足余量。

### 帧率余量

原生内核把单帧处理压到 16.4ms（理论上限 61fps），而 CSI 传感器本身支持到 30fps
（`FrameDurationLimits` 下限 33333µs）。实测配置帧率能完全跟上：

| 配置 fps | 实际 fps | jpeg_ms | 单核 CPU |
| --- | --- | --- | --- |
| 10 | 10.0 | 12.5 ms | 20.7% |
| 15 | 15.0 | 12.5 ms | 29.5% |
| 20 | 20.0 | 13.1 ms | 38.6% |
| 30 | 30.0 | 12.4 ms | 57.5% |

`jpeg_ms` 不随帧率变化，说明采集是瓶颈、编码有余量。
**树莓派 3B 建议保持 10fps**（默认���），4/5 可上调到 20～30fps。

### 自动编译与降级

- `build_native.sh` 负责编译，`deploy.sh` 发布后自动执行，`install.sh` 安装时也会执行。
- 需要 `gcc` 与 `libjpeg62-turbo-dev`（脚本会在缺失时自动 apt 安装）。
- **编译失败不影响服务**：自动回落到纯 Python + numpy 实现，功能完全一致，只是慢。
- 想临时关掉加速做对比或排障：设环境变量 `PKC_NO_NATIVE=1`。
- 加速后端可在网页「系统」页或日志中确认（`native acceleration enabled`）。

### 一致性保证

C 内核与原 Python 实现经过逐位比对：帧差分占比、包围盒、连续命中计数**完全相同**；
JPEG 输出字节数相同、PSNR > 138 dB（视觉等同）。
灰度图有 26/57600 像素存在 ±1 的差异（float32 与 double 的截断边界），不影响检测判定。

---

### 关于 CSI 的 MJPEG 通路（v2.3.0 起）

早期版本结论是「CSI 不能走 MJPEG」——这其实只对了一半：
`create_video_configuration(main={"format": "MJPEG"})` 确实会被 libcamera 拒绝
（`RuntimeError: Bad format JPEG in stream main`），但**换成 `rpicam-vid` 就能让 ISP 硬件编码 JPEG**。

两条通路的实测对比（Pi 4 + ov5647 + 1280×720@10，v2.4.0 复测）：

| 通路 | 采集链路总 CPU | `jpeg_ms` | 管线重建 |
| --- | --- | --- | --- |
| **MJPEG**（`rpicam-vid` + ISP 硬件编码） | **≈ 29.9%** | **0.00** | 0 |
| RGB888（picamera2 + C 内核软件编码） | ≈ 33.7% | 20.37 | 0 |

所以 CSI 的 `camera.format=auto` 现在**优先选 MJPEG**，网页上也可随时切换
（摄像头下拉框旁新增「采集通路」选择器）。

> ⚠️ **踩坑提醒：`rpicam-vid` 必须显式加 `-t 0`。**
> 它的 `--timeout` 默认值是 **5 秒**，含义是"程序最多跑 5 秒"，
> 不是"等帧超时"。不加这个参数，采集进程会在第 5 秒自行退出并打印
> `Halting: reached timeout of 5000 milliseconds.`，
> 看起来极像"相机管线卡死"，实际只是程序时限到了——
> 表现上和服务每 16 秒重建一次管线完全一样，极易误判。
> 加上 `-t 0` 后实测 45 秒 436 帧、精确 10.00 fps 不间断。

> 补充：**USB 摄像头不经过 libcamera**，走 ffmpeg + V4L2 直读，
> 若设备原生支持 MJPEG 则 `-c:v copy` 零转码直通，无此编码开销。详见下文「USB 摄像头支持」。

### AE（自动曝光）的两个坑

libcamera 的控制项分「标量」和「数组」，**类型错了会直接让整个进程 abort**（`signal=ABRT`）：

| 控制项 | 类型 | 范围 |
| --- | --- | --- |
| `ExposureTime` | 标量 int | 1..66666 µs |
| `AnalogueGain` | 标量 float | 1.0..16.0 |
| `AeConstraintMode` | 标量 int | 0..3 |
| `FrameDurationLimits` | **数组** | ← 只有它是数组 |

- 给标量控制项传元组，值会变成数组，libcamera 内部按 int 读取时命中
  `Assertion '!isArray_' failed`，进程当场 abort。
- libcamera **没有"给曝光/增益封顶"的语义**：给 `ExposureTime`/`AnalogueGain`
  赋一个标量等于**锁死成手动曝光**，自动曝光从此失效，暗光下画面明显变暗。
- `AeConstraintMode` 是**测光模式**（0=Normal 1=Highlight 2=Shadows 3=Custom），
  误设成 1(Highlight) 会让 AE 按高光测光，画面同样明显变暗。

所以本实现让 AE 保持**全自动原生**，只把 `AeConstraintMode` 作为可选安全旋钮
（`camera.ae_constraint`，默认 `normal`）；真正的防卡死靠的是采集看门狗 + 自动降级。

---

## USB 摄像头支持

v2.1.0 起，程序同时支持 **CSI（树莓派官方排线摄像头）** 与 **USB 摄像头**，
可在网页「系统 → 摄像头」下拉框里随时切换，无需重启树莓派。

### 为什么 USB 必须绕开 libcamera

Debian 13 的 libcamera 只带树莓派专用的 RPi 处理器，**不含 `u8vidcam`（V4L2 UVC）处理器**，
因此 libcamera（以及 `rpicam-vid`）**根本枚举不到 USB 摄像头**。
本项目为此实现了双后端：

| 后端 | 适用设备 | 采集方式 |
|---|---|---|
| `rpicam` | CSI 排线摄像头（默认） | rpicam-vid，ISP 硬件 JPEG 编码，JPEG 字节直传 |
| `libcamera` | CSI 排线摄像头（备选） | picamera2，RGB888 主流 + C 内核软件 JPEG |
| `v4l2` | USB / UVC 摄像头 | ffmpeg 直读 `/dev/videoN`，MJPEG 优先直通 |

### 自动识别与切换

- `GET /api/cameras` 返回枚举到的全部摄像头（CSI + USB）。
- `POST /api/cameras/select`，body `{"device": "/dev/video0"}` 立即切换；
  `"auto"` 交回自动选择，`"0"`/`"1"` 表示 libcamera 索引。
- 配置项 `camera.device`（`auto` / libcamera 索引 / `/dev/videoN`）持久化到 `config.json`。
- 切换后采集、检测、录像链路整体重建，无需重启服务。

### USB 摄像头的性能建议

- **优先用 MJPEG 直通**：绝大多数 UVC 摄像头原生输出 MJPEG，
  本程序会自动探测 `v4l2-ctl --list-formats-ext`，命中则 `-c:v copy` 直通，零转码。
- 若设备只支持 YUYV，则由 ffmpeg 转 MJPEG，CPU 开销高于直通，建议降低 `camera.fps`。
- 采集分辨率/帧率取设备支持的最大值，可在「侦测调参」里单独设定检测分辨率与检测帧率
  （检测分辨率独立于预览分辨率，Pi 3B 上建议 320×240）。

### 手工确认设备

```bash
# 列出所有视频设备及其支持的格式
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext

# 试读 2 秒
ffmpeg -f v4l2 -input_format mjpeg -video_size 1280x720 -framerate 10 \
  -i /dev/video0 -t 2 -f image2pipe -c:v copy - | wc -c
```

> **注意**：Debian 13 的 `v4l2loopback` 虚拟设备在**写入端**决定格式。
> 想让虚拟设备暴露 MJPEG，写入端要推 MJPEG：
> `ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=10 -f v4l2 -vcodec mjpeg -q:v 5 /dev/video1`

---

## 多语言（v2.5.0+）

界面支持 **简体中文** 与 **English**，前后端**共用同一份语言包**：
`core/locales/<语言代码>.json`，结构是扁平的 `{"key": "文案"}`。

- 顶栏右上角有语言下拉框，切换后写回 `config.json` 的 `web.language` 并整页重载；
- `web.language` 可以是 `auto`（按浏览器 `Accept-Language` 自动协商，认不出来则回落简体中文）
  或某个具体语言代码；
- 后端自己产生的消息（鉴权失败、非法语言等）也走同一份语言包，不是只有界面翻译了。

```bash
# 读取当前语言、全部可选语言与文案字典
curl -s http://pi.local:8080/api/i18n

# 切换为英文（持久化到 config.json）
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"language":"en-US"}' http://pi.local:8080/api/i18n

# 恢复自动选择
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"language":"auto"}' http://pi.local:8080/api/i18n
```

### 新增一种语言

只要两步，**前端不需要任何改动**：

1. 复制 `core/locales/zh-CN.json` 改成新语言代码（例如 `ja-JP.json`），把文案翻译过去；
2. 在 `core/i18n.py` 的 `LANGUAGES` 里登记一行：

```python
LANGUAGES = {
    "zh-CN": {"name": "Chinese (Simplified)", "native": "简体中文"},
    "en-US": {"name": "English", "native": "English"},
    "ja-JP": {"name": "Japanese", "native": "日本語"},   # ← 新增
}
```

新语言会自动出现在顶栏的下拉框里。缺 key 时自动回落到简体中文，不会出现空白界面。

> 文案目录由 `tools/apply_i18n.py` 从源码自动抽取生成（`tools/i18n_table.py` 是中英对照表）。
> 改完前端文案后跑一次 `python3 tools/apply_i18n.py` 即可同步语言包，
> 脚本会报告「未收录文案」和「表里没用上的条目」，不会悄悄漏翻译。

---

## 部署

### 方式一：版本化发布（推荐）

每个版本都独立保留，**永不覆盖**：

```bash
cd pikrellcam-lite
bash deploy.sh            # 发布当前工作目录 → releases/<时间戳>-v<版本>/
bash deploy.sh --list     # 列出全部已保留版本 + 当前运行版本
bash deploy.sh --rollback v2.0.0   # 回滚到指定历史版本
```

`deploy.sh` 通过 tar over ssh 上传，落到 `~/pikrellcam-lite/releases/<时间戳>-v<版本>/`，
然后把 `current` 软链指向新目录并重启服务。历史版本原封不动留在 `releases/` 下，随时可回滚。

### 方式二：首次安装

```bash
# 1. 拷贝到树莓派
scp -r -i ~/.ssh/id_ed25519_pi_mcode pikrellcam-lite pi@pi.local:~/

# 2. 在树莓派上安装
ssh -i ~/.ssh/id_ed25519_pi_mcode pi@pi.local 'bash ~/pikrellcam-lite/install.sh'

# 3. 打开浏览器
open http://pi.local:8080/
```

`install.sh` 会：安装缺失的系统包（`python3-picamera2` / `python3-numpy` / `python3-pil` /
`ffmpeg` / `python3-venv`）→ 建立 `venv`（`--system-site-packages`，复用系统的 picamera2 与 numpy）
→ `pip install flask` → 写入 `~/.config/systemd/user/pikrellcam-lite.service`
（`ExecStart` 指向 `current` 软链）→ `systemctl --user enable --now` → `loginctl enable-linger`。

开机自启已验证：重启后服务自动拉起并占住相机。

### 目录结构与版本管理

```
~/pikrellcam-lite/
├── current -> releases/20261109-2213-v2.1.0   # 软链，指向当前运行版本
├── releases/                                     # 所有历史版本，各自独立完整
│   ├── 20261108-2319-v2.0.0/
│   └── 20261109-2213-v2.1.0/
├── media/     # 录像/截图/事件索引（各版本共享，升级不丢）
├── logs/      # 运行日志（各版本共享）
├── venv/      # Python 虚拟环境（各版本共享）
└── config.json# 配置（各版本共享）
```

**版本目录与共享数据的边界**：代码、模板、前端资源全部在版本目录里；
`media/`、`logs/`、`venv/`、`config.json` 挂在共享根目录，升级和回滚都不影响录像与设置。

**回滚**只需重指软链并重启：

```bash
ln -sfn releases/20261108-2319-v2.0.0 ~/pikrellcam-lite/current
systemctl --user restart pikrellcam-lite.service
```

也可以用脚本一步完成（`--rollback` 按版本号匹配最新一个目录）：

```bash
bash deploy.sh --rollback v2.0.0
```

回滚已实测：切到 v2.0.0 后服务照常拉起、相机照常出帧（`/api/state` 里 `release` 字段消失，
正是旧版本没有该字段所致），再切回 v2.1.3 同样正常。

---

## 常用运维命令

```bash
ssh pi@pi.local

systemctl --user status  pikrellcam-lite.service   # 查看状态
systemctl --user restart pikrellcam-lite.service   # 重启
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f   # 实时日志
tail -f ~/pikrellcam-lite/logs/pikrellcam.log      # 文件日志（自动轮转）

# 换端口
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home()/"pikrellcam-lite/config.json"
c = json.loads(p.read_text()); c["web"]["port"] = 8090
p.write_text(json.dumps(c, indent=2))
EOF
systemctl --user restart pikrellcam-lite.service
```

> `journalctl --user` 在本机不可用，改用 `journalctl _SYSTEMD_USER_UNIT=<单元名>`。

### 忘记密码怎么办

密码保存在 `config.json` 的 `web.password_hash`。把它改成空字符串再重启服务即可关闭密码保护：

```bash
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home()/"pikrellcam-lite/config.json"
c = json.loads(p.read_text()); c["web"]["password_hash"] = ""
p.write_text(json.dumps(c, indent=2))
EOF
systemctl --user restart pikrellcam-lite.service
```

---

## 参数说明

`config.json`：

### camera

| 键 | 默认 | 含义 |
| --- | --- | --- |
| `resolution` | `[1280,720]` | 采集分辨率（改动需重启服务） |
| `fps` | `10` | 采集帧率 |
| `jpeg_quality` | `72` | 预览/录像帧 JPEG 质量 |
| `detect_resolution` | `[320,180]` | 侦测用的降采样尺寸 |
| `detect_fps` | `10` | 侦测帧率 |
| `buffer_count` | `6` | libcamera 缓冲帧数 |
| `device` | `auto` | 摄像头：`auto` / libcamera 索引（如 `0`）/ USB 设备（如 `/dev/video0`） |
| `format` | `auto` | 采集通路：`auto`（CSI→ISP 硬件 MJPEG）/ `MJPEG` / `RGB888`；USB 后端自动探测 MJPEG 直通 |
| `rotation` | `0` | 画面旋转 0/90/180/270（MJPEG 通路 0/180 由 ISP 零成本完成，90/270 自动改走 RGB888 软件旋转） |
| `flip` | `none` | 镜像：`none` / `horizontal` / `vertical` / `both` |
| `ae_constraint` | `normal` | AE 测光模式：`normal` / `highlight` / `shadows` / `custom` |
| `stall_timeout` | `8.0` | 取帧看门狗：超过该秒数没有新帧就重建采集管线 |
| `min_fps` | `0.5` | 帧率下限：低于该值持续 `stall_timeout` 秒同样判定为卡死 |

### motion

| 键 | 默认 | 含义 |
| --- | --- | --- |
| `enabled` | `true` | 是否开启侦测（网页可热切换） |
| `algorithms.far.magnitude_limit` | `12` | far 算法单像素灰度差阈值，越大越迟钝 |
| `algorithms.far.count_limit` | `0.006` | far 算法区域内变化像素占比阈值 |
| `algorithms.far.consecutive_frames` | `2` | far 算法连续命中帧数 |
| `algorithms.far.noise_filter` | `2` | far 算法邻域去噪半径（0 关闭） |
| `algorithms.near.*` | `28 / 0.02 / 2 / 3` | near 算法同上，面向近处大目标 |
| `regions` | 全画面 | 运动区域数组，元素为 `{name,x,y,w,h,enabled}`，坐标归一化到 0~1 |
| `region_presets` | `{}` | 命名区域预设 |

### record / timelapse / web / media / servo / hooks

| 键 | 默认 | 含义 |
| --- | --- | --- |
| `record.pre_seconds` | `5` | 触发前预录秒数 |
| `record.post_seconds` | `8` | 触发后补录秒数 |
| `record.event_gap_seconds` | `10` | 两次事件之间的最小间隔 |
| `record.max_event_seconds` | `120` | 单个事件最长时长，防止持续移动导致内存无限增长 |
| `record.max_disk_gb` | `8` | 录像目录上限，超限自动删最旧 |
| `record.encoder` | `auto` | `auto` / `h264_v4l2m2m` / `libx264`（`auto` 优先硬件编码器，失败自动回退软件编码器） |
| `record.frame_write_timeout` | `8` | 单帧写入编码器的最长等待秒数；超时判定编码器卡死，放弃本次录像而不拖死服务 |
| `record.encoder_close_timeout` | `15` | 结束录像时等待 ffmpeg 写完 `moov` 的最长秒数 |
| `record.encoder_cooldown` | `60` | 编码器卡死后暂停尝试录像的秒数 |
| `timelapse.period` | `30` | 延时摄影抓帧间隔（秒） |
| `web.port` | `8080` | 监听端口 |
| `web.password_hash` | `""` | `sha256:<hex>`，空表示不启用密码保护 |
| `media.dir` | `""` | 媒体目录，空表示用应用目录下 `media/`；可指向 `/mnt/usb` 等 |
| `media.archive_target` | `""` | 远程归档目标，形如 `user@host:/path` |
| `servo.pan_pin` / `tilt_pin` | `18` / `17` | BCM 引脚号 |
| `servo.positions` | 3 个预设 | `[{name,pan,tilt}]`，每个位置可绑定设置预设 |
| `hooks.*` | `""` | 事件钩子命令，支持 `{id} {video} {thumb} {time} {date} {duration} {algorithm} {region} {media_dir}` 占位符 |

---

## 定时命令

除了网页上的调度表，还可以直接编辑 `~/.pikrellcam/at-commands.conf`（**热重载，无需重启**）：

```
Mon-Fri 07:30 "@tl_start 30"
Mon-Fri 09:00 "@tl_hold off"
Mon-Fri 17:00 "@tl_hold off"
Fri 18:00 "@tl_end"
Mon 7:30 "record on"
```

可用的内部命令：

```
record on | off | pause      still              tl_start [秒]     tl_hold on|off
tl_end                       motion_enable on|off|toggle
motion load_regions 名称     motion limits <magnitude_limit> <count_limit>
servo goto 名称              servo set <pan> <tilt>      start | stop | restart
```

脚本也可以往 FIFO 写命令（不需要 `@` 前缀）：

```bash
echo "record off" > ~/.pikrellcam/commands.fifo
```

---

## 目录结构

```
~/pikrellcam-lite/
├── current -> releases/<版本>   # 当前运行版本软链
├── releases/<版本>/             # 每个版本一个独立完整目录，全部保留
│   ├── krellcam.py              # 入口
│   ├── install.sh               # 安装脚本
│   ├── core/
│   │   ├── app.py               # 服务容器 + 内部命令调度
│   │   ├── camera.py            # 双后端采集（libcamera CSI + ffmpeg/V4L2 USB）
│   │   ├── detect.py            # 多区域双算法帧差分检测
│   │   ├── recorder.py          # 事件录制 + ffmpeg 管道 + 缩略图
│   │   ├── presets.py           # 命名配置预设
│   │   ├── scheduler.py         # 定时命令 + FIFO
│   │   ├── timelapse.py         # 延时摄影
│   │   ├── servo.py             # 舵机云台
│   │   ├── hooks.py             # 事件钩子
│   │   ├── state.py             # 运行时状态
│   │   ├── config.py            # 配置加载/热重载 + 共享根目录解析
│   │   ├── util.py              # 工具函数
│   │   └── web.py               # Flask 路由
│   ├── templates/               # index.html / login.html
│   └── static/                  # app.js / style.css
├── config.json          # 配置（共享）
├── media/               # 录像与截图（共享）
│   ├── videos/          # 事件 MP4 与延时摄影成片
│   ├── stills/          # 缩略图（含 _obj 运动目标裁剪图）
│   └── events.json      # 事件索引
├── logs/                # 运行日志（共享）
└── venv/                # Python 虚拟环境（共享）
```

---

## 已知限制

- **摄像头必须重新上电才能从"前端超时"恢复**。Pi 的 `reboot` 不会切断 3.3V 电源轨，
  传感器无法真正复位；需要**拔掉电源等 10 秒再插上**。症状：`Camera frontend has timed out!`，
  传感器能通过 I²C 枚举但不出帧。
- 相机被其他进程独占时会报 `Pipeline handler in use by another process`；先结束占用进程再启动服务。
- 浏览器与树莓派需在同一局域网；跨网访问请自行做端口转发或隧道。
- 帧差分对整体光照突变（开关灯、窗帘飘动）较敏感；调高 `magnitude_limit` 与 `count_limit` 可缓解。
- **摄像头朝向很关键**：镜头正对显示器时，屏幕内容变化会被当成"移动"，服务会持续触发录像。
- 未实现音频流（需 USB 声卡）。
- **录像文件必须正常收尾才可播放**。MP4 的索引（`moov`）由 ffmpeg 在退出时写入，断电或 `kill -9` 会留下打不开的文件；服务启动时会自动清理这类残留文件，所以录像列表里出现的条目一定可以播放，但断电瞬间正在录的那一段仍会丢失。
- Flask 使用开发服务器；内网自用足够，如需公网暴露请自行加反向代理。
