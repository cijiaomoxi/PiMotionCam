# Changelog

All notable changes to pikrellcam-lite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versions

| Version | Date | Highlights |
| --- | --- | --- |
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
