# 性能与兼容性验证 / Performance and compatibility

v2.8.1 · 2026-11-15

## 设计 / Design

保留 Python / Flask、libcamera / picamera2、V4L2 / ffmpeg 和可选 C 内核。配置键、API 返回字段和录制流程继续兼容 v2.8.0。

The Python / Flask, libcamera / picamera2, V4L2 / ffmpeg and optional C architecture is retained. Configuration keys, API response fields and recording behavior remain compatible with v2.8.0.

| 改动 / Change | 行为 / Behavior |
| --- | --- |
| 检测计算复用 / Shared detection | 同灰度阈值与去噪半径的大面积或重叠区域共用积分图；区域占比直接查询，包围盒通过前缀计数查边界。面积合计小于整帧的区域保持局部计算，避免小区域反而变慢。 / Large or overlapping regions sharing magnitude and noise settings reuse integral images. Counts use rectangle queries; bbox edges use prefix-count searches. Regions whose combined area is smaller than the frame keep local computation to avoid a sparse-layout regression. |
| 并发与缓冲安全 / Concurrency and buffer safety | C 检测工作区按调用分配；JPEG 输出不足时返回失败并扩容重试；C 接口验证数组尺寸、类型与连续性。 / Detection scratch belongs to each call. A full JPEG destination fails safely so the caller can retry. Arrays are validated and strided views are made contiguous. |
| 音频电平 / Audio meter | NumPy 使用 int64 平方求和，保持原 RMS 语义；独立音频工具保留无 NumPy 路径。 / NumPy sums int64 squares with the same RMS semantics; standalone tools retain a no-NumPy fallback. |
| 媒体统计 / Media statistics | scandir 单次读取文件元数据，状态接口共享 3 秒缓存；切换目录或写操作会失效。 / A single scandir pass reads metadata; dashboard requests share a three-second cache, invalidated by directory changes or writes. |
| 磁盘护栏 / Disk guards | 配额扫描始终读取当前文件大小；文件系统剩余空间与挂载检查不使用界面缓存。 / Quota scans always read current sizes. Filesystem free space and mount checks do not use the dashboard cache. |
| 网页轮询 / Browser polling | 等请求完成再安排下一次；相同 GET 复用在途请求；隐藏页面暂停，日志与音频只在对应标签页轮询。 / Polls wait for completion. Identical GETs share in-flight requests. Hidden pages pause polling; logs and audio poll on their respective tabs. |
| 部署 / Deployment | 上传时排除虚拟环境、媒体与本机编译文件；Git 检出保留元数据以继续支持网页升级；新目录先编译，再重启一次。 / Uploads exclude virtual environments, media and local binaries. Git checkouts retain metadata for web upgrades. Compilation occurs in the new directory before a single restart. |

## 4B 实测 / Raspberry Pi 4B measurements

2026-11-15，在同一台 4B、64 位 Raspberry Pi OS、Python 3.13.5、NumPy 2.2.4 上对比 v2.8.0（`8924d60`）和 v2.8.1。USB 摄像头、16 kHz 单声道音频和循环录像保持运行；每项预热 5 次、采样 80 次。表中为中位耗时，越低越好。

Measured on the same Pi 4B on 2026-11-15, running 64-bit Raspberry Pi OS, Python 3.13.5 and NumPy 2.2.4. The comparison is v2.8.0 (`8924d60`) versus v2.8.1. USB capture, 16 kHz mono audio and loop recording remained active. Each case has five warm-ups and 80 samples. Median latency is shown; lower is better.

| 场景 / Scenario | v2.8.0 | v2.8.1 | 变化 / Change |
| --- | ---: | ---: | --- |
| 状态接口 / State API | 107.964 ms | 7.433 ms | 耗时减少 93.1% / 93.1% less time |
| 每算法 8 个区域 / 8 regions per algorithm | 6.528 ms | 1.717 ms | 耗时减少 73.7% / 73.7% less time |
| 每算法 32 个区域 / 32 regions per algorithm | 23.156 ms | 2.553 ms | 耗时减少 89.0% / 89.0% less time |
| 每算法 1 个区域 / 1 region per algorithm | 1.431 ms | 1.459 ms | +0.028 ms |
| 设备实际小区域布局 / Device's configured small regions | 0.368 ms | 0.410 ms | +0.042 ms |
| 音频 RMS，2048 采样 / Audio RMS, 2048 samples | 1.263 ms | 0.049 ms | 耗时减少 96.1% / 96.1% less time |
| 音频 RMS，24000 采样 / Audio RMS, 24000 samples | 15.163 ms | 0.157 ms | 耗时减少 99.0% / 99.0% less time |

