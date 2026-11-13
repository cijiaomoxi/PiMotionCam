# pikrellcam-lite v2

A **motion-detection recording service** for Raspberry Pi OS (Debian 13 / trixie, 64-bit). It reproduces the full
set of web features of the official [PiKrellCam](https://github.com/billw2/pikrellcam), implements them on the
current **libcamera / picamera2** camera stack, and additionally supports **USB cameras**.

Access URL: **http://pi.local:8080/** — current version: **v2.6.0**

`CSI + USB cameras` `libcamera / picamera2` `Frame-differencing motion detection` `Native C kernel` `Event recording with pre/post-roll` `Graphical motion regions` `Dual far/near algorithms` `Timelapse` `Servo pan/tilt` `Scheduled commands` `Event hooks` `Bilingual UI` `Versioned releases with one-command rollback`

> [!NOTE]
> **This is an unofficial, independent implementation.** It is not affiliated with, nor endorsed by,
> the author of [PiKrellCam](https://github.com/billw2/pikrellcam) or by the Raspberry Pi Foundation.
> It matches PiKrellCam in features and interaction, but the code is written from scratch — see
> [Acknowledgements and References](#acknowledgements-and-references).

---

> 📋 **A feature-by-feature comparison with the upstream project** is in [`docs/上游功能对照.md`](docs/上游功能对照.md): which features are covered, which are partially covered, which are missing, and what pikrellcam-lite has that upstream does not.

## Acknowledgements and References

**pikrellcam-lite** (GitHub repository: `pikrellcam_update`) is a multilingual re-implementation
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
  stack (see "Why Not the Official PiKrellCam"). The stacks differ entirely: upstream is C + PHP, this
  project is Python / Flask.
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

---

## Why Not the Official PiKrellCam

The last commit of the official PiKrellCam dates to 2020-06-08, and it is built on the legacy camera stack that
Debian 13 has removed:

| Official dependency | Status on a current system |
| --- | --- |
| `/opt/vc` + `libbrcmmmal-dev` / `libbcm-host-dev` | Delisted from the repositories; `/opt/vc` no longer exists |
| Prebuilt 32-bit ARM (armhf) ELF binaries | The system has no `/lib/ld-linux-armhf.so.3`, so they cannot execute |
| MMAL hardware motion vectors | They belong to the old proprietary stack and are not exposed to user space by the new libcamera stack |

163 `mmal_` call sites in the official source cannot be compiled or run on a pure new-stack system. This
implementation keeps the **user experience** of PiKrellCam but replaces the hardware motion vectors with **frame
differencing**, so it works on a Chinese-locale Raspberry Pi with Raspberry Pi Connect.

---

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
| Video / snapshot / timelapse / archive pages | ✅ Media tab + remote archiving (scp) |
| System log page | ✅ Continuously scrolling log |
| Help page | ✅ Built-in documentation |
| Audio stream | ⚠️ Requires a USB sound card, not implemented |
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

## Deployment

### Method 1: Versioned Publishing (recommended)

Every version is kept independently and **is never overwritten**:

```bash
cd pikrellcam-lite
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
scp -r -i ~/.ssh/id_ed25519_pi_mcode pikrellcam-lite pi@pi.local:~/

# 2. Install on the Raspberry Pi
ssh -i ~/.ssh/id_ed25519_pi_mcode pi@pi.local 'bash ~/pikrellcam-lite/install.sh'

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
| `record.max_disk_gb` | `8` | Size limit of the recording directory; the oldest files are deleted when it is exceeded |
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
│   ├── krellcam.py              # entry point
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
- No audio stream (this would require a USB sound card).
- **A recording has to be closed properly to be playable.** The MP4 index (`moov`) is written by ffmpeg when it exits, so a power cut or a `kill -9` leaves a file that cannot be opened. The service removes such leftovers on startup, so every entry in the recordings list can be played — but the segment that was being recorded at the moment the power went out is still lost.
- Flask runs on its development server; that is good enough for a home LAN, but add your own reverse proxy before
  exposing it to the internet.
