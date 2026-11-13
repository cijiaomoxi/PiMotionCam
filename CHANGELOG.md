# Changelog

All notable changes to pikrellcam-lite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versions

| Version | Date | Highlights |
| --- | --- | --- |
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
- `tools/test_v270.py` — 88 offline unit tests covering the parameter normalisation, the three backend mappings,
  the loop state machine (segment rotation, yielding to an event, resuming afterwards), the loop disk cap and the
  reclamation order. It runs on a Mac without numpy / Pillow (they are stubbed) and on the Pi with the real
  libraries.
- 78 new strings in each language pack (493 in total).

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
