# Changelog

All notable changes to PiMotionCam are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 2.8.2 — 2026-11-16

- 浏览器实时 PCM 音频、共享 ALSA 采集、增益、声音触发及独立 MP3。
- USB MJPEG 实际旋转 / 镜像；无变换时保留直通。
- 可选软件方向 / 矢量 / burst 分析，CSV、非阻塞 FIFO、运动起止日志及相机移动静置。
- 立即手动录像、外部触发、运动抓拍、持久化命名序号、整帧缩略图修复。
- 可选裁剪、软件效果、防抖、独立尺寸抓拍和烧入字幕；不宣称 MMAL 硬件兼容。
- 预设复制 / 移动、舵机反相 / 步进 / 巡航与绑定预设、日出日落调度、六种新增钩子。
- 本地 / 已挂载 NFS/SMB 日历归档及校验；签名 TCP / 组播和客户端工具默认关闭。
- 主题、扩展链接、CLI、日志行数和相机设置导入 / 导出；完整中英控件。
- 修复 PCM 块时长少算样本宽度、音频切片浮点截断、监听误开录像音轨、FIFO 停止阻塞、调度跨午夜及网页伪造本地 shell 来源等问题。

Live browser audio, shared capture, gain, sound triggers and MP3; USB transforms with passthrough retained when off; optional software motion analysis and telemetry; manual/external recording and motion photos; persistent naming; image processing/captions; preset/servo/solar extensions; verified calendar archives; opt-in signed network controls; and bilingual settings. Legacy MMAL, full upstream OSD menus and raw wire compatibility are not claimed. See [validation status](docs/V2.8.2-VALIDATION.md) before deployment.

## Versions