原始数据保留中位数、p95、采样次数和运行环境：[v2.8.0 基线](benchmarks/pi4-v2.8.0.json)、[实际区域基线](benchmarks/pi4-v2.8.0-configured.json)、[v2.8.1](benchmarks/pi4-v2.8.1.json)。状态接口为连续请求，包含三秒统计缓存命中的效果；不代表每次冷扫描只需 7 ms。实际区域基线另外运行，未改配置。

Raw results include medians, p95, sample counts and environment metadata: [v2.8.0 baseline](benchmarks/pi4-v2.8.0.json), [configured-region baseline](benchmarks/pi4-v2.8.0-configured.json), and [v2.8.1](benchmarks/pi4-v2.8.1.json). State API requests are consecutive and benefit from the three-second statistics cache; a cold scan is not claimed to take 7 ms. The configured-region baseline was a separate run without configuration changes.

小区域和单区域未获得检测提速；新增数组验证和线程安全工作区带来少量开销。这些是函数与接口测量，不能换算成整机 CPU 降幅、摄像头帧率增长或其它设备的保证值。保留现有 Python + C 架构即可解决已测热点，因此没有整体换语言重写。

Small-region and single-region detection did not speed up; array validation and call-owned scratch add some overhead. These are function/API measurements, not claims about whole-system CPU reduction, camera FPS gains or other devices. The existing Python + C architecture addresses the measured hot paths, so a complete language rewrite was unnecessary.

## 实机兼容性 / Hardware compatibility checks

| 验证 / Check | 结果 / Result |
| --- | --- |
| 原有音频、核心与 Web 检查 / Existing audio, core and Web checks | 57 + 136 + 70 = 263 项通过 / 263 passed |
| 新增检查 / New checks | 15 项通过；关闭 C 后 9 项通过、6 项按设计跳过 / 15 passed; with C disabled, 9 passed and 6 intentionally skipped |
| 在线 API 回归 / Live API regression | 64 项通过，0 失败，1 类破坏性操作跳过 / 64 passed, 0 failed; one destructive-operation category skipped |
| 网页轮询 / Browser polling | Node.js 4 项通过；实际网页中英文、预览、媒体、系统和帮助已查看 / 4 Node.js checks passed; Chinese/English, preview, media, system and help inspected in a real browser |
| USB + CSI 摄像头 / USB + CSI capture | USB V4L2、CSI OV5647 的 rpicam MJPEG 与 libcamera RGB888 均有 1280×720 有效 JPEG / Valid 1280×720 JPEG on USB V4L2 and CSI OV5647 via rpicam MJPEG and libcamera RGB888 |
| 事件与循环录像 / Event and loop recording | 真实触发、倒计时、事件优先和循环恢复；H.264 + AAC、10 fps、16 kHz 单声道；两段完整解码无错误，音视频时长差为 0 / Real trigger, countdown, event priority and loop resumption; H.264 + AAC, 10 fps, 16 kHz mono; both files decoded fully without errors and had equal audio/video durations |
| 配置恢复 / Settings restoration | 临时测试设置已恢复，并与升级前配置比对 / Temporary test settings restored and compared with the pre-upgrade configuration |

硬件结果：[摄像头](benchmarks/pi4-cameras.json)、[最终录像](benchmarks/pi4-recording.json)、[配置一致性与代码哈希](benchmarks/pi4-final-health.json)。这些文件只含验证元数据，不包含配置、密码或相机影像。原有媒体目录和历史发布目录保留。

