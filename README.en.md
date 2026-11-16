# PiMotionCam v2.8.1

The rename retains `~/pikrellcam-lite` and `pikrellcam-lite.service` for existing configuration, media and upgrade compatibility.

[中文 / English project home](README.md) · [中文技术说明](README.zh-CN.md) · [English user guide](docs/USAGE.en.md)

A **motion-detection recording service** for Raspberry Pi OS (Debian 13 / trixie, 64-bit). Inspired by the feature
design of the official [PiKrellCam](https://github.com/billw2/pikrellcam), it implements recording on the
current **libcamera / picamera2** camera stack, and additionally supports **USB cameras**.

Access URL: **http://pi.local:8080/** — current version: **v2.8.1**

v2.8.1 retains v2.8.0 features, configuration and APIs while optimizing multi-region detection,
audio metering and media statistics. See [Performance and validation](docs/PERFORMANCE.md)
for the changes, measurement method and compatibility checks.

`CSI + USB cameras` `libcamera / picamera2` `Frame-differencing motion detection` `Native C kernel` `Event recording with pre/post-roll` `Graphical motion regions` `Dual far/near algorithms` `Timelapse` `Servo pan/tilt` `Scheduled commands` `Event hooks` `Bilingual UI` `Versioned releases with one-command rollback`

> [!NOTE]
> **This is an unofficial, independent implementation.** It is not affiliated with, nor endorsed by,
> the author of [PiKrellCam](https://github.com/billw2/pikrellcam) or by the Raspberry Pi Foundation.
> It matches PiKrellCam in features and interaction, but the code is written from scratch — see
> [Acknowledgements and References](#acknowledgements-and-references).

---

> 📋 **A feature-by-feature comparison with the upstream project** is in [`docs/上游功能对照.md`](docs/上游功能对照.md): which features are covered, which are partially covered, which are missing, and what PiMotionCam has that upstream does not.

## Acknowledgements and References

**PiMotionCam** (GitHub repository: `PiMotionCam`) is a multilingual re-implementation
built on the **feature design and user experience** of
**[PiKrellCam](https://github.com/billw2/pikrellcam)**. Our sincere thanks go to the original author
**Bill Wilson ([@billw2](https://github.com/billw2))** and to the PiKrellCam community.

| Reference project | Author | Link | Upstream license |
| --- | --- | --- | --- |
| PiKrellCam | Bill Wilson ([@billw2](https://github.com/billw2)) | <https://github.com/billw2/pikrellcam> | GPL-3.0 |

- **Feature parity**: it reproduces PiKrellCam's web features, configuration options, scheduled commands and
  operational workflow, and adds a **Simplified Chinese / English bilingual UI**, a **native acceleration
  kernel**, **USB camera support**, and **versioned one-command install/rollback**.
- **Different implementation**: PiKrellCam is built on the proprietary MMAL camera stack that Debian 13 removed;
  this project re-implements the capture and motion-detection pipeline on the official **libcamera / picamera2**
  stack. The stacks differ entirely: upstream is C + PHP, this project is Python / Flask.
- **Provenance**: this is an **independent implementation**. The repository **contains no PiKrellCam source
  code** and is **not a fork** of it; only the upstream feature design, interaction flow and documentation
  wording were referenced. This repository is released under the **MIT** license (see [LICENSE](LICENSE));
  upstream PiKrellCam is licensed under **GPL-3.0**.
- **Command names**: names such as `tl_start` / `on_motion_begin` are upstream functional command identifiers,
  cited **only to document configuration and command compatibility** — not to imply copied implementation.
- **Trademarks**: PiKrellCam, Raspberry Pi and Raspberry Pi OS are trademarks or registered trademarks of their
  respective owners and are used here for attribution only, implying no affiliation or endorsement.
- **Upstream link**: <https://github.com/billw2/pikrellcam>

> Contributions that correct or extend this attribution are welcome — please open an issue or a pull request.


## Feature Comparison

| Official PiKrellCam | This implementation |
| --- | --- |
| MJPEG web preview + OSD overlay | ✅ `/video_feed` multipart MJPEG stream + browser-side HTML OSD overlay (zero CPU cost) |
| MMAL motion vector detection | ✅ Frame differencing + neighborhood density denoising, equivalent to the official "sparkle" filter |
| Pre-roll / post-roll / event gap | ✅ `pre_seconds` / `post_seconds` / `event_gap_seconds` |
| Any number/size/position of motion regions | ✅ Normalized rectangles, drawn by dragging on the preview |
| Graphical live editing of regions | ✅ Drag to draw on the preview, right-click to select, then move/resize, double-click to rename |
| Region configurations saved/loaded by name | ✅ Named region presets |
| Two motion algorithms in parallel (far/near) | ✅ `far` (small, slow, distant targets) / `near` (large, close targets), each with its own sensitivity |
| Settings presets | ✅ Named configuration presets, one-click activation, can be bound to servo positions |
| Thumbnail = cropped motion target | ✅ Both a full-frame thumbnail and a cropped moving-object bounding box are produced |
| Motion begin/end/preview-save event commands | ✅ `on_motion_begin` / `on_motion_end` / `on_motion_preview_save` hooks |
| Command scheduling (time + frequency) | ✅ `at-commands.conf` + a web table, supporting weekday ranges and fixed intervals |
| FIFO command interface | ✅ `~/.pikrellcam/commands.fifo` |
| Recording pause | ✅ `POST /api/record {"action":"pause"}` |
| Timelapse + hold | ✅ `tl_start` / `tl_hold` / `tl_end`, with automatic MP4 assembly |
| Servo control (PWX GPIO / ServoBlaster) | ✅ RPi.GPIO / ServoBlaster auto-detection, position presets, pan/tilt limits, smooth movement |
| Password protection | ✅ Session login, switchable at any time |
| One-click upgrade | ✅ `git pull` + restart |
| USB camera | ✅ ffmpeg + V4L2 dual backend, switch between CSI / USB from the web UI at any time (v2.1.0+) |
| Multiple versions side by side with rollback | ✅ One independent directory per version under `releases/` plus a `current` symlink; every historical version is kept (v2.1.0+) |
| Native acceleration | ✅ Frame-processing C extension (loaded via ctypes), 4.71x end-to-end, half the CPU cost (v2.2.0+) |
| ISP hardware JPEG passthrough | ✅ CSI uses `rpicam-vid`, software JPEG encoding drops to zero (`jpeg_ms=0`), total CPU down another 11% (v2.3.0+) |
| Switchable capture path | ✅ Switch between ISP hardware JPEG and raw RGB from the web UI at any time, no service restart (v2.3.0+) |
| Picture rotation / mirroring | ✅ 0/180 is done by the ISP at zero cost, 90/270 automatically switches to software rotation over RGB888 (v2.4.0+) |
| Stall self-healing | ✅ Frame-fetch watchdog + automatic degradation (resolution → frame rate → fall back to RGB888); a dead pipeline is rebuilt automatically (v2.3.0+) |
| Loop recording | ✅ Continuous recording split into fixed-length segments, oldest segments deleted when the disk cap is exceeded; yields to the event recorder on motion (v2.7.0+) |
| Imaging parameter matrix | ✅ Brightness / contrast / saturation / sharpness / denoise / exposure / metering / EV / ISO / shutter / white balance / digital zoom, applied per capture path (v2.7.0+) |
| Recordings with sound | ✅ Microphone captured continuously into a ring buffer, sliced out after the recording and muxed in; the pre-roll of an event clip carries the matching audio (v2.8.0+) |
| Recording countdown | ✅ While an event recording runs, the picture shows how many seconds are left; with only the loop recorder running it shows the time left in the current segment (v2.8.0+) |
| Video / snapshot / timelapse / archive pages | ✅ Media tab + remote archiving (scp) |
| System log page | ✅ Continuously scrolling log |
| Help page | ✅ Built-in documentation |
| Audio stream | ❌ Not implemented (live audio in the browser), see "Known Limitations" |
| Hardware motion vectors | ❌ Not available in the new stack; replaced by frame differencing |

---

## Performance Design (Targeting Raspberry Pi 3B and Newer)

This was the focus of the rewrite: the measured bottleneck is not the language but the **repeated work per frame**.

| Optimization | Description |
| --- | --- |
| **Native acceleration kernel (C extension)** | Since v2.2.0 the three most expensive stages of frame processing are compiled from `core/_pkc_native.c` into a `.so` and loaded via ctypes, see [Native Acceleration](#native-acceleration-v220) |
| **Encode once, reuse everywhere** | Each frame is JPEG-encoded once and the result is shared by the web preview, the recording frames, and the thumbnail; the old version decoded and re-encoded every frame |
| **Downsample before grayscaling** | Detection computes grayscale only on 320×180 target pixels. **Never** write `np.dot(frame[..., :3], [0.299,0.587,0.114])` — numpy takes the batched matrix-multiply path for a 3-D array against a 1-D vector, which takes tens of seconds per frame at 720p and is enough to wedge the capture thread |
| **Browser-side OSD** | Timestamp, status, FPS, and region boxes are overlaid in HTML and never burned into the image |
| **Streaming preview** | A long-lived multipart MJPEG connection replaces the old polling of a full JPEG every 200ms |
| **Record while encoding** | ffmpeg receives frames over `image2pipe` and encodes on the fly: no intermediate files, no second read from disk |
| **Downgrade by model** | Pi 3/3B/Zero automatically switch to 640×480 @ 8fps, Pi 4/5 use 1280×720 @ 10fps |
| **Hard timeout on frame fetch** | `Job.get_result(timeout=8)`; a misbehaving sensor can no longer hang the thread forever |
| **Hardware H.264 encoding** | Pi 4/5 prefer `h264_v4l2m2m` and fall back to `libx264` automatically |

---

## Native Acceleration (v2.2.0+)

The three most expensive stages of the frame-processing chain are moved out of Python/numpy into C, compiled into
`core/_libpkc.so`, and loaded through ctypes.

### Measured Data (Raspberry Pi 4, 1280×720, detection resolution 320×180)

| Stage | Pure Python | Native C | Speedup |
| --- | --- | --- | --- |
| Grayscale downsampling | 35.77 ms | **0.85 ms** | 42.1x |
| Dual-algorithm motion detection | 22.76 ms | **2.26 ms** | 10.1x |
| JPEG encoding | 18.62 ms | **13.29 ms** | 1.4x |
| **Full chain, single frame** | **77.16 ms** | **16.40 ms** | **4.71x** |

Server-side end to end (A/B on the same machine):

| Backend | Single-core CPU usage | `jpeg_ms` |
| --- | --- | --- |
| Pure Python | 42.3% | 17.3 ms |
| Native C | **20.7%** | **12.7 ms** |

**This is exactly the key to running smoothly on a Raspberry Pi 3B**: a 3B's single-core performance is roughly 1/2.5
to 1/3 of a Pi 4, so the pure Python backend alone would saturate a single core on a 3B for frame processing
(42.3% × ~2.7 ≈ 114%). With the native kernel the same workload comes to roughly 55%, which leaves plenty of
headroom at 10fps.

### Frame Rate Headroom

The native kernel brings a single frame down to 16.4ms (a theoretical ceiling of 61fps), while the CSI sensor
itself supports up to 30fps (the lower bound of `FrameDurationLimits` is 33333µs):

| Configured fps | Actual fps | `jpeg_ms` | Single-core CPU |
| --- | --- | --- | --- |
| 10 | 10.0 | 12.5 ms | 20.7% |
| 15 | 15.0 | 12.5 ms | 29.5% |
| 20 | 20.0 | 13.1 ms | 38.6% |
| 30 | 30.0 | 12.4 ms | 57.5% |

`jpeg_ms` does not vary with the frame rate, which shows that capture is the bottleneck and encoding has spare
capacity. **Keep 10fps on a Raspberry Pi 3B** (the default); Pi 4/5 can be raised to 20–30fps.

### Automatic Build and Fallback

- `build_native.sh` does the compiling; `deploy.sh` runs it after a release and `install.sh` runs it during installation.
- `gcc` and `libjpeg62-turbo-dev` are required (the script installs the latter automatically when it is missing).
- **A failed build does not break the service**: it falls back automatically to the pure Python + numpy implementation, with identical functionality and only lower speed.
- To turn acceleration off temporarily for comparison or troubleshooting, set the environment variable `PKC_NO_NATIVE=1`.
- The active backend can be confirmed on the "System" tab of the web UI or in the log (`native acceleration enabled`).

### Consistency Guarantee

The C kernel was compared bit for bit against the original Python implementation: the frame-difference ratio, the
bounding box, and the consecutive-hit counter are **identical**; the JPEG output has the same byte count and a
PSNR > 138 dB (visually identical). The grayscale images differ by ±1 on 26 of 57600 pixels (the truncation boundary
between float32 and double), which does not affect the detection decision.

### The CSI MJPEG Capture Path (since v2.3.0)

Earlier versions concluded that "CSI cannot use MJPEG" — which is only half true:
`create_video_configuration(main={"format": "MJPEG"})` is indeed rejected by libcamera
(`RuntimeError: Bad format JPEG in stream main`), but **switching to `rpicam-vid` lets the ISP encode JPEG in
hardware**. Measured comparison of the two paths (Pi 4 + ov5647 + 1280×720@10, v2.4.0):

| Path | Total capture-chain CPU | `jpeg_ms` | Pipeline rebuilds |
| --- | --- | --- | --- |
| **MJPEG** (`rpicam-vid` + ISP hardware encoding) | **≈ 29.9%** | **0.00** | 0 |
| RGB888 (picamera2 + C kernel software encoding) | ≈ 33.7% | 20.37 | 0 |

`camera.format=auto` therefore prefers MJPEG for CSI today, and the web UI can switch paths at any time (a "capture
path" selector sits next to the camera dropdown).

> ⚠️ **Pitfall: `rpicam-vid` must be given `-t 0` explicitly.** Its `--timeout` default is **5 seconds**, and the
> meaning is "the program runs for at most 5 seconds", not "wait 5 seconds for a frame". Without this flag the
> capture process quits on its own after 5 seconds and prints
> `Halting: reached timeout of 5000 milliseconds.`, which looks exactly like "the camera pipeline is frozen" — the
> symptom is identical to the service rebuilding the pipeline every 16 seconds, so it is very easy to misdiagnose.
> With `-t 0` the measurement is 436 frames in 45 seconds, exactly 10.00fps, uninterrupted. **USB cameras do not go
> through libcamera**; they are read directly over ffmpeg + V4L2, and a device that natively supports MJPEG is
> passed through with `-c:v copy`, zero transcoding.

### The Two AE (Auto-Exposure) Pitfalls

The libcamera controls are split into "scalars" and "arrays", and **the wrong type aborts the whole process**
(`signal=ABRT`):

| Control | Type | Range |
| --- | --- | --- |
| `ExposureTime` | scalar int | 1..66666 µs |
| `AnalogueGain` | scalar float | 1.0..16.0 |
| `AeConstraintMode` | scalar int | 0..3 |
| `FrameDurationLimits` | **array** | ← it is the only array |

- Passing a tuple to a scalar control turns the value into an array, and libcamera's internal read hits
  `Assertion '!isArray_' failed` and aborts the process on the spot.
- libcamera has **no "cap the exposure / gain" semantics**: assigning a scalar to `ExposureTime` / `AnalogueGain`
  **locks the camera into manual exposure**, auto exposure stops working from then on, and the picture becomes
  noticeably darker in low light.
- `AeConstraintMode` is the **metering mode** (0=Normal 1=Highlight 2=Shadows 3=Custom). Setting it to 1 (Highlight)
  by mistake makes the AE meter for highlights, and the picture darkens noticeably in the same way.

This implementation therefore keeps AE **fully automatic and native**, and exposes only `AeConstraintMode` as an
optional safety knob (`camera.ae_constraint`, default `normal`); real protection against stalls comes from the
capture watchdog + automatic degradation.

---

## USB Camera Support

Since v2.1.0 the program supports **CSI (the official Raspberry Pi ribbon camera)** and **USB cameras** at the same
time, and you can switch between them from the "System → Camera" dropdown in the web UI without rebooting the Pi.

### Why USB Must Bypass libcamera

The libcamera stack in Debian 13 ships only the Raspberry Pi's own processor and **does not include `u8vidcam` (the
V4L2 UVC processor)**, so libcamera (and therefore `rpicam-vid`) **cannot enumerate USB cameras at all**. This
project implements a dual backend for that reason:

| Backend | Suitable devices | Capture method |
|---|---|---|
| `rpicam` | CSI ribbon camera (default) | rpicam-vid, ISP hardware JPEG encoding, JPEG bytes passed straight through |
| `libcamera` | CSI ribbon camera (fallback) | picamera2, RGB888 main stream + C kernel software JPEG |
| `v4l2` | USB / UVC camera | ffmpeg reading `/dev/videoN` directly, MJPEG passthrough when available |

### Automatic Detection and Switching

- `GET /api/cameras` returns every enumerated camera (CSI + USB).
- `POST /api/cameras/select` with body `{"device": "/dev/video0"}` switches immediately; `"auto"` hands control
  back to automatic selection, `"0"`/`"1"` mean a libcamera index.
- The configuration key `camera.device` (`auto` / libcamera index / `/dev/videoN`) is persisted to `config.json`.
- After a switch the capture, detection, and recording chain is rebuilt as a whole; no service restart is needed.

### Performance Advice for USB Cameras

- **Prefer MJPEG passthrough**: almost every UVC camera outputs MJPEG natively, and this program probes
  `v4l2-ctl --list-formats-ext` automatically; on a hit it uses `-c:v copy`, with zero transcoding.
- If the device only supports YUYV, ffmpeg transcodes to MJPEG, which costs more CPU than passthrough; lower
  `camera.fps` in that case.
- Capture resolution and frame rate use the maximum the device supports. The detection resolution and detection
  frame rate can be set separately under "Detection Tuning" (detection resolution is independent of the preview
  resolution; 320×240 is a good choice on a Pi 3B).

### Manually Confirming a Device

```bash
# List every video device and the formats it supports
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext

# Try reading for 2 seconds
ffmpeg -f v4l2 -input_format mjpeg -video_size 1280x720 -framerate 10 \
  -i /dev/video0 -t 2 -f image2pipe -c:v copy - | wc -c
```

> **Note**: on Debian 13 the format of a `v4l2loopback` virtual device is decided by the **writing** end. To make
> the virtual device expose MJPEG, push MJPEG on the writing side:
> `ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=10 -f v4l2 -vcodec mjpeg -q:v 5 /dev/video1`

---

## Multiple Languages / 多语言 (since v2.5.0)

The interface supports **Simplified Chinese** and **English**, and the front end and the back end **share the very
same language pack**: `core/locales/<language-code>.json`, a flat `{"key": "text"}` dictionary.

- The **language dropdown sits in the top-right corner of the top bar**. Picking a language writes it back to
  `web.language` in `config.json` and then reloads the whole page.
- `web.language` is either `auto` (negotiated from the browser's `Accept-Language` header, falling back to
  Simplified Chinese when nothing matches) or a concrete language code such as `zh-CN` / `en-US`.
- The messages the back end produces itself (authentication failures, an unsupported language, …) go through the
  same pack, so it is not only the interface that is translated.
- `GET /api/i18n` returns `{language, available, strings}` — the current language, the list of available
  languages, and the string dictionary; `POST /api/i18n` switches the language.

```bash
# Read the current language, all available languages, and the string dictionary
curl -s http://pi.local:8080/api/i18n

# Switch to English (persisted to config.json)
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"language":"en-US"}' http://pi.local:8080/api/i18n

# Back to automatic selection
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"language":"auto"}' http://pi.local:8080/api/i18n
```

### Adding a New Language

Two steps are enough, and **the front end needs no change at all**:

1. Copy `core/locales/zh-CN.json` to a new language code (for example `ja-JP.json`) and translate the strings;
2. Register it in the `LANGUAGES` dictionary in `core/i18n.py`:

```python
LANGUAGES = {
    "zh-CN": {"name": "Chinese (Simplified)", "native": "简体中文"},
    "en-US": {"name": "English", "native": "English"},
    "ja-JP": {"name": "Japanese", "native": "日本語"},   # ← new
}
```

The new language appears in the top-bar dropdown automatically. A key that is missing from a pack falls back to
Simplified Chinese, so the interface never goes blank.

> The string catalogue is extracted from the source code by `tools/apply_i18n.py` (`tools/i18n_table.py` is the
> Chinese/English table). After changing the front-end wording, run `python3 tools/apply_i18n.py` once to resync the
> packs; the script reports the strings it could not find and the table entries it never used, so no translation
> goes missing unnoticed.

---

## External Storage (since v2.6.0)

Recordings, snapshots and timelapse videos can be written to a **USB drive, a portable hard disk or an external
SD card** instead of the Raspberry Pi's own SD card. Pick a device in the **Storage location** panel on the Media
tab and click **Apply storage settings** — **no restart needed**.

### Why this needs careful handling

After a USB drive is pulled out, **the mount point directory stays behind on the SD card** (it is simply an empty
directory now). If the program only asks "does this path exist?", it concludes that everything is fine and keeps
writing the recordings into the SD card. Over time that fills up the system partition and **bricks the Raspberry
Pi — it will no longer boot**.

This project therefore does the following:

1. The target must be a **real mount point** (findable in `/proc/mounts`), not an ordinary directory;
2. It must not point at the **root filesystem**;
3. Writability is **proven** — an actual temporary file is created instead of trusting the permission bits;
4. The target is re-validated **before every single recording**, and a background thread re-checks it every three
   seconds.

### What happens when the drive is pulled out

The default behaviour is to **pause recording and show a warning** (the top bar turns red) rather than quietly
writing back to the SD card:

- `media.require_mount` (default `true`): the target has to be a mount point;
- `media.fallback_internal` (default `false`): whether to fall back to the internal storage when the device
  disappears. Set it to `true` to keep recording on the SD card while the drive is away; the interface then shows
  that it has fallen back.

The event index (`events.json`) **always lives in the internal storage**, so pulling the USB drive out never loses
the event list.

### From the command line

```bash
# List the detected storage devices and the current state
curl -s http://pi.local:8080/api/storage

# Switch to the USB drive (the directory must be a real mount point right now,
# otherwise the API answers 400 and explains why)
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"dir":"/media/pi/USB","require_mount":true,"fallback_internal":false}' \
     http://pi.local:8080/api/storage

# Switch back to the internal storage
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"dir":""}' http://pi.local:8080/api/storage
```

> Tip: right after plugging the drive in, the system may not have mounted it yet. Run `lsblk -f` to look at the
> partitions, and if needed mount it by hand with
> `sudo mkdir -p /media/pi/USB && sudo mount /dev/sda1 /media/pi/USB`.

---

## Disk monitoring (v2.6.0+)

The "Disk" indicator in the top bar shows the **real free space of the target filesystem**
(e.g. `free 20.9 GB`) and turns red when it drops below the floor. The detection tab shows the media usage,
the quota and the free space side by side under the recording parameters.

### The disk limit and the free-space floor are not the same thing

| Setting | Meaning | Default |
| --- | --- | --- |
| `record.max_disk_gb` | **Media quota**: the limit for recordings + snapshots + time-lapse in GB (1–128). The oldest recordings are deleted once it is exceeded. | `8` |
| `record.min_free_gb` | **Free-space floor**: below this much free space on the target filesystem the old media is removed; if that is not enough, recording is paused. `0` switches the guard off. | `1` |

**Why the second one is needed**: the quota may be set larger than the whole disk — `max_disk_gb = 128` on a
28.7 GB SD card is perfectly valid, but then the quota **never triggers** and recording simply continues until
the filesystem is 100 % full. An ext4 root partition at 100 % means no log can be written, no configuration can
be saved, and the device may no longer boot. What actually protects you is "how much space is left", not
"how much media has piled up".

### Cleaning up never destroys your history

- The **oldest recordings** go first (together with their snapshots); only when the recordings are gone and the
  gap is still open do the **time-lapse** files go (they can be regenerated);
- **if deleting all the media still would not close the gap**, the disk is full of something else
  (system logs, another application, another partition). In that case **not a single recording is deleted** —
  recording is paused and the alarm goes off instead, because keeping the history matters more than keeping a
  recording count;
- Every automatic cleanup is written to the service log (`disk guard: removed N old media file(s)`), so it never
  happens silently.

### Switching the target re-checks the free space

After switching to an external drive, the free space is **recomputed for the new target**: the API returns the
fresh result immediately, the background thread re-checks every three seconds, and every candidate device is
listed with its own usable / total figures.

---

## Loop recording (since v2.7.0)

The Media tab has a "Loop recording" panel. Once enabled the camera records continuously and splits the footage
into fixed-length segments under `media/loop/`.

| Key | Default | Meaning |
| --- | --- | --- |
| `loop.enabled` | `false` | Whether loop recording is on |
| `loop.segment_seconds` | `60` | Length of one segment |
| `loop.max_disk_percent` | `30` | Percentage of the **whole filesystem** the loop footage may occupy; the oldest segments are deleted when it is exceeded |
| `loop.quality` | `26` | CRF of the loop recording (slightly cheaper than the event clips) |

The cap is a percentage of the **filesystem capacity**, matching the upstream `loop_diskusage_percent`, so the
number stays meaningful after switching to a USB drive.

Pausing the recorder (the "pause recording" switch in the web interface, or the internal command `record off`)
also pauses loop recording — the same semantics as the upstream `pause` flag. The panel says "Recording paused"
instead of looking like the switch did nothing, and it shows the **frame rate that is really used**: some USB
cameras ignore the requested frame rate (10 fps configured, 30 fps delivered), the capture path throttles to the
configured rate and the encoder timestamps the frames with the measured rate, so a "60 second" segment really is
about 60 seconds long.

### Loop recording and event recording cannot run at the same time

The Pi's H.264 hardware encoder lives on `/dev/video31` and **only one ffmpeg instance can use it at a time**;
the capture thread feeds a single encoder as well. The two recorders are therefore mutually exclusive by
construction, and the implementation uses the same state machine as upstream
(`VCB_STATE_LOOP_RECORD` / `VCB_STATE_MOTION_RECORD`):

```
idle         → the loop recorder writes
motion seen  → the current loop segment is closed, the event clip takes the hardware encoder
event over   → the loop recording resumes on the next frame
```

So with loop recording and motion detection both on, the few seconds around an event belong to the **event
clip**, not to a loop segment. That is a hardware constraint, not a trade-off.

### Which footage is reclaimed first

The two disk guards from v2.6.0 (media quota, free-space floor) now reclaim loop segments too. The order is
**loop segments → event recordings → timelapse**: a loop segment is the least valuable of the three (it is
continuous coverage by definition and the oldest ones are meant to be overwritten), while an event clip carries a
specific moment that triggered the recording.

---

## Imaging parameter matrix (since v2.7.0)

The Detection tab has an "Imaging" panel with 14 parameters:

| Key | Range | Normal | Meaning |
| --- | --- | --- | --- |
| `brightness` | 0–100 | 50 | Overall brightness |
| `contrast` | -100–100 | 0 | Contrast strength |
| `saturation` | -100–100 | 0 | -100 gives a pure greyscale picture |
| `sharpness` | -100–100 | 0 | Edge sharpening |
| `denoise` | auto / off / cdn_fast / cdn_hq | auto | Noise reduction, useful in low light |
| `exposure` | normal / sport | normal | Sport shortens the exposure |
| `metering` | centre / spot / average / custom | centre | Which part of the frame auto exposure meters |
| `ev` | -10–10 | 0 | Exposure compensation in stops |
| `iso` | 0–3200 | 0 (auto) | Fixed analogue gain |
| `shutter` | 0–500000 µs | 0 (auto) | Fixed shutter time |
| `awb` | auto / daylight / cloudy / … | auto | White balance preset |
| `awb_r_gain` / `awb_b_gain` | 0–3 | 0 (auto) | Manual white balance gains |
| `zoom` | 100–300 % | 100 | Digital zoom (centre crop, costs resolution) |

The ranges deliberately match the semantics of the upstream MMAL build so that upstream configurations can be
migrated over.

### Three capture paths, three ways to apply them

| Path | How the parameters are applied | Restart needed? |
| --- | --- | --- |
| CSI + rpicam-vid (ISP hardware JPEG) | Translated into command-line flags | **Yes**, these are startup flags |
| CSI + picamera2 / libcamera (raw RGB) | `set_controls()` | No, applied live |
| USB cameras | `v4l2-ctl --set-ctrl` | No, applied live |

What a USB camera actually supports has to be **probed**: the controls and their ranges are read with
`--list-ctrls` first, each value is scaled into the control's own range, and controls the camera does not
implement are skipped and reported as unsupported (greyed out in the UI).

### The controls are generated

The controls are **not hard-coded in the HTML** — they are generated from the parameter schema returned by
`/api/imaging`. Adding a parameter only means editing `SPECS` in `core/imaging.py`; neither the template nor the
JavaScript has to change.

```bash
# read the current parameters and the active path
curl -s http://<pi>:8080/api/imaging | python3 -m json.tool

# change parameters (they are stored and applied automatically)
curl -s -X POST http://<pi>:8080/api/imaging \
  -H 'Content-Type: application/json' \
  -d '{"values":{"brightness":60,"contrast":10,"awb":"daylight"}}'
```

---

## Audio (since v2.8.0)

The Media tab has an "音频 / Audio" panel. Once it is enabled, loop segments and event recordings both carry an
**audio track**, and the sound stays in sync with the picture.

| Parameter | Meaning | Default |
| --- | --- | --- |
| `record.audio_enabled` | Enable microphone capture | `false` |
| `record.audio_device` | Capture device: `auto` / `hw:N,M` / `plughw:N,M` | `auto` |
| `record.audio_rate` | Sample rate (Hz) | `16000` |
| `record.audio_channels` | Channel count | `1` |
| `record.audio_bitrate` | AAC bitrate (kbps) | `64` |
| `record.audio_buffer_seconds` | Length of the in-memory ring buffer (seconds) | `180` |

It is **off** by default: a machine without a microphone should not report an error all day.

### How the audio gets into the recording

The microphone does **not** go straight into the encoder. A resident `arecord` process reads raw PCM into an
in-memory **ring buffer**; once the recording has finished, the slice belonging to its wall-clock time window is
cut out of that buffer and muxed into the MP4 with ffmpeg:

```
resident arecord ──► PCM ring buffer (180 seconds by default)
                          │
recording closed (moov written) ──┴──► slice the window ──► ffmpeg -c:v copy -c:a aac ──► clip with audio
```

Why not feed ALSA into the encoder directly? Because an event recording starts with a **pre-roll**
(`record.pre_seconds`, 5 seconds by default): the picture at the beginning is from five seconds ago, so the
sound at that moment has to be from five seconds ago as well. The audio track of an event recording therefore
starts at the moment of the **earliest frame in the pre-roll buffer**, and the track of a loop segment starts
when the segment started.

The end of the window is computed from the **video's own timeline** (frame count ÷ the frame rate the encoder
actually used), not from the wall clock at close time — the latter makes the track nearly a second longer than
the picture.

Parts of the window that the ring buffer does not cover are **padded with silence** instead of shifting the
track. A silent beginning is better than a drifting soundtrack.

The video is **not re-encoded** (`-c:v copy`); only the audio track is added. AAC is used rather than the
upstream's MP3 because MP4 supports AAC natively: no second container pass, and browsers and phones play the
result directly.

### Using a different microphone

The device drop-down lists **every** ALSA capture device on the machine (the output of `arecord -l`), so
"not the microphone built into the camera, but an external USB one" simply means: plug it in, pick it in the
drop-down, save.

The default `auto` prefers **the microphone on the same USB port as the camera** — the microphone of a USB
camera sits on that very port. Only when there is none does it fall back to any USB device.

### Command line

```bash
# list all capture devices
arecord -l

# current audio state (device, level, sample rate)
curl -s http://<pi>:8080/api/audio | python3 -m json.tool

# enable audio with a specific device
curl -s -X POST http://<pi>:8080/api/audio \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"device":"plughw:3,0"}'

# internal command
curl -s -X POST http://<pi>:8080/api/command \
  -H 'Content-Type: application/json' -d '{"command":"audio status"}'
```

### Limitations

- The ring buffer is only `audio_buffer_seconds` long (180 seconds by default). The **pre-roll cannot reach
  further back than that**; anything older is padded with silence.
- An ALSA capture device is **exclusive**: if another program holds it (a player, a voice assistant), the capture
  fails.
- The native format of a device is not necessarily 16 kHz mono. Use `plughw:` rather than `hw:` and the plugin
  handles the conversion.
- The **audio stream** (live audio in the browser) and **audio-triggered recording** (record when the sound
  crosses a threshold) are not implemented — they are separate subsystems.

---

## Deployment

### Method 1: Versioned Publishing (recommended)

Every version is kept independently and **is never overwritten**:

```bash
cd PiMotionCam
bash deploy.sh                  # publish the current working directory → releases/<timestamp>-v<version>/
bash deploy.sh --list           # list every retained version + the running one
bash deploy.sh --rollback v2.4.0   # roll back to a historical version
```

`deploy.sh` uploads over ssh with tar into `~/pikrellcam-lite/releases/<timestamp>-v<version>/`, then points the
`current` symlink at the new directory and restarts the service. Historical versions stay untouched under `releases/`
and can be rolled back at any time.

### Method 2: First-Time Install

```bash
# 1. Copy to the Raspberry Pi
scp -r -i ~/.ssh/id_ed25519_pi_mcode PiMotionCam pi@pi.local:~/

# 2. Install on the Raspberry Pi
ssh -i ~/.ssh/id_ed25519_pi_mcode pi@pi.local 'bash ~/PiMotionCam/install.sh'

# 3. Open the browser
open http://pi.local:8080/
```

`install.sh` installs the missing system packages (`python3-picamera2` / `python3-numpy` / `python3-pil` / `ffmpeg` /
`python3-venv`), creates a `venv` with `--system-site-packages` (reusing the system picamera2 and numpy), runs
`pip install flask`, writes `~/.config/systemd/user/pikrellcam-lite.service` (with `ExecStart` pointing at the
`current` symlink), runs `systemctl --user enable --now`, and enables `loginctl enable-linger`. Boot-time autostart
has been verified: after a reboot the service comes up on its own and holds the camera.

### Directory Layout and Version Management

```text
~/pikrellcam-lite/
├── current -> releases/20261110-2328-v2.4.0   # symlink to the running version
├── releases/                                     # all historical versions, each complete and independent
│   ├── 20261110-2327-v2.4.0/
│   └── 20261110-2328-v2.4.0/
├── media/     # recordings / snapshots / event index (shared by all versions, never lost on upgrade)
├── logs/      # runtime logs (shared by all versions)
├── venv/      # Python virtual environment (shared by all versions)
└── config.json# configuration (shared by all versions)
```

**The boundary between version directories and shared data**: the code, templates, and front-end assets live inside
the version directory, while `media/`, `logs/`, `venv/`, and `config.json` live in the shared root, so neither an
upgrade nor a rollback affects your recordings or your settings. **Rolling back** only means pointing the symlink
elsewhere and restarting:

```bash
ln -sfn releases/20261110-2327-v2.4.0 ~/pikrellcam-lite/current
systemctl --user restart pikrellcam-lite.service
```

The script can do it in one step as well (`--rollback` matches the newest directory with that version number):

```bash
bash deploy.sh --rollback v2.4.0
```

Rollback has been tested: after switching to v2.0.0 the service came up normally and the camera produced frames as
usual (the `release` field disappears from `/api/state`, which is exactly what an older version without that field
looks like), and switching back to a newer version worked just as well.

---

## Common Operations

```bash
ssh pi@pi.local

systemctl --user status  pikrellcam-lite.service   # check the status
systemctl --user restart pikrellcam-lite.service   # restart
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f   # live log
tail -f ~/pikrellcam-lite/logs/pikrellcam.log      # file log (rotated automatically)

# Change the port
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home()/"pikrellcam-lite/config.json"
c = json.loads(p.read_text()); c["web"]["port"] = 8090
p.write_text(json.dumps(c, indent=2))
EOF
systemctl --user restart pikrellcam-lite.service
```

> `journalctl --user` is not available on this machine; use `journalctl _SYSTEMD_USER_UNIT=<unit name>` instead.

### Forgotten Password

The password is stored as `web.password_hash` in `config.json`. Set it to an empty string and restart the service to
disable password protection:

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

## Parameter Reference

`config.json`:

### camera

| Key | Default | Meaning |
| --- | --- | --- |
| `resolution` | `[1280,720]` | Capture resolution (a change requires a service restart) |
| `fps` | `10` | Capture frame rate |
| `jpeg_quality` | `72` | JPEG quality of preview and recording frames |
| `detect_resolution` | `[320,180]` | Downsampled size used for detection |
| `detect_fps` | `10` | Detection frame rate |
| `buffer_count` | `6` | Number of libcamera buffer frames |
| `device` | `auto` | Camera: `auto` / libcamera index (such as `0`) / USB device (such as `/dev/video0`) |
| `format` | `auto` | Capture path: `auto` (CSI→ISP hardware MJPEG) / `MJPEG` / `RGB888`; the USB backend auto-detects MJPEG passthrough |
| `rotation` | `0` | Rotation 0/90/180/270 (on the MJPEG path 0/180 is free from the ISP, 90/270 automatically switches to software rotation over RGB888) |
| `flip` | `none` | Flip: `none` / `horizontal` / `vertical` / `both` |
| `ae_constraint` | `normal` | AE metering mode: `normal` / `highlight` / `shadows` / `custom` |
| `stall_timeout` | `8.0` | Frame-fetch watchdog: if no new frame arrives within this many seconds, the capture pipeline is rebuilt |
| `min_fps` | `0.5` | Frame rate floor: if the rate stays below this for `stall_timeout` seconds, the pipeline is likewise considered dead |
| `imaging.*` | see above | The imaging parameter matrix (14 parameters); ranges and semantics are listed in the "Imaging parameter matrix" section |

### motion

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Whether detection is on (switchable live from the web UI) |
| `algorithms.far.magnitude_limit` | `12` | Per-pixel grayscale difference threshold of the far algorithm; larger means less sensitive |
| `algorithms.far.count_limit` | `0.006` | Threshold for the fraction of changed pixels inside a region (far algorithm) |
| `algorithms.far.consecutive_frames` | `2` | Consecutive matching frames required by the far algorithm |
| `algorithms.far.noise_filter` | `2` | Neighborhood denoising radius of the far algorithm (`0` disables it) |
| `algorithms.near.*` | `28 / 0.02 / 2 / 3` | The same for the near algorithm, aimed at large close-up targets |
| `regions` | whole frame | Array of motion regions, each `{name,x,y,w,h,enabled}`, with coordinates normalized to 0~1 |
| `region_presets` | `{}` | Named region presets |

### record / timelapse / web / media / servo / hooks

| Key | Default | Meaning |
| --- | --- | --- |
| `record.pre_seconds` | `5` | Seconds of pre-roll before the trigger |
| `record.post_seconds` | `8` | Seconds of post-roll after the trigger |
| `record.event_gap_seconds` | `10` | Minimum interval between two events |
| `record.max_event_seconds` | `120` | Maximum length of a single event, so continuous motion cannot grow memory without bound |
| `record.max_disk_gb` | `8` | Size limit of the recording directory (media quota in GB, 1–128); the oldest files are deleted when it is exceeded |
| `record.min_free_gb` | `1` | Free-space floor of the target filesystem in GB; below it the old media is removed, and recording is paused if that is not enough. `0` disables it |
| `record.encoder` | `auto` | `auto` / `h264_v4l2m2m` / `libx264` (`auto` prefers the hardware encoder and falls back to the software encoder) |
| `record.frame_write_timeout` | `8` | Longest wait, in seconds, for one frame to reach the encoder; on timeout the encoder is treated as stuck and the recording is abandoned instead of the service |
| `record.encoder_close_timeout` | `15` | Longest wait, in seconds, for ffmpeg to finish writing the `moov` atom when a recording ends |
| `record.encoder_cooldown` | `60` | Seconds to stop trying to record after the encoder got stuck |
| `timelapse.period` | `30` | Timelapse capture interval (seconds) |
| `web.port` | `8080` | Listen port |
| `web.password_hash` | `""` | `sha256:<hex>`; an empty value disables password protection |
| `web.language` | `auto` | Interface language: `auto` (negotiated from the browser's `Accept-Language`) / `zh-CN` / `en-US` |
| `media.dir` | `""` | Media directory; empty means `media/` under the application root, and it can point at an external mount such as `/mnt/usb` |
| `media.require_mount` | `true` | Whether an external target must be a real mount point (prevents a pulled-out USB drive from filling up the SD card) |
| `media.fallback_internal` | `false` | Whether to fall back to the internal storage when the external storage is unavailable; `false` pauses recording and warns instead |
| `media.archive_target` | `""` | Remote archive target, in the form `user@host:/path` |
| `servo.pan_pin` / `tilt_pin` | `18` / `17` | BCM pin numbers |
| `servo.positions` | 3 presets | `[{name,pan,tilt}]`; each position can be bound to a settings preset |
| `hooks.*` | `""` | Event hook commands, supporting the `{id} {video} {thumb} {time} {date} {duration} {algorithm} {region} {media_dir}` placeholders |
| `loop.enabled` | `false` | Whether loop recording is on |
| `loop.segment_seconds` | `60` | Length of one loop recording segment (seconds) |
| `loop.max_disk_percent` | `30` | Percentage of the whole filesystem the loop footage may occupy; the oldest segments are deleted when it is exceeded |
| `loop.quality` | `26` | CRF of the loop recording |

---

## Scheduled Commands

Besides the scheduling table in the web UI, you can edit `~/.pikrellcam/at-commands.conf` directly (**hot reload,
no restart**):

```text
Mon-Fri 07:30 "@tl_start 30"
Mon-Fri 09:00 "@tl_hold off"
Mon-Fri 17:00 "@tl_hold off"
Fri 18:00 "@tl_end"
Mon 7:30 "record on"
```

The available internal commands are:

```text
record on | off | pause      still              tl_start [秒]     tl_hold on|off
tl_end                       motion_enable on|off|toggle
motion load_regions 名称     motion limits <magnitude_limit> <count_limit>
servo goto 名称              servo set <pan> <tilt>      start | stop | restart
```

Scripts can also push commands into the FIFO (without the `@` prefix):

```bash
echo "record off" > ~/.pikrellcam/commands.fifo
```

---

## Directory Layout

```text
~/pikrellcam-lite/
├── current -> releases/<版本>   # symlink to the running version
├── releases/<版本>/             # one complete, independent directory per version, all of them kept
│   ├── pimotioncam.py              # entry point
│   ├── install.sh / deploy.sh / build_native.sh   # install, publish, native kernel build
│   ├── core/
│   │   ├── app.py               # service container + internal command dispatch
│   │   ├── camera.py            # dual-backend capture (libcamera CSI + ffmpeg/V4L2 USB)
│   │   ├── detect.py            # multi-region dual-algorithm frame-difference detection
│   │   ├── recorder.py          # event recording + ffmpeg pipeline + thumbnails
│   │   ├── presets.py / scheduler.py / timelapse.py / servo.py / hooks.py
│   │   ├── state.py / config.py / util.py / web.py
│   │   ├── i18n.py + locales/   # language packs + Accept-Language negotiation
│   │   └── native.py + _pkc_native.c   # native kernel loader (ctypes) + C source
│   ├── templates/               # index.html / login.html
│   └── static/                  # app.js / i18n.js / style.css
├── config.json          # configuration (shared)
├── media/               # recordings and snapshots (shared)
│   ├── videos/          # event MP4s and timelapse output
│   ├── stills/          # thumbnails (including _obj motion-object crops)
│   └── events.json      # event index
├── logs/                # runtime logs (shared)
└── venv/                # Python virtual environment (shared)
```

---

## Known Limitations

- **The camera must be power-cycled to recover from a "frontend timeout"**. A `reboot` of the Pi does not cut the
  3.3V power rail, so the sensor is never really reset; you have to **unplug the power for 10 seconds and plug it
  back in**. Symptoms: `Camera frontend has timed out!`; the sensor enumerates over I²C but produces no frames.
- If another process holds the camera exclusively you get `Pipeline handler in use by another process`; stop the
  other process before starting the service.
- The browser and the Raspberry Pi must be on the same LAN; for access across networks, set up port forwarding or a
  tunnel yourself.
- Frame differencing is sensitive to abrupt changes in overall illumination (a light being switched on, a curtain
  moving); raising `magnitude_limit` and `count_limit` mitigates this.
- **The orientation of the camera matters**: with the lens pointed at a monitor, the changing content of the screen
  is treated as "motion" and the service keeps triggering recordings.
- The **audio stream** (live audio in the browser) and **audio-triggered recording** are not implemented; recordings with sound themselves are supported (v2.8.0+).
- **A recording has to be closed properly to be playable.** The MP4 index (`moov`) is written by ffmpeg when it exits, so a power cut or a `kill -9` leaves a file that cannot be opened. The service removes such leftovers on startup, so every entry in the recordings list can be played — but the segment that was being recorded at the moment the power went out is still lost.
- Flask runs on its development server; that is good enough for a home LAN, but add your own reverse proxy before
  exposing it to the internet.