| Version | Date | Highlights |
| --- | --- | --- |
| [2.8.1](#281---2026-11-15) | 2026-11-15 | 性能优化与双语说明 / Performance and bilingual documentation |
| [2.8.0](#280---2026-11-14) | 2026-11-14 | Audio subsystem — recordings with sound |
| [2.7.0](#270---2026-11-13) | 2026-11-13 | Loop recording + imaging parameter matrix |
| [2.6.0](#260---2026-11-13) | 2026-11-13 | Record to USB / external storage with safe unplug handling |
| [2.5.0](#250---2026-11-11) | 2026-11-11 | Bilingual interface (Chinese / English) |
| [2.4.0](#240---2026-11-10) | 2026-11-10 | ISP hardware JPEG path, AE rework, working rotation / flip |
| [2.3.2](#232---2026-11-10) | 2026-11-10 | Native kernel reports the release it was built from |
| [2.3.1](#231---2026-11-10) | 2026-11-10 | Automatic degradation and clean handle release |
| [2.3.0](#230---2026-11-10) | 2026-11-10 | Native acceleration kernel, frame-fetch watchdog |
| [2.2.0](#220---2026-11-09) | 2026-11-09 | Event hooks, hot-reloaded scheduled commands |
| [2.1.5](#215---2026-11-09) | 2026-11-09 | One camera selector shared by two tabs |
| [2.1.4](#214---2026-11-09) | 2026-11-09 | Maintenance release |
| [2.1.3](#213---2026-11-09) | 2026-11-09 | Event frame counter |
| [2.1.2](#212---2026-11-09) | 2026-11-09 | Tab deep links |
| [2.1.1](#211---2026-11-09) | 2026-11-09 | `GET /api/release`, camera selector on the preview tab |
| [2.1.0](#210---2026-11-09) | 2026-11-09 | USB cameras, versioned publishing, servo pan/tilt |
| [2.0.0](#200---2026-11-08) | 2026-11-08 | First release |

---

## [2.8.1] - 2026-11-15

### 中文

- 2026-11-16 项目更名为 PiMotionCam，统一仓库、控制台、双语说明和发布包名称；版本仍为 2.8.1，现有安装路径与服务兼容。
- 修复英文界面的默认区域名：列表、画面叠加和事件记录随语言显示“全画面 / Full frame”及“区域2 / Region 2”，保留配置和自定义名称。
- 多区域检测按阈值和去噪参数复用计算；保留原判定、连续命中和包围盒语义。
- 音频电平改用 int64 向量计算，保留独立工具的无 NumPy 路径。
- 媒体统计单次扫描，状态接口共用 3 秒缓存；配额与剩余空间护栏仍读取当前值。
- 网页轮询等待请求完成、复用相同 GET，在后台暂停；日志和音频按当前标签页刷新。
- 修复视频队列满时未保留最新帧、C 检测共享工作区并发冲突和 JPEG 输出容量不足的处理。
- 修正实测帧率把 N 个时间戳当成 N 段间隔的问题，避免配置 10 fps 被误估为 11 fps、缩短视频时间轴。
- 登录前允许加载静态资源；回归工具恢复原有侦测、暂停与语言设置。
- 2026-11-16 补充修复：暂停状态从已保存配置读取，避免重启后界面错误显示为可录制。
- 2026-11-16 补充修复：侦测总开关实际停止事件触发；暂停时更新背景帧并清空连续命中，恢复时重新计数。
- README 首页改为中英双语，保留完整的中文与英文技术说明和使用文档，扩充双语网页帮助。
- 部署包排除虚拟环境、媒体和本机二进制；Git 检出保留元数据以支持网页升级；切换前编译，服务只重启一次。
- 新增真实数组、并发、缓冲容量、缓存与轮询检查，以及 Python 3.11 / 3.13 CI 模板（尚未启用）。
- 性能测量与硬件验证范围见 [PERFORMANCE.md](docs/PERFORMANCE.md)。

### English

- Renamed to PiMotionCam on 2026-11-16 across the repository, console, bilingual docs and release packages. The version remains 2.8.1; existing installation paths and services stay compatible.
- Localize built-in region names in lists, overlays and event cards, preserving saved configuration and custom names when switching languages.
- Reuse detection work across regions sharing magnitude/noise settings, preserving hit, consecutive-frame and bbox behavior.
- Vectorize audio RMS with int64 arithmetic, retaining the no-NumPy path for standalone tools.
- Scan media in one pass and share a three-second dashboard cache; quota and free-space guards still use current values.
- Wait for poll completion, coalesce identical GETs and pause hidden pages. Poll logs/audio on their respective tabs.
- Fix newest-frame retention on full queues, concurrent C detection scratch and undersized JPEG destinations.
- Estimate frame rate from N−1 intervals for N timestamps, avoiding a 10 fps stream being measured as 11 fps and shortening the video timeline.
- Serve login static assets before authentication; restore the original motion, pause and language settings after regression tests.
- Follow-up on 2026-11-16: read the paused state from saved configuration so a restart cannot incorrectly display recording as enabled.
- Follow-up on 2026-11-16: honor the motion master switch, refresh the baseline and clear consecutive hits while disabled, then count fresh hits when re-enabled.
- Introduce a bilingual README landing page, preserve full Chinese/English technical and user guides, and expand bilingual in-app help.
- Exclude virtual environments, media and local binaries from deployment; retain checkout metadata for web upgrades, compile before switching and restart once.
- Add real-array, concurrency, capacity, caching and polling checks, with a Python 3.11 / 3.13 CI template (not yet enabled).
- See [PERFORMANCE.md](docs/PERFORMANCE.md) for measurements and the scope of hardware validation.

## [2.8.0] - 2026-11-14

The audio subsystem: **recordings with sound**. A microphone is captured continuously into a memory ring buffer and
muxed into the finished clip, so both loop segments and event recordings carry an audio track that stays in sync
with the picture.

### Added

- **`core/audio.py` — the audio subsystem.**
  - *Device discovery.* All ALSA capture devices are enumerated (`arecord -l`) and enriched with their USB path
    from `/proc/asound/cards`, so the device list can tell "the microphone on the same USB port as the camera"
    from "some other USB microphone". The default selection prefers **the microphone on the same USB port as the
    camera** (a USB camera's own microphone sits on that very port), then any USB device, and only then anything
    else. The ALSA path and the sysfs path spell the port differently, so both are normalised to a port number
    (`1.3`) before comparing them.
  - *Continuous capture.* A resident `arecord -q -D plughw:N,M -f S16_LE -r <rate> -c <ch> -t raw` process feeds
    a **PCM ring buffer** in memory (180 seconds by default). Each block is timestamped with the moment it was
    read, minus its own duration. The device list is cached for ten seconds, because `arecord -l` spawns a
    subprocess and the UI polls the status every second.
  - *Window slicing.* `slice_wav(t0, t1)` cuts the audio for a wall-clock time window out of the ring buffer and
    **pads the missing parts with silence**, so the result is exactly as long as the window and the picture never
    drifts. A window that falls completely outside the buffer returns nothing.
  - *Muxing.* `mux_audio()` runs `ffmpeg -c:v copy -c:a aac -b:a Nk -movflags +faststart`. The video is **not
    re-encoded** — only the audio track is added. AAC is used instead of the upstream's MP3 because MP4 supports
    AAC natively: no second container pass, and browsers and phones play the result directly.
- **The audio track does not go into the encoder.** It is sliced out of the ring buffer **after** the recording is
  finished and then muxed in. Feeding ALSA straight into the encoder would have been the obvious approach, but an
  event recording starts with a *pre-roll* (`record.pre_seconds`, 5 seconds by default): the picture at the
  beginning is from five seconds ago, so the sound at that moment must be too. The audio track of an event
  recording therefore starts at the moment of the **earliest frame in the pre-roll buffer**, and the audio track
  of a loop segment starts at the moment the segment started. The end of the window is computed from the video's
  own timeline (frame count ÷ the frame rate the encoder actually used), not from the wall clock at close time —
  otherwise the track would be nearly a second longer than the picture.
- **Muxing happens in a background thread** (`pkc-audio-mux`, with a queue). The capture thread feeds a single
  encoder and must not be blocked, so the ffmpeg run happens after the recording has been closed.
- The muxing output file is written **into the same directory as the video**: `/tmp` is a tmpfs on the Pi, and
  renaming across filesystems fails with `EXDEV`. If the mux fails the original video is left untouched and
  ffmpeg's error goes to the log.
- `record.audio_enabled` (default `false` — a machine without a microphone should not report an error all day),
  `record.audio_device` (`auto` / `hw:N,M` / `plughw:N,M`), `record.audio_rate` (4000–48000, default 16000),
  `record.audio_channels` (1–2, default 1), `record.audio_bitrate` (16–256 kbps, default 64) and
  `record.audio_buffer_seconds` (30–900, default 180).
- `GET /api/audio` reports the configuration, the runtime state, the live level and the list of capture devices;
  `POST /api/audio` stores `enabled`, `device`, `rate`, `channels`, `bitrate` and `buffer_seconds`, clamping
  out-of-range values and applying the change immediately. `GET /api/state` gained an `audio` section.
- The `audio on|off|status` internal command.
- An "音频 / Audio" panel on the Media tab: switch, device drop-down, sample rate, channel count and a
  **live level meter**. The device drop-down is what makes "record with a different microphone" possible: every
  ALSA capture device on the machine is listed, so an external USB microphone can be selected instead of the one
  built into the camera. The AAC bitrate and the length of the ring buffer have no control on the panel —
  they are set through `POST /api/audio` or `config.json`.
- 19 new strings in each language pack (518 in total).
- **A recording countdown on the picture.** While an event recording is running, the OSD overlay shows how long it is
  still going to run (`录制中 00:17`): an event clip ends when the movement stops for `record.post_seconds`, or when
  it hits `record.max_event_seconds`, whichever comes first, so the countdown is the time to the earlier of the two.
  When only the loop recorder is running, the same line shows the time left in the current segment (`循环段 00:14`).
  The numbers come from `Recorder.record_status()` and are published as the `record` section of `/api/state`.
- `tools/test_audio.py` — 57 offline unit tests for the device parsing, the port normalisation, the device
  selection order, the ring buffer, the window slicing (including the silence padding) and the WAV packing.

### Fixed

- **Event recordings are no longer ten times too long.** The measured frame rate was sampled over a window that
  started when the service started. When the camera took a while to produce its first frames — which is exactly
  what happens right after a restart — that window was mostly idle, the measured rate came out below 0.1 fps and
  was clamped to 1 fps, and the encoder then timestamped every frame one second apart: a 120-second event
  produced a file claiming to be 1203 seconds long. The sampling window now starts at the **first frame**, a
  window with fewer than five frames is treated as noise and ignored, and a measured rate below 2 fps is never
  trusted — the configured rate is used instead.
- **The audio track is no longer about a second longer than the picture.** The end of the audio window was taken
  from the wall clock at the moment the recorder closed, but closing the encoder takes a few hundred milliseconds
  to a second, so the track carried roughly a second of extra sound at the end. The window now ends where the
  video ends.
- **Recordings made right after a restart have sound again.** The microphone was started *after* the camera, and
  opening the camera takes tens of seconds while it waits for the V4L2 stream. For the first half minute after a
  restart the recordings were silent — and the first event after a restart had no audio track at all, because the
  time window fell entirely before the microphone had recorded anything. The microphone is now started **before**
  the camera so the ring buffer warms up immediately, and the device is re-checked once the camera is up, because
  only then is it known which USB port the camera sits on.
- **The interface no longer serves stale JavaScript after an upgrade.** Flask sends static files with a
  `max-age` of twelve hours by default, so a browser that had the console open kept using the old `app.js` and
  `style.css` — the new panels and the recording countdown simply did not appear until the cache happened to
  expire. Static files are now sent without caching.

### Notes

- The audio stream of the upstream (`www/audio_stream.php`, listening to the live audio in the browser) and
  **audio-triggered recording** (`audio_trigger_video` / `audio_trigger_level`) are **not** implemented. They are
  separate subsystems: the first is a live streaming path, the second needs continuous level detection against a
  threshold. This release covers "recording with sound".
- The upstream's `audio_gain_dB` has no counterpart here — the gain is a property of the device and is set with
  `alsamixer`. The upstream's `box_MP3_only` is not implemented either; the output is always MP4 with AAC.
- The microphone used for the real-machine test is the one built into a USB "Generalplus WEB CAM", which ALSA
  exposes as `plughw:3,0` and which natively records 16 kHz mono (48 kHz stereo is rejected by the device; the
  `plughw:` plugin converts it). The audio of a microphone on a **different** USB port was verified the same way
  the code selects it: with a kernel-provided loopback sound card standing in for a second, independent
  microphone, the recorder produced a clip whose audio track came from that device alone.

---

## [2.7.0] - 2026-11-13

Two features that were still missing compared with the upstream PiKrellCam: continuous **loop recording** and a
full **imaging parameter matrix** (brightness, contrast, saturation, sharpness, denoise, exposure, metering,
exposure compensation, ISO, shutter, white balance, digital zoom).

### Added

- **Loop recording** (`loop.enabled`, `loop.segment_seconds`, `loop.max_disk_percent`, `loop.quality`).
  While enabled the camera records continuously and splits the footage into fixed-length segments under
  `media/loop/`. The disk cap follows the upstream semantics: it is a percentage of the **whole filesystem**
  (`loop_diskusage_percent`), not of the media folder, so the number stays meaningful after switching to a USB
  drive. When the cap is exceeded the oldest segments are deleted — that is what a loop recorder is for.
- **Loop recording yields to event recording.** The Pi's H.264 hardware encoder lives on `/dev/video31` and only
  one ffmpeg instance can use it at a time, and the capture thread feeds a single encoder. So the two recorders
  are mutually exclusive by construction: when motion is detected the current loop segment is closed, the event
  clip is recorded with the hardware encoder, and the loop resumes on the next frame. This is the same state
  machine the upstream uses (`VCB_STATE_LOOP_RECORD` / `VCB_STATE_MOTION_RECORD`).
- The disk guard from 2.6.0 now also reclaims loop segments. The reclamation order is
  **loop segments → event recordings → timelapse**: a loop segment is the least valuable of the three (it is
  continuous coverage by definition and the oldest ones are the intended ones to overwrite), while an event clip
  carries a specific moment that triggered the recording.
- `GET /api/loop` and `POST /api/loop` (switch it on/off, change the segment length, the disk cap and the CRF),
  the `loop` configuration section, the `loop on|off|status` internal command, and a "循环录像 / Loop recording"
  panel on the Media tab with a button to delete the loop footage.
- **`core/imaging.py` — the imaging parameter matrix.** One set of backend-independent parameters (14 of them),
  each with a fixed range that matches the upstream MMAL semantics: `brightness` 0..100 (50 = normal),
  `contrast` / `saturation` / `sharpness` -100..100 (0 = normal, saturation -100 = pure greyscale), `ev` -10..10,
  `iso` 0..3200 (0 = automatic), `shutter` in microseconds (0 = automatic), `zoom` 100..300 %, plus the
  `denoise`, `exposure`, `metering` and `awb` enumerations.
- The parameters are translated into whatever the active capture path speaks:
  - **rpicam-vid** (CSI, ISP hardware JPEG) → command-line flags. These are *startup* flags, so changing a value
    restarts the capture process; the web UI says so explicitly.
  - **picamera2 / libcamera** (CSI, raw RGB) → `set_controls()`, i.e. live, without restarting the camera.
  - **USB cameras** → `v4l2-ctl --set-ctrl`. The available controls are probed with `--list-ctrls` first, each
    value is scaled into the control's own range, and the parameters a camera does not implement are reported as
    unsupported instead of failing the whole command.
- `GET /api/imaging` returns the current values, the parameter schema, the active backend and the list of
  parameters the backend does not support; `POST /api/imaging` stores and applies them.
- An "成像参数 / Imaging" panel on the Detection tab. The controls are **generated from the schema** returned by
  the backend, so adding a parameter only means editing `core/imaging.py` — no template or JavaScript changes.
  Parameters the current capture path cannot do are greyed out and disabled.
- `tools/test_v270.py` — 101 offline unit tests covering the parameter normalisation, the three backend mappings,
  the loop state machine (segment rotation, yielding to an event, resuming afterwards), the loop disk cap and the
  reclamation order. It runs on a Mac without numpy / Pillow (they are stubbed) and on the Pi with the real
  libraries.
- `tools/test_web_v270.py` — 37 integration tests for the two new endpoints, driven through the Flask test
  client: request handling, value clamping, persistence, the camera restart on the rpicam path, and the new
  `loop` section of `/api/state`. It needs Flask (skipped with a hint when it is missing) and needs no camera.
- 82 new strings in each language pack (497 in total).

### Fixed

- **Recorded videos are now as long as they actually are.** The capture thread handed every frame the camera
  produced to the recorder, while the encoder timestamps the frames with the *configured* frame rate. A camera
  that ignores the requested frame rate (10 fps configured, 30 fps delivered — common for USB cameras) therefore
  produced a 20-second recording that claims to be 60 seconds long: a 3× slow motion. The capture path now
  throttles the frames handed to the recorder to the configured frame rate (the preview keeps the camera's native
  rate), and the encoder additionally uses the *measured* frame rate, so a camera that is slower than requested
  no longer produces fast-forward footage either. Event recordings were affected by the same bug.
- The loop panel now tells the real reason when nothing is being recorded: pausing the recorder pauses loop
  recording as well (the same semantics as the upstream `pause` flag), and the panel says so instead of silently
  showing "enabled". It also shows the frame rate that is really used for recording.

### Notes

- The upstream `image_effect` (negative, oil painting, cartoon …) is **not** implemented. Those effects are an
  MMAL feature and have no counterpart in libcamera / rpicam-vid / V4L2; implementing them in software would cost
  a JPEG decode plus an encode on every frame, which is exactly the kind of per-frame cost this project avoids.
  Greyscale — the only effect that actually matters for surveillance — is already covered by pulling
  `saturation` down to -100, which the ISP does for free.
- Digital zoom is a centre crop (`--roi` on rpicam-vid, `ScalerCrop` on libcamera), so it costs resolution
  rather than field of view.

---

## [2.6.0] - 2026-11-13

The external-storage release: recordings can be written to a USB drive or any other mounted filesystem, and
pulling that drive out no longer silently fills up the SD card.

### Added

- `core/storage.py` — storage discovery and validation. It enumerates the candidate mount points
  (`/media`, `/run/media`, `/mnt`), classifies each one as internal / USB / SD card / external, reports the free
  space, and validates a target before it is used. The validation is deliberately strict: the path must be a real
  mount point, it must not be the root filesystem, and writability is proven by actually creating a temporary file
  instead of trusting the permission bits.
- `GET /api/storage` lists the detected devices together with the current storage state; `POST /api/storage`
  switches the recording target and the two safety switches.
- The `media.dir`, `media.require_mount` and `media.fallback_internal` configuration keys.
- `StorageMonitor` — a background thread that re-validates the target every three seconds and publishes the
  result to the runtime state (`storage_available`, `storage_fallback`, `storage_path`, `storage_reason`).
- A "存储位置 / Storage location" panel on the Media tab: the detected devices, the free space, the two safety
  switches, and the current state. The top bar turns into a warning as soon as the target becomes unavailable.
- 22 new strings in each language pack for the storage panel, plus 9 for the disk monitoring (414 in total).
- `docs/上游功能对照.md` — an item-by-item comparison against the upstream [billw2/pikrellcam](https://github.com/billw2/pikrellcam):
  which features are covered, which are partially covered, which are missing, and which ones pikrellcam-lite has that
  upstream does not.
- **A real free-space guard for the disk** (`record.min_free_gb`, 1 GB by default). The disk limit is a *media quota*:
  it may be set to 128 GB even on a 28.7 GB SD card, and then it never triggers. The free-space floor is what
  actually protects the card — below it, the oldest recordings are removed automatically, and if that is not enough,
  recording is paused instead of writing the filesystem to 100 %.
- The top bar now shows the **real free space** of the target filesystem (`Disk · free 20.9 GB`) instead of
  "media usage / quota", and turns red when the space drops below the floor. The detection tab shows both numbers
  side by side under the disk limit slider, plus a new "free space floor" slider.
- The storage panel lists the **free / total space of every candidate device**, so an external drive can be
  compared with the SD card before it is selected.

### Changed

- **The scheduled commands can run arbitrary shell commands again.** The web interface and the documentation both
  promised it, but the implementation only ever dispatched the internal commands — an `at-commands.conf` entry such as
  `daily 08:00 "python3 /home/pi/sync.py"` silently did nothing. The official PiKrellCam runs `at-commands.conf`
  entries through the shell, so pikrellcam-lite now does the same: an entry that is not an internal command is passed
  to the shell. Only `~/.pikrellcam/at-commands.conf` gets this — the command table in the web interface is writable
  over the network and therefore still restricted to internal commands.
- `at-commands.conf` accepts the `start` / `hour` / `minute` / `5minute` time specifications as well; they are
  translated into a fixed minute interval.
- The event index (`events.json`) always lives in the internal storage. It used to follow `media.dir`, which meant
  that unplugging the USB drive also took the event list with it. Existing indexes are picked up automatically.
- `Config.media_dir()` now resolves the directory that is actually written to, which can differ from the configured
  one while the fallback is active. `Config.media_dir_configured()` still returns the configured target, and
  `Config.internal_media_dir()` returns the internal storage.
- The recording, the snapshots and the timelapse all write through the runtime target, so switching storage takes
  effect immediately — no restart needed.

### Fixed

- **Setting the disk limit above the size of the disk could fill the card.** The limit was compared against the
  *media files* only, so a 128 GB limit on a 28.7 GB card never triggered: recording simply continued until the
  filesystem was 100 % full. An ext4 root partition at 100 % means no log can be written, no configuration can be
  saved and the device may no longer boot. The free-space floor now closes this gap.
- The disk quota only counted the video files, not the snapshots and the time-lapse clips, while the top bar
  counted everything — the two numbers never matched. Both now use the same figure.
- **Switching to an external drive did not re-check the free space.** The guard now re-evaluates the new target
  immediately after the switch, in the API response and every three seconds in the background.
- The storage panel labelled the free space as "current usage".
- The 22 storage strings introduced in v2.6.0 had only been added to the language packs, not to the i18n source
  table — re-running `tools/apply_i18n.py` would have dropped all of them. They are now in the table as well.
- `err.activateFailed` and `btn.goto` were missing from the language packs and showed up as raw keys in the
  interface.
- **A USB drive that was pulled out could fill up the SD card.** The mount point stays behind as an empty
  directory on the SD card, so a path-existence check happily reported "writable" and the recordings kept going
  into the system partition. Long runs therefore ended with an unbootable device. Three things prevent this now:
  the target must still be a mount point at the moment of writing, the recorder checks this before every single
  event, and `StorageMonitor` re-checks it continuously. When the target is gone, recording is paused with a
  visible warning instead of falling back to the SD card.
- `check_target()` reported "no write permission" for the root filesystem, because the permission check ran
  before the root-filesystem check. The root filesystem is now recognised first, so the message names the actual
  problem.

> Quality assurance: the storage layer was verified with an offline test suite covering mount detection, the
> unplugged-drive case, `require_mount` on and off, the root-filesystem rejection, and the fallback behaviour. The
> checks run against a substituted mount table, so they are deterministic and do not need physical hardware.
>
> The disk guards were verified with a second offline suite (29 checks) covering: the media quota deleting the
> oldest recordings, a 128 GB quota on a 28.7 GB disk correctly *not* triggering, the free-space floor taking
> over when the quota is out of range, the floor being switched off with `min_free_gb = 0`, the time-lapse files
> being removed only after the recordings are gone, a switch to another target re-evaluating against the new
> filesystem, a disk that is full of foreign data **not** deleting the recordings (the history is preserved and
> recording is paused instead), and the deletion stopping when the space does not actually free up.

---

## [2.5.0] - 2026-11-11

The internationalization release: the web interface is bilingual and the language can be switched at any time
without restarting the service.

### Added

- `core/i18n.py` — the language-pack loader with `Accept-Language` negotiation. `LANGUAGES` registers `zh-CN` and
  `en-US`; `strings()` returns a pack with a per-key fallback, `translate()` translates a message produced by the
  back end, and `resolve()` decides which language a request uses.
- `GET /api/i18n` returns `{language, available, strings}`; `POST /api/i18n` switches the language and persists it.
- The `web.language` configuration key: `auto` (negotiated from the browser's `Accept-Language` header) or a
  concrete language code such as `zh-CN` / `en-US`.
- `core/locales/zh-CN.json` and `core/locales/en-US.json` with 385 strings each.
- Front end: `t()` and `applyI18n()` plus the `data-i18n` marker system (`data-i18n`, `data-i18n-title`,
  `data-i18n-placeholder`, `data-i18n-alt`) in `static/i18n.js`, and a language dropdown in the top bar that writes
  `web.language` back to `config.json` and then reloads the page.
- A migration toolchain for the Chinese source text: `tools/apply_i18n.py` (marks the templates, rewrites the JS
  string literals, generates the packs), `tools/i18n_table.py` (the source-text → key/translation table),
  `tools/jslex.py` (a JS lexer that correctly recognises regex literals, so a pattern such as `/'/g` is not
  mistaken for the start of a string), and `tools/htmltree.py` (an HTML structure parser that reports byte offsets,
  so the templates are touched no more than necessary).

### Changed

- `/api/help` now reads its content from the language pack instead of the built-in Chinese constant.
- The authentication and validation errors ("需要登录", "密码错误", "不支持的语言") are translated into the
  language of the current request.
- Back-end messages are written in the source language and translated through `i18n.translate()`, so one code path
  serves every language.

### Fixed

- Text nodes that contain only Chinese punctuation (for example "、") are now recognised by the migration tool, so
  no stray Chinese marks are left behind in the English interface.
- A key that is missing from a language pack is filled in from the fallback language, so an element can no longer
  render empty.
- A recording could freeze the entire service. When the encoder stopped consuming frames — the hardware H.264
  encoder was still initialising, or it had become unavailable — writing a frame blocked forever on the pipe. That
  write happens on the capture thread, so the whole service froze with it: the preview stopped, the API stopped
  answering, and the recording was left behind as a 0-byte file. Frame writes now run with a timeout
  (`record.frame_write_timeout`, default 8 s); a stuck encoder aborts the recording instead of the service, and a
  cooldown (`record.encoder_cooldown`, default 60 s) keeps the capture thread responsive afterwards.
- The hardware encoder never fell back even though the code promised it. `record.encoder=auto` selected
  `h264_v4l2m2m`, but if that encoder failed to start the recording was silently lost. `auto` now retries with the
  software encoder `libx264` and reports the fallback.
- ffmpeg's standard error went into a pipe that nobody read. Once that pipe buffer filled up, ffmpeg blocked
  itself. The error output now goes to `ffmpeg-err.log` next to the other temporary files.
- Recordings that were killed instead of closed had no `moov` atom and could not be played. The encoder is now
  closed by end-of-file — the only thing that makes ffmpeg write the `moov` — the systemd unit uses
  `KillMode=mixed` so the encoder is not killed before the service can finish it, and every start sweeps the media
  directory and removes the files that cannot be played.
- A recording file of 0 bytes is deleted instead of being left in the list, so the recordings view only ever shows
  entries that actually open.
- Pausing the recording left the running recording hanging: the encoder never received an end-of-file, so it
  stayed alive and kept holding the hardware encoder. Pausing now closes the event properly first.

> Quality assurance: every step of the migration was validated with a full API regression pass and a
> recording-integrity check — the complete HTTP surface was exercised before and after the switch, and the
> recorded events were verified to be complete (pre-roll, duration, recording file, full-frame thumbnail and
> motion-object crop), so the internationalization work changed no detection and no recording behaviour.

---

## [2.4.0] - 2026-11-10

### Added

- Rotation and mirroring for the preview and the recordings: `camera.rotation` and `camera.flip` are exposed in the
  web UI and really take effect now.

### Changed

- 0/180 degree rotation is done by the ISP at zero cost; 90/270 degrees automatically switch to the RGB888 path
  for a software rotation. The USB capture path does not support rotation yet and logs why.
- `POST /api/config` rebuilds the capture chain when `rotation`, `flip`, `format`, or `device` change, in addition to
  `resolution` and `fps`.

### Fixed

- The degradation / self-healing path crashed before it could heal: `Camera` had no log callback, so `self.log(...)`
  raised `AttributeError` on exactly the path that only runs when the camera fails. The camera now takes a log
  callback.
- `deploy.sh` could overwrite a release published in the same minute; it now appends `-r2` / `-r3` instead, so every
  published version is really kept.

---

## [2.3.2] - 2026-11-10

### Added

- The native kernel reports the release it was compiled from (`pkc_native_version()`).

### Changed

- `build_native.sh` passes the package version to the compiler, so a rebuilt kernel always belongs to the release
  that is running.

### Fixed

- The native kernel was rebuilt and re-verified against the pure Python implementation (identical detection
  results, same JPEG byte count).

---

## [2.3.1] - 2026-11-10

### Added

- Automatic degradation of the capture chain: when the frames stop arriving the pipeline is rebuilt — first
  lowering the resolution, then the frame rate, and finally falling back to RGB888.
- `camera.ae_constraint` — the AE metering mode (`normal` / `highlight` / `shadows` / `custom`) exposed as an
  optional safety knob.

### Changed

- The AE runs fully automatic and native again. libcamera has no "cap the exposure / gain" concept: assigning a
  scalar to `ExposureTime` / `AnalogueGain` locks the camera into manual exposure, so the service no longer tries to
  fake a cap.
- `AeConstraintMode` is now treated as what it actually is — a metering mode — and passed as the scalar control item
  it is.

### Changed

- The camera handles are released in a defined order when the capture chain is restarted or switched.

### Fixed

- After a camera switch the next start failed with `Pipeline handler in use by another process`, because the
  previous libcamera / ffmpeg handles were still held. They are now released cleanly.
- libcamera aborted the whole process (`signal=ABRT`, `Assertion '!isArray_' failed`) when a range tuple was passed
  to a scalar control such as `ExposureTime`. Only `FrameDurationLimits` really is an array.

---

## [2.3.0] - 2026-11-10

### Added

- The ISP hardware JPEG (MJPEG) passthrough path for CSI cameras: `rpicam-vid` lets the ISP encode the JPEG in
  hardware, so the per-frame software JPEG encoding cost drops to zero (`jpeg_ms=0`). `camera.format` selects
  `auto` / `MJPEG` / `RGB888`, and the web UI can switch the capture path without restarting the service.
- The frame-fetch watchdog: `camera.stall_timeout` and `camera.min_fps` decide when the capture chain counts as
  dead, so a stalled pipeline is rebuilt instead of freezing the preview.

### Changed

- The native acceleration kernel is warmed up when the service starts instead of on the first detection, so the
  first frames are not delayed by the compilation.
- The service falls back to the pure Python implementation automatically when the kernel is missing, fails to load,
  or is incompatible with the platform; the functionality is identical, only the speed differs.

### Fixed

- The detection result of the native kernel no longer differs from the pure Python implementation: the
  frame-difference ratio, the bounding box, and the consecutive-hit counter are bit-for-bit identical, and the
  JPEG output has the same byte count (PSNR > 138 dB).
- `rpicam-vid` looked like it had hung: its `--timeout` default is 5 seconds and means "the program runs for at most
  5 seconds", so the capture process quit on its own and printed
  `Halting: reached timeout of 5000 milliseconds.` The capture path now passes `-t 0`, which was measured at
  436 frames in 45 seconds — exactly 10.00 fps without a single interruption.

---

## [2.2.0] - 2026-11-09

### Added

- The native acceleration kernel: `core/_pkc_native.c` (libjpeg-turbo JPEG encoding + motion detection), compiled
  by `build_native.sh` into `core/_libpkc.so` and loaded through ctypes.
- Event hooks: `hooks.on_motion_begin`, `hooks.on_motion_end`, `hooks.on_motion_preview_save`, and
  `hooks.on_timelapse_end`, supporting the `{id} {video} {thumb} {time} {date} {duration} {algorithm} {region}
  {media_dir} {stills_dir} {videos_dir}` placeholders. They are read and written through `GET` / `POST /api/hooks`,
  and the recent executions are listed in the web UI.
- Hot reload of the scheduled commands: `~/.pikrellcam/at-commands.conf` and the `schedules` section of
  `config.json` are re-read while the service runs, and `POST /api/schedules/reload` forces a reload.

### Changed

- The web UI, the scheduler, and the FIFO now run their commands through the same dispatcher, so a command behaves
  identically no matter how it is triggered.

### Fixed

- A hook that fails is no longer invisible: its exit code, stdout, and stderr are recorded in the hook history and
  shown in the web UI.

---

## [2.1.5] - 2026-11-09

### Added

- The camera list is built once and shared by the preview tab and the system tab.

### Changed

- Both camera selectors show the same list and the same current value, and a switch made in one of them updates
  the other.

### Fixed

- Switching the camera on the preview tab no longer leaves the system tab showing a stale selection.

---

## [2.1.4] - 2026-11-09

### Added

- Nothing user-visible; this release only bumps the version number.

### Changed

- The version was bumped to 2.1.4 and the release was published again as an independent version directory.

### Fixed

- Nothing user-visible in this release.

---

## [2.1.3] - 2026-11-09

### Added

- The recorder counts the frames of an event.

### Changed

- The frame count of an event is reported by the recorder, so the duration of a recording can be cross-checked
  against the number of frames it actually contains.

### Fixed

- The event frame counter was never incremented and therefore always stayed at zero.

---

## [2.1.2] - 2026-11-09

### Added

- Deep links: a tab can be opened directly with `http://pi.local:8080/#system`, and the tab that is open is written
  into the URL.

### Changed

- The tab switch was refactored into a single `showTab()` function, so the click handler and the URL hash behave
  identically.

### Fixed

- Clicking something that is not a tab (for example a metric in the header) no longer throws; the click handler
  ignores such clicks.

---

## [2.1.1] - 2026-11-09

### Added

- `GET /api/release` returns the running version together with every historical version that is still kept on the
  host (`{version, release, current, releases, root}`).
- The camera selector is now also available on the preview tab, next to the capture-path selector.

### Changed

- The camera selector keeps the user's current choice when the camera list is refreshed, and only falls back to
  "auto" when there is no valid selection.

### Fixed

- Refreshing the camera list no longer resets the selection to "auto".

---

## [2.1.0] - 2026-11-09

### Added

- USB camera support: an ffmpeg + V4L2 backend next to the libcamera backend, `GET /api/cameras` to enumerate the
  cameras, `POST /api/cameras/select` to switch immediately, and the `camera.device` / `camera.format`
  configuration keys to persist the choice.
- Versioned publishing: `deploy.sh` uploads the current directory to
  `~/pikrellcam-lite/releases/<timestamp>-v<version>/`, points the `current` symlink at it, and keeps every
  historical version. `bash deploy.sh --list` lists them, `bash deploy.sh --rollback <version>` rolls back.
- Servo pan/tilt support: automatic backend detection (RPi.GPIO / lgpio / ServoBlaster), position presets, angle
  limits, and smooth movement. A position can be bound to a settings preset.

### Changed

- The configuration, the media, the logs, and the virtual environment moved into a shared root directory
  (`~/pikrellcam-lite/`), so upgrading or rolling back never touches the recordings or the settings.

### Fixed

- Switching the camera no longer requires a restart of the Raspberry Pi: the capture, detection, and recording
  chain is rebuilt in place.

---

## [2.0.0] - 2026-11-08

The first release.

### Added

- The CSI capture chain on libcamera / picamera2, with one JPEG encoding per frame that is shared by the web
  preview, the recording frames, and the thumbnail.
- Frame-difference motion detection with configurable regions, a per-pixel magnitude threshold, a
  fraction-of-changed-pixels threshold, a consecutive-frame counter, and neighborhood denoising.
- Event recording with pre-roll and post-roll, a full-frame thumbnail and a cropped moving-object thumbnail per
  event, and the event index in `media/events.json`.
- A browser-based management console for tuning the detection parameters, watching the live preview, reviewing
  the recordings, and reading the log.

### Changed

- The frame processing was rewritten to downsample before converting to grayscale: `np.dot(frame[..., :3],
  [0.299, 0.587, 0.114])` takes the batched matrix-multiply path in numpy and takes tens of seconds per frame at
  720p, which is enough to wedge the capture thread.
- The frame fetch uses a hard timeout (`Job.get_result(timeout=...)`), so a misbehaving sensor can no longer hang the
  capture thread forever.

### Fixed

- The detection no longer runs on the full-resolution frame, which made a single frame take tens of seconds and
  starved the capture thread.