Hardware results: [cameras](benchmarks/pi4-cameras.json), [final recordings](benchmarks/pi4-recording.json), and [settings parity and source hashes](benchmarks/pi4-final-health.json). These contain validation metadata, not configuration, passwords or camera images. Existing media and release directories were retained.

Mac 上的 C 独立检查通过 AddressSanitizer + UndefinedBehaviorSanitizer；4B 上通过 UBSan。该 Pi 的 ASan 在进入测试前初始化分配器失败，因此未声称其通过。Linux CI 模板已配置相同的 ASan + UBSan 检查，但云端尚未运行。

Standalone C checks passed AddressSanitizer + UndefinedBehaviorSanitizer on Mac and UBSan on the Pi. ASan failed during allocator initialization on this Pi before the tests began, so a Pi ASan pass is not claimed. The Linux CI template includes the same ASan + UBSan checks, but cloud CI has not run.

## 重现 / Reproduce

同一台设备、相同采样次数，分别对两个版本运行同一份脚本。基准不改变配置与媒体。`--url` 额外测量实际运行服务的状态接口。

Run the same script with identical sample counts against both versions on the same device. The benchmark does not change configuration or media. `--url` additionally measures the live service's state endpoint.

```bash
python tools/benchmark.py --repo /path/to/version --iterations 80 \
  --url http://127.0.0.1:8080 --output results.json

# 可选：测试实际区域布局 / Optional: measure the configured regions
python tools/benchmark.py --repo /path/to/version --iterations 80 \
  --config /path/to/config.json --output configured.json
```

测试图片为固定随机种子的 320×180 灰度图，含局部变化；每个场景使用 far / near 两组参数，每组各 1、8 或 32 个区域。音频分别为 2048 和 24000 个 S16_LE 采样。

Images are seeded 320×180 grayscale arrays with a local change. Each scenario uses two far / near parameter sets, each with 1, 8 or 32 regions. Audio buffers contain 2048 or 24000 S16_LE samples.

## 验证命令 / Validation commands

```bash
python -m pip install -r requirements-test.txt
python -c 'from core import native; ok, log = native.build(force=True); print(log); assert ok'
python tools/test_audio.py
python tools/test_v270.py --quiet
python tools/test_web_v270.py --quiet
python tools/test_optimizations.py
PKC_NO_NATIVE=1 python tools/test_optimizations.py
node --test tools/test_polling.cjs
bash package.sh --out /tmp/pkc-packages --no-zip
```

新增检查覆盖随机图像的逐区域结果、连续命中、包围盒、禁用 C 后的回退、并发检测、非连续数组、JPEG 缓冲容量、音频电平、目录变化和轮询调度。可启用的 CI 模板见 [tools/ci/checks.yml](../tools/ci/checks.yml)，面向 Python 3.11 与 3.13。

New checks cover per-region random-image parity, consecutive hits, bounding boxes, C-disabled fallback, concurrent detectors, strided arrays, JPEG destination capacity, audio levels, directory changes and poll scheduling. The [CI template](../tools/ci/checks.yml) targets Python 3.11 and 3.13.

当前 GitHub OAuth 授权仅有 `repo`，缺少 `workflow`，GitHub 拒绝推送 `.github/workflows/` 中的新文件。已有 GitHub SSH 登录也不可用，因此模板保存在 `tools/ci/`；具有工作流权限的账号可将其复制到 `.github/workflows/checks.yml` 后提交以启用。本次实际验证为 Mac 和树莓派上的上述检查。

The current GitHub OAuth authorization includes `repo` but lacks `workflow`; GitHub rejected the new file under `.github/workflows/`. Existing GitHub SSH authentication was also unavailable. The template is retained under `tools/ci/`; an account with workflow permissions can copy it to `.github/workflows/checks.yml` and commit it to enable CI. Validation performed for this update is the Mac and Pi testing described above.

GPIO 舵机、其它相机型号、USB 拔盘与长期运行需要在对应硬件环境另行验证。单次设备测试不能代替这些条件下的验证。

GPIO servos, other camera models, USB unplug behavior and sustained operation require validation on the corresponding hardware. One device run does not establish those properties.
