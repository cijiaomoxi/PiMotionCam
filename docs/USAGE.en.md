# pikrellcam-lite User Guide

Written for users who already have a Raspberry Pi and want to install and run a motion-detection recording service on it.

- Applies to: **v2.5.0** (current development version is v2.4.0; this release is v2.5.0)
- Web interface: **http://pi.local:8080/**
- Companion document: technical internals and design rationale live in `README.md` at the repository root. This guide covers "how do I install it and use it".
- Acknowledgements and reference: <https://github.com/billw2/pikrellcam> — this is an independent, unofficial implementation; see "Acknowledgements and References" in the repository root `README.md`.

---

## Table of Contents

1. [Introduction and Features](#1-introduction-and-features)
2. [System Requirements and Hardware Setup](#2-system-requirements-and-hardware-setup)
3. [Installation](#3-installation)
4. [First-Time Configuration](#4-first-time-configuration)
5. [Interface Tour](#5-interface-tour)
6. [Detection Tuning in Depth](#6-detection-tuning-in-depth)
7. [Recording and Events](#7-recording-and-events)
8. [Timelapse, Servo, Scheduled Commands, and Event Hooks](#8-timelapse-servo-scheduled-commands-and-event-hooks)
9. [Complete Configuration Reference](#9-complete-configuration-reference)
10. [API Reference](#10-api-reference)
11. [Multiple Languages](#11-multiple-languages)
12. [Version Management and Rollback](#12-version-management-and-rollback)
13. [Packaging and Release](#13-packaging-and-release)
14. [Native Acceleration](#14-native-acceleration)
15. [Troubleshooting](#15-troubleshooting)
16. [Security Recommendations](#16-security-recommendations)

---

## 1. Introduction and Features

pikrellcam-lite is a **motion-detection recording service** that runs on a Raspberry Pi. The camera streams continuously; when motion appears in the frame it triggers a recording automatically, and once the recording finishes it produces a full-frame thumbnail plus a cropped image of the moving object. You tune parameters, review recordings, and do maintenance from a browser-based management console.

It reproduces the web features of the official [PiKrellCam](https://github.com/billw2/pikrellcam) and adds a number of enhancements on top.

### How It Differs from Official PiKrellCam

The official PiKrellCam's last commit dates to 2020. It was built on the legacy MMAL camera stack that Debian 13 has removed, so it no longer compiles or runs on current systems. pikrellcam-lite keeps the official user experience but replaces the foundation:

| Area | Official PiKrellCam | pikrellcam-lite |
| --- | --- | --- |
| Camera stack | MMAL (`/opt/vc`, delisted from the repos) | libcamera / picamera2 |
| Motion detection | BCM2835 hardware motion vectors | Frame differencing with neighborhood density denoising |
| Cameras | CSI only | CSI **and** USB (UVC) |
| Native acceleration | None | C kernel (loaded via ctypes), roughly 4.7x faster end-to-end |
| Capture path | Fixed | Switch between ISP hardware JPEG and raw RGB at any time |
| Failure recovery | None | Frame-fetch watchdog plus automatic degradation (resolution → frame rate → fall back to RGB888) |
| Version management | None | One independent directory per version with one-command rollback |
| Interface language | Chinese | Switchable Chinese / English |

### Main Features

- **Live preview**: a multipart MJPEG long-lived stream. The OSD overlay (clock, FPS, region boxes) is rendered by the browser and never burned into the image.
- **Graphical motion regions**: draw rectangles directly on the preview, then move, resize, and rename them. Multiple regions are supported.
- **Two parallel detection algorithms**: `far` (small, slow, distant targets) and `near` (large, close targets), each with independently tunable sensitivity.
- **Pre-roll and post-roll**: the frames captured just before motion was detected are automatically included, so a target that walks in and out immediately is not missed.
- **Event playback**: every event yields an MP4 recording, a full-frame thumbnail, and a cropped moving-object thumbnail.
- **Self-managing disk usage**: the oldest recordings are deleted automatically once the size limit is exceeded.
- **Timelapse**: capture frames on an interval and stitch them into an MP4 automatically.
- **Servo pan/tilt**: automatic backend detection across RPi.GPIO, ServoBlaster, and lgpio, with position presets and angle limits.
- **Scheduled commands**: run commands by weekday and time or on a fixed interval, configured from the web UI, from a hot-reloaded `at-commands.conf` file, or through a FIFO.
- **Event hooks**: run your own commands when motion starts or ends, when a preview is saved, and when a timelapse finishes.
- **USB webcams**: ffmpeg + V4L2 with MJPEG passthrough and zero transcoding.
- **Version management**: every version is kept independently, nothing is ever overwritten, and rollback is a single command.
- **Bilingual interface**: switch languages from the top bar at any time, with no service restart.

---

## 2. System Requirements and Hardware Setup

### Hardware

| Item | Requirement |
| --- | --- |
| Raspberry Pi | **Raspberry Pi 4** (recommended). Pi 3B / Zero also work; installation automatically drops them to 640x480 @ 8fps. Pi 5 is supported as well. |
| Storage | microSD card, 16 GB or larger |
| Camera (pick one) | **CSI ribbon camera** (such as ov5647), or a **USB / UVC camera** |
| Network | Same LAN as your browser, with `pi.local` resolvable |

### Operating System

- Raspberry Pi OS (Debian 13 / trixie, 64-bit), or a comparable Debian 13 arm64 system.
- Root access for a one-time `apt` installation.

### Camera Wiring

**CSI ribbon camera**

1. **Power down** the Raspberry Pi first. Hot-plugging the ribbon damages the connector.
2. Insert the ribbon into the camera module's connector and push it all the way in.
3. Insert the other end of the ribbon into the CSI camera connector on the board, all the way in, and close the connector clip.
4. The ribbon is directional; follow the camera and board vendor instructions (usually the blue stiffened side faces the board).
5. Do not fold the ribbon at a right angle; use a bracket for long-term installations.

**USB camera**

Simply plug it into a USB port on the Pi. No extra configuration is needed; the system exposes it as `/dev/videoN`.

> Tip: the libcamera stack in Debian 13 ships only Raspberry Pi's own processors and **cannot enumerate USB cameras**. pikrellcam-lite implements an ffmpeg + V4L2 backend for this, so USB cameras must be picked manually under "System → Camera" in the web interface.

### Confirm the Camera Is Detected

Run these on the Raspberry Pi after wiring it up:

```bash
# CSI camera: can libcamera see it?
libcamera-hello --list-cameras

# USB camera: V4L2 nodes and supported formats
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

---

## 3. Installation

### 3.1 Copy the Source to the Raspberry Pi

Run this on your **development machine** (replace `PKC_KEY` with your SSH private key path):

```bash
scp -r -i ~/.ssh/id_ed25519_pi_mcode pikrellcam-lite pi@pi.local:~/
```

### 3.2 Run the Install Script

Log in to the Raspberry Pi and run:

```bash
ssh -i ~/.ssh/id_ed25519_pi_mcode pi@pi.local
bash ~/pikrellcam-lite/install.sh
```

The install script performs these steps in order:

1. Checks for and installs missing system packages (`python3-venv`, `python3-picamera2`, `python3-numpy`, `python3-pil`, `ffmpeg`).
2. Creates the virtual environment `~/pikrellcam-lite/venv` with `--system-site-packages` so it reuses the system picamera2 and numpy.
3. Installs Flask into that virtual environment.
4. Copies the source into the version directory `~/pikrellcam-lite/releases/<timestamp>-v<version>/` and points the `current` symlink at it.
5. Writes the systemd user service `~/.config/systemd/user/pikrellcam-lite.service` and enables it with `enable --now`.
6. Compiles the native acceleration kernel. If compilation fails, the service automatically falls back to the pure Python implementation.
7. Runs `loginctl enable-linger` so the service **starts at boot even without a graphical login session**.

### 3.3 Install the Optional Dependencies

The install script covers the base dependencies above, but these two need to be installed by hand:

```bash
# rpicam-apps: required for the CSI "ISP hardware JPEG" capture path (provides rpicam-vid)
sudo apt-get install -y rpicam-apps

# gcc: required to compile the native acceleration kernel
sudo apt-get install -y gcc

# libjpeg62-turbo-dev: required for JPEG encoding in the native kernel
# (build_native.sh installs this automatically if it is missing)
sudo apt-get install -y libjpeg62-turbo-dev
```

| Dependency | Purpose | If missing |
| --- | --- | --- |
| `python3-venv` | Creating the virtual environment | The install script cannot run |
| `python3-picamera2` | libcamera capture path | CSI cameras are unusable |
| `python3-numpy` | Frame differencing | The service cannot start |
| `python3-pil` | Image decoding and thumbnails | Preview and thumbnails are unavailable |
| `ffmpeg` | Video encoding, timelapse conversion | **Recording is impossible** |
| `rpicam-apps` | Provides `rpicam-vid` | CSI cameras silently fall back to the raw RGB path (higher CPU) |
| `gcc` | Compiling the C kernel | Automatic fallback to the pure Python implementation |
| `libjpeg62-turbo-dev` | JPEG encoding in the C kernel | Same fallback |

### 3.4 Verify the Installation

```bash
# Service status
systemctl --user status pikrellcam-lite.service

# Live logs
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f

# Open the management console
# Browse to http://pi.local:8080/
```

### 3.5 Start at Boot

`install.sh` already runs `loginctl enable-linger`, so normally nothing more is needed. Verify manually:

```bash
loginctl show-user "$USER" --property=Linger
```

Output of `Linger=yes` means the service starts even without a login session.

---

## 4. First-Time Configuration

### 4.1 Open the Management Console

Browse to **http://pi.local:8080/**. If `pi.local` does not resolve, use the Raspberry Pi's IP address directly.

### 4.2 Set the Access Password

Go to the **System** tab → **Upgrade and Password**:

- Type a new password and click "Save Password" to enable password protection.
- **Leaving it blank** and saving disables password protection.
- The password is stored as `sha256:<hex>` in `web.password_hash` in `config.json` and survives restarts.
- Once enabled, every page redirects to the login page, and unauthenticated `/api/` calls return `401` with `{"auth": true}`.

> See [Section 15](#15-troubleshooting) if you forget the password.

### 4.3 Select a Camera

Go to the **System** tab → **Camera**:

1. Pick the target camera from the dropdown (a CSI ribbon camera, or a USB camera shown as `/dev/videoN`), or keep "Auto".
2. Click "Refresh List" to re-enumerate devices.
3. Choose a **capture path** (see the table below) and click "Switch".

Capture paths differ in only one respect: whether JPEG is encoded by hardware or by the CPU.

| Path | Meaning | Applies to | Notes |
| --- | --- | --- | --- |
| Auto (`auto`) | CSI prefers MJPEG; USB uses ffmpeg passthrough | Default | Recommended |
| ISP hardware JPEG (`MJPEG`) | Captures with `rpicam-vid`; the ISP encodes JPEG in hardware and the JPEG bytes are passed straight through to preview and recording | CSI | Software JPEG encoding cost drops to zero (`jpeg_ms = 0.0`); requires `rpicam-apps` |
| Raw RGB (`RGB888`) | Captures raw frames with picamera2 and encodes JPEG with the local C kernel (libjpeg-turbo) | CSI | Used automatically when 90/270 degree rotation is requested |

The same pair of dropdowns plus a "Switch" button also appears on the **Live Preview** tab; both places do the same thing.

### 4.4 Set Rotation and Flip

Go to **Detection Tuning** → **Camera Parameters**:

- **Rotation**: `0` / `90` / `180` / `270`.
  - `0` and `180` are handled directly by the ISP at **zero CPU cost**.
  - `90` and `270` require a transpose the ISP cannot perform, so capture automatically switches to the raw RGB path and rotates in software, using slightly more CPU.
- **Flip**: `none` / `horizontal` / `vertical` / `both`.

> Rotation and flip are not supported on the USB path: USB uses MJPEG passthrough, and transforming the image would require decoding and re-encoding. The setting is kept in the configuration but has no effect, and a note appears in the log.

### 4.5 Confirm the Picture Is Healthy

Switch to the **Live Preview** tab. You should see a continuously updating picture with an OSD overlay in the corners:

- Top left: time and status badge (Still / Motion)
- Top right: FPS, detection FPS, event count, disk usage
- Bottom left: the algorithm and region that matched, the change ratio, and the active preset
- Bottom right: the motion bounding box coordinates

The top bar simultaneously shows FPS, detection FPS, event count, disk usage, and the current preset.

---

## 5. Interface Tour

The interface has six tabs.

### 5.1 Live Preview

The live picture is on the left; motion regions and region presets are on the right.

**Picture area**

- Above the picture are two dropdowns: **camera selection** and **capture path selection**, plus a "Switch" button.
- Below the picture are four buttons: **Pause Detection**, **Pause Recording**, **Take Snapshot**, and **Restart Service**.
- The OSD drawn over the picture is an HTML overlay and does not affect recording quality.

**Drawing detection regions on the preview** (the key interaction)

| Action | Result |
| --- | --- |
| **Hold the left mouse button and drag** on empty picture area | Draws a new rectangular region, created on mouse release |
| **Click a row** in the region list on the right | Selects that region (click again to deselect) |
| **Drag the selected box** | Moves the region |
| Drag the **small square at the bottom-right corner** of the box | Resizes the region |
| **Double-click the box** | Renames the region |
| "Rename / Delete" buttons in the region list | Renames or deletes a specific region |
| Enter a name below the region list and click "**Add Full-Screen Region**" | Adds a region covering the whole frame |

Additional details:

- Drags shorter than 1.5% of the picture are treated as misclicks and ignored.
- There is a limit of **32** regions.
- A newly drawn region is named "Region N" automatically and is **selected immediately**, so you can rename or fine-tune it right away.
- Region coordinates are stored as ratios of the picture (0 to 1), so positions stay put when you change resolution.
- Click "**Save Regions**" to write the changes to the configuration; most other interactions save automatically as well.

**Region presets**

In the "Region Presets" panel, enter a name and click "Save Current as Preset" to store the current set of regions under a name. Pick it from the dropdown later and click "Load" to switch over in one go.

### 5.2 Detection Tuning

- **Dual Algorithm Sensitivity**: the `far` and `near` parameter sets, detailed in [Section 6](#6-detection-tuning-in-depth).
- **Detection Switches**: enable motion detection, and start detecting as soon as the service starts (the latter currently only stores its value; whether detection actually runs is governed by "Enable Motion Detection").
- **Recording Parameters**: pre-roll, post-roll, event gap, maximum event length, disk limit, encoding quality CRF, encoder.
- **Camera Parameters**: main stream resolution, frame rate, rotation, flip, detection resolution, detection frame rate, and exposure (the exposure slider currently only stores its value and does not change the camera's automatic exposure behavior).
- **Timelapse Parameters**: enable switch, default period, and start in hold mode.
- Two buttons at the bottom: **Save Configuration** and **Restore Default Configuration**.
- **Configuration Presets**: store the entire current configuration under a name and activate it with one click.

> Changing resolution, frame rate, rotation, flip, capture path, or camera **rebuilds the capture pipeline**, so the picture is interrupted for a few seconds.

### 5.3 Media

- **Timelapse**: enter a period in seconds and click "Start"; "Hold" pauses frame capture; "End and Compose" turns the captured frames into an MP4.
- **Event Recordings**: lists every event; click an entry to view it; each entry has an "Archive to Remote" button on the right.
- **Video Files** / **Snapshot Images**: two file lists you can open directly.
- Three clear buttons at the top: **Clear Videos**, **Clear Snapshots**, and **Clear All**.

### 5.4 Scheduled Commands

- **Add / Edit Scheduled Command**: weekday, time, interval (minutes), command text, and an enable switch.
  - Weekdays accept `*`, `Mon-Fri`, `Mon,Wed`, and similar forms.
  - **An interval greater than 0 takes priority over the time**, meaning the command runs every N minutes.
- **Command List**: a table of all scheduled commands, each of which can be enabled, disabled, or deleted; the "Reload" button re-reads both the configuration and `at-commands.conf`.
- **Run Immediately**: type a command and run it right away; the output appears below (only [internal commands](#83-scheduled-commands) are supported).

### 5.5 Servo

- **Servo Status**: the current backend, whether it is enabled, the current angles, the pins, and the limits.
- **Manual Control**: Pan / Tilt sliders plus a smoothing time in milliseconds; click "Move to Position" to apply.
- **Position Presets**: save, recall, and delete named positions. The three built-in presets are named "左", "中", and "右" (left, center, right).

### 5.6 System

- **Service Control**: start / stop / restart the service.
- **Camera**: device and capture path selection.
- **Upgrade and Password**: one-click upgrade (`git pull` plus a restart) and the access password.
- **Version and Release**: the running version, what `current` points to, and the list of retained historical versions.
- **Event Hooks**: command inputs for the four hooks; the panel below shows the 50 most recent hook executions.
- **System Information**: model, system version, Python version, application directory, media directory, hostname, and uptime.
- **Help**: built-in feature overview.
- **Live Log**: a scrolling log refreshed every second, with optional auto-scroll and a clear button.

---

## 6. Detection Tuning in Depth

### 6.1 How Detection Works

Every frame is first downsampled to a grayscale image (320x180 by default), then differenced against the previous frame:

1. Threshold against `magnitude_limit` to mark "changed" pixels.
2. Apply neighborhood density filtering to remove isolated noise (equivalent to the official "sparkle" filter).
3. Count the fraction of changed pixels inside each motion region; the region matches when it exceeds `count_limit`.
4. Require `consecutive_frames` consecutive matches before declaring motion.

The two algorithms run **in parallel**, each judging every region independently.

### 6.2 The Difference Between `far` and `near`

| Algorithm | Target | Default `magnitude_limit` | Default `count_limit` | Default `consecutive_frames` | Default `noise_filter` |
| --- | --- | --- | --- | --- | --- |
| `far` | Distant, small, slow targets | 12 | 0.006 | 2 | 2 |
| `near` | Close, large targets | 28 | 0.02 | 2 | 3 |

- **`far` is more sensitive**: the thresholds are low, so it reacts faster to small slow movement far away (a distant figure, a small animal crossing) — and is also more easily triggered by lighting changes or a curtain blowing.
- **`near` is more conservative**: the thresholds are high, so it only responds to large, rapidly changing targets, which suits close-range scenes such as a doorway or a driveway.

**How to choose:**

- Monitoring a far walkway, yard, or balcony → rely mainly on `far`, and consider turning `near` off to cut down false positives.
- Monitoring a doorway, garage, or other close-range scene → rely mainly on `near`.
- Want both → enable both (the default) and tune each one's thresholds separately.

### 6.3 What Each Parameter Means

| Parameter | Meaning | Effect of raising it | Effect of lowering it |
| --- | --- | --- | --- |
| `magnitude_limit` | **Per-pixel grayscale difference threshold.** A pixel counts as changed only if its brightness changed by more than this between two frames. | Sluggish, noise-resistant | Sensitive, prone to false positives |
| `count_limit` | **Fraction of changed pixels inside the region.** Changed pixels divided by total pixels in the region. | Sluggish | Sensitive |
| `consecutive_frames` | **Number of consecutive matching frames** required before motion is declared. | Sluggish, jitter-resistant | Sensitive, prone to false positives |
| `noise_filter` | **Neighborhood denoising radius.** `0` disables it; `k` means that within a `(2k+1) x (2k+1)` neighborhood, at least a quarter of the pixels must have changed for the change to count as significant. | Stronger noise removal | Retains more detail |

### 6.4 Recommended Tuning Order

1. Turn on `motion.enabled` and confirm the preview looks healthy.
2. **Tune `count_limit` first** — it is the parameter with the biggest effect (it decides "how much movement counts").
   - Too many false positives → raise `count_limit`.
   - Missed events → lower `count_limit`.
3. Still too many false positives → raise `magnitude_limit`, or increase `noise_filter`.
4. The picture itself is jittery (leaves in wind, reflections) → raise `consecutive_frames` to 3–5.
5. Exclude what you do not care about: shrink the region on the preview, or disable it in the region list.
6. Missing small distant targets → adjust only `far`'s `count_limit`; leave `near` alone.

> Frame differencing is sensitive to **sudden changes in overall lighting** (lights switched on or off, curtains moving). Raising `magnitude_limit` and `count_limit` helps.
> Another common false-positive source is a **camera pointed at a monitor**: changing screen content looks like motion.

---

## 7. Recording and Events

### 7.1 The Recording Flow

1. The service continuously maintains a **ring buffer** holding the most recent `pre_seconds` of JPEG frames.
2. When detection matches, an event starts and the pre-recorded frames plus the current frame are piped into ffmpeg.
3. Recording continues for `post_seconds` after motion stops.
4. ffmpeg encodes while it receives frames using `image2pipe`, so **no intermediate files are produced and the disk is not read twice**.
5. When the event ends, thumbnails are generated and the event index is updated.

This means a target that steps into frame and immediately leaves is not lost — the frames from just before the trigger were already in the buffer.

### 7.2 Key Parameters

| Parameter | Default | Meaning |
| --- | --- | --- |
| `pre_seconds` | 5 | Seconds of pre-roll captured before the trigger (0–30). Set to 0 to disable pre-roll. |
| `post_seconds` | 8 | Seconds of post-roll captured after motion stops (0–60). |
| `event_gap_seconds` | 10 | Minimum interval between two events. Motion occurring sooner after the previous event ended does not start a new event, which prevents continuous jitter from producing a swarm of tiny clips. |
| `max_event_seconds` | 120 | Maximum length of a single event (5–600). Sustained motion forces the event to end so a file can never grow without bound. |
| `max_disk_gb` | 8 | Size limit for the recording directory in GB (1–128). The oldest recordings are deleted automatically once it is exceeded. `0` disables the limit. |
| `encoder` | auto | Encoder, see below. |
| `quality` | 23 | CRF value for `libx264`, from 10 to 40. Lower means better quality and larger files. It does not apply to the hardware encoder. |

### 7.3 Choosing an Encoder

| Value | Description |
| --- | --- |
| `auto` | Uses `h264_v4l2m2m` when a hardware H.264 encoder is detected (`/dev/video31` exists, or `v4l2-ctl --list-devices` reports `bcm2835-codec`), otherwise `libx264`. |
| `h264_v4l2m2m` | Forces the Raspberry Pi hardware encoder at a fixed 4 Mbps bitrate. Recommended on Pi 4/5. |
| `libx264` | Forces software encoding with quality controlled by `quality` (CRF). |

All output is MP4 (`yuv420p` pixel format, `+faststart` for smooth web playback).

### 7.4 What Gets Produced

Each event produces:

| File | Location | Description |
| --- | --- | --- |
| `<event-id>.mp4` | `media/videos/` | The event recording |
| `<event-id>.jpg` | `media/stills/` | Full-frame thumbnail (320x180) |
| `<event-id>_obj.jpg` | `media/stills/` | Cropped moving-object thumbnail (240x240) |
| Index entry | `media/events.json` | Event ID, start and end time, duration, frame count, size, encoder, and the algorithm and region that matched |

Event IDs use the format `YYYYMMDD_HHMMSS`.

### 7.5 Archiving an Event to a Remote Host

Every event in the **Media** tab has an "Archive to Remote" button, and you can also use the API:

```bash
# Archive a single event
curl -X POST http://pi.local:8080/api/archive \
  -H 'Content-Type: application/json' \
  -d '{"id": "20261111_203015"}'
```

Archiving uses `scp`. The destination comes from `media.archive_target`, in the form `user@host:/path`:

```json
{
  "media": {
    "archive_target": "pi@nas.local:/volume1/camera"
  }
}
```

The Raspberry Pi must already have passwordless SSH access to the target host. **The destination directory must exist and be writable**, otherwise `scp` fails and the interface reports the error.

### 7.6 Pausing Recording

Click "Pause Recording" on the **Live Preview** tab, or call:

```bash
curl -X POST http://pi.local:8080/api/record \
  -H 'Content-Type: application/json' \
  -d '{"action": "pause"}'
```

Resume with `{"action": "resume"}` (equivalent to `"on"`).

---

## 8. Timelapse, Servo, Scheduled Commands, and Event Hooks

### 8.1 Timelapse

**Configuring it**: the timelapse panel in the **Media** tab, or **Detection Tuning** → Timelapse Parameters (default period, start in hold mode).

| Parameter | Default | Meaning |
| --- | --- | --- |
| `timelapse.enabled` | `false` | Whether the timelapse feature is enabled |
| `timelapse.period` | 30 | Default capture interval in seconds |
| `timelapse.hold` | `false` | Whether to start in hold mode (no frames captured while held) |

**Operating it**:

1. Enter a period in seconds and click "Start". Frames are written to `media/timelapse/<session-id>/frame_00000.jpg`.
2. Click "Hold" to pause capture; click it again to resume.
3. Click "End and Compose" to turn the captured frames into `media/videos/timelapse_<session-id>.mp4` with ffmpeg (libx264, CRF 23). The temporary frame directory is then removed.

The output frame rate is `round(1 / period)`, with a floor of 1 fps.

**Controlling it from a command**:

```bash
curl -X POST http://pi.local:8080/api/timelapse \
  -H 'Content-Type: application/json' \
  -d '{"action": "start", "period": 30}'
```

`action` accepts `start` (optionally with `period`), `hold` (optionally with `on`), and `end`.

### 8.2 Servo

| Parameter | Default | Meaning |
| --- | --- | --- |
| `servo.enabled` | `false` | Whether the servo is enabled |
| `servo.backend` | auto | Backend: `auto` / `lgpio` / `rpi` / `servoblaster` / `none` |
| `servo.pan_pin` | 18 | Pan servo BCM pin |
| `servo.tilt_pin` | 17 | Tilt servo BCM pin |
| `servo.pan_min` / `pan_max` | 0 / 180 | Pan angle limits |
| `servo.tilt_min` / `tilt_max` | 0 / 180 | Tilt angle limits |
| `servo.smooth_ms` | 0 | Smoothing time in milliseconds; 0 means jump straight to the target |
| `servo.positions` | 3 presets | Position preset list, `[{name, pan, tilt}]` |

**Backend detection order**: `RPi.GPIO` → `servoblaster` → `lgpio` → unavailable. When none is present the servo feature degrades gracefully and does not affect anything else.

**Using the web interface**: the **Servo** tab → click "Enable Servo", set the angles with the Pan / Tilt sliders, then click "Move to Position". Enter a name and click "Save as Position Preset" to store the current angles.

**Command interface**:

```bash
curl -X POST http://pi.local:8080/api/servo \
  -H 'Content-Type: application/json' \
  -d '{"action": "set", "pan": 90, "tilt": 45}'
```

`action` accepts `enable`, `disable`, `goto` (with `name`), `set` (with `pan`/`tilt`/`smooth_ms`), `save_position`, and `delete_position`.

### 8.3 Scheduled Commands

There are three equivalent ways to configure them.

**(a) Web interface**: the **Scheduled Commands** tab → add / edit → save.

**(b) Configuration file**: `~/.pikrellcam/at-commands.conf`, **hot-reloaded with no restart**:

```
Mon-Fri 07:30 "@tl_start 30"
Mon-Fri 09:00 "@tl_hold off"
Fri 18:00 "@tl_end"
Mon 7:30 "record on"
```

The format is `<weekday> <time or interval in minutes> "<command>"`. Weekdays accept `*`, `Mon-Fri`, `Mon,Wed`; a time without a `:` is treated as a fixed interval in minutes. Commands starting with `@` are handed to the internal command handler; anything else is processed as an ordinary command.

> **Note: the scheduler only executes the internal commands listed above.** An unrecognized command returns `unknown command: …` and is **not** run as a shell command. To run an arbitrary shell command, use an [event hook](#84-event-hooks) instead.

**(c) FIFO**: external scripts can write commands into `~/.pikrellcam/commands.fifo` (no `@` prefix needed):

```bash
echo "record off" > ~/.pikrellcam/commands.fifo
```

**Available internal commands**:

| Command | Effect |
| --- | --- |
| `record on` / `record off` / `record pause` | Start / stop / pause recording |
| `record_pause` | Pause recording (same as above) |
| `still` | Capture a snapshot of the current frame |
| `tl_start [seconds]` | Start a timelapse, optionally with a given period |
| `tl_hold on` / `tl_hold off` | Hold / resume frame capture |
| `tl_end` | End the timelapse and compose the video |
| `motion_enable on` / `off` / `toggle` | Turn motion detection on / off / toggle |
| `motion load_regions <name>` | Load a named region preset |
| `motion limits <magnitude_limit> <count_limit>` | Change the two thresholds of the `far` algorithm |
| `servo goto <name>` | Move to a position preset |
| `servo set <pan> <tilt>` | Set the angles directly |
| `servo enable` | Enable the servo |
| `start` / `stop` / `restart` | Start, stop, or restart the whole service |

A leading `@` is allowed and is stripped automatically. **The command must be one of the internal commands above**: an unrecognized command returns `unknown command: …` and is not executed as a shell command.

**Run a command immediately**:

```bash
curl -X POST http://pi.local:8080/api/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "record on"}'
```

### 8.4 Event Hooks

Configure the four hooks in the **System** tab → **Event Hooks**:

| Hook | Fires when |
| --- | --- |
| `on_motion_begin` | The moment an event starts recording |
| `on_motion_end` | The event ends |
| `on_motion_preview_save` | The recording and thumbnails have been written successfully |
| `on_timelapse_end` | The timelapse has ended and been composed |

Placeholders in the command text are substituted when the hook fires:

| Placeholder | Value |
| --- | --- |
| `{id}` | Event ID, such as `20261111_203015` |
| `{video}` | Video file name |
| `{thumb}` | Thumbnail file name |
| `{duration}` | Event duration in seconds |
| `{algorithm}` | The algorithm that matched (`far` / `near`) |
| `{region}` | The name of the region that matched |
| `{time}` | Current time as `HH:MM:SS` |
| `{date}` | Current date as `YYYY-MM-DD` |
| `{media_dir}` | Media root directory |
| `{stills_dir}` | Snapshot directory |
| `{videos_dir}` | Video directory |

Examples:

```
echo "motion started: {id} algorithm={algorithm} region={region} time={time}" >> /tmp/motion.log
curl -s -X POST http://192.168.1.10:8080/api/command -d '{"command":"record on"}'
```

Hooks run in their own thread with a 120-second timeout per execution. The execution history (command, status, return code, output) is shown in the hook history panel on the **System** tab.

---

## 9. Complete Configuration Reference

The configuration file lives at `~/pikrellcam-lite/config.json` and holds **63 configuration keys** across 10 top-level sections. The defaults below match `DEFAULT_CONFIG` in `core/config.py` exactly.

### 9.1 camera — Capture

| Key | Default | Meaning |
| --- | --- | --- |
| `camera.resolution` | `[1280, 720]` | Main stream capture resolution (width, height). Pi 3B/Zero are automatically set to `[640, 480]`. |
| `camera.fps` | `10` | Capture frame rate, 1–30. |
| `camera.buffer_count` | `6` | libcamera buffer count, minimum 3. |
| `camera.rotation` | `0` | Rotation: `0` / `90` / `180` / `270`. 0 and 180 are free from the ISP; 90 and 270 automatically switch to software rotation over the RGB888 path. Not supported on the USB path. |
| `camera.flip` | `none` | Flip: `none` / `horizontal` / `vertical` / `both`. Not supported on the USB path. |
| `camera.jpeg_quality` | `72` | JPEG quality for preview and recording frames. |
| `camera.detect_resolution` | `[320, 180]` | Downsample size used for detection (width, height). |
| `camera.detect_fps` | `10` | Detection frame rate, 1–30. |
| `camera.exposure` | `-1` | Exposure time in microseconds; `-1` means fully automatic exposure. **The current version only stores this value; the capture chain does not apply it to the sensor**, so exposure always stays fully automatic under AE. |
| `camera.device` | `auto` | Camera: `auto` / a libcamera index (such as `0`) / a libcamera id / `/dev/videoN`. |
| `camera.format` | `auto` | Capture path: `auto` / `MJPEG` / `RGB888` (plus `XBGR8888` / `YUYV` / `YUV420` as internally negotiated formats). The USB backend auto-detects MJPEG passthrough. |
| `camera.stall_timeout` | `8.0` | Frame-fetch watchdog in seconds. If no new frame arrives within this time, the capture pipeline is considered dead and is rebuilt. |
| `camera.min_fps` | `0.5` | Minimum frame rate. If the rate stays below this for `stall_timeout` seconds, the pipeline is likewise considered dead. Set to `0` to disable the check. |
| `camera.ae_constraint` | `normal` | AE metering mode: `normal` (full frame) / `highlight` / `shadows` / `custom`. Note that `highlight` makes the picture noticeably darker. |

### 9.2 motion — Detection

| Key | Default | Meaning |
| --- | --- | --- |
| `motion.enabled` | `true` | Whether motion detection is on. Can be toggled live from the web interface. |
| `motion.startup_motion` | `true` | Whether to start detecting as soon as the service starts. **The current version only stores this value**; whether detection actually runs is governed by `motion.enabled`, which defaults to `true` (so detection does start at launch). |
| `motion.algorithms.far.enabled` | `true` | Enable the `far` algorithm. |
| `motion.algorithms.far.magnitude_limit` | `12` | Per-pixel grayscale difference threshold for `far`. |
| `motion.algorithms.far.count_limit` | `0.006` | Fraction-of-changed-pixels threshold for `far`. |
| `motion.algorithms.far.consecutive_frames` | `2` | Consecutive matching frames required by `far`. |
| `motion.algorithms.far.noise_filter` | `2` | Neighborhood denoising radius for `far`; `0` disables it. |
| `motion.algorithms.near.enabled` | `true` | Enable the `near` algorithm. |
| `motion.algorithms.near.magnitude_limit` | `28` | Per-pixel grayscale difference threshold for `near`. |
| `motion.algorithms.near.count_limit` | `0.02` | Fraction-of-changed-pixels threshold for `near`. |
| `motion.algorithms.near.consecutive_frames` | `2` | Consecutive matching frames required by `near`. |
| `motion.algorithms.near.noise_filter` | `3` | Neighborhood denoising radius for `near`; `0` disables it. |
| `motion.regions` | 1 region | Array of motion regions, each `{name, x, y, w, h, enabled}`, with coordinates normalized to 0–1. The default is a single region named "全画面" covering the whole frame (`x=0, y=0, w=1, h=1`). |
| `motion.region_presets` | `{}` | Named region presets, mapping a name to an array of regions. |

### 9.3 record — Recording

| Key | Default | Meaning |
| --- | --- | --- |
| `record.pre_seconds` | `5` | Seconds of pre-roll before the trigger. |
| `record.post_seconds` | `8` | Seconds of post-roll after the trigger. |
| `record.event_gap_seconds` | `10` | Minimum interval between two events, in seconds. |
| `record.max_event_seconds` | `120` | Maximum length of a single event, in seconds. |
| `record.max_disk_gb` | `8` | Size limit for the recording directory in GB; `0` disables the limit. |
| `record.encoder` | `auto` | Encoder: `auto` / `h264_v4l2m2m` / `libx264`. |
| `record.quality` | `23` | CRF value for `libx264` (10–40); lower means better quality. |
| `record.paused` | `false` | Whether recording is paused. |
| `record.frame_write_timeout` | `8` | Longest wait, in seconds, for one frame to reach the encoder. On timeout the encoder is treated as stuck: the recording is abandoned and the service keeps running. |
| `record.encoder_close_timeout` | `15` | Longest wait, in seconds, for ffmpeg to finish writing the `moov` atom when a recording ends. |
| `record.encoder_cooldown` | `60` | Seconds to stop trying to record after the encoder got stuck, so every motion event does not wait for a timeout. |

### 9.4 timelapse — Timelapse

| Key | Default | Meaning |
| --- | --- | --- |
| `timelapse.enabled` | `false` | Whether the timelapse feature is enabled. |
| `timelapse.period` | `30` | Default capture interval in seconds. |
| `timelapse.hold` | `false` | Whether to start in hold mode (no frames captured while held). |

### 9.5 web — Interface and Security

| Key | Default | Meaning |
| --- | --- | --- |
| `web.host` | `0.0.0.0` | Listen address. |
| `web.port` | `8080` | Listen port. |
| `web.password_hash` | `""` | Password hash in the form `sha256:<hex>`; an empty string disables password protection. |
| `web.osd` | `true` | Whether the OSD overlay is shown. **The current version does not wire this switch up**, so the OSD is always shown. |
| `web.show_vectors` | `false` | Whether motion vectors are shown (for debugging). **The current version does not wire this switch up**; the key is retained only for compatibility with the official configuration layout. |
| `web.language` | `auto` | Interface language: `auto` (picked from the browser's `Accept-Language` header) / `zh-CN` / `en-US`. |

### 9.6 media — Media Directories

| Key | Default | Meaning |
| --- | --- | --- |
| `media.dir` | `""` | Media directory. Empty means `~/pikrellcam-lite/media/`; a relative path is resolved against the shared root, an absolute path is used as-is, for example `/mnt/usb`. |
| `media.archive_target` | `""` | Remote archive target in the form `user@host:/path`. |

### 9.7 servo — Servo

| Key | Default | Meaning |
| --- | --- | --- |
| `servo.enabled` | `false` | Whether the servo is enabled. |
| `servo.backend` | `auto` | Backend: `auto` / `lgpio` / `rpi` / `servoblaster` / `none`. |
| `servo.pan_pin` | `18` | Pan servo BCM pin number. |
| `servo.tilt_pin` | `17` | Tilt servo BCM pin number. |
| `servo.pan_min` | `0` | Pan lower limit in degrees. |
| `servo.pan_max` | `180` | Pan upper limit in degrees. |
| `servo.tilt_min` | `0` | Tilt lower limit in degrees. |
| `servo.tilt_max` | `180` | Tilt upper limit in degrees. |
| `servo.smooth_ms` | `0` | Smoothing time in milliseconds; `0` means jump straight to the target. |
| `servo.positions` | 3 presets | Position preset list, `[{name, pan, tilt}]`; an existing name is overwritten. The three defaults are named "左", "中", and "右" with pan angles of 30°, 90°, and 150°, all at a tilt angle of 90°. |

### 9.8 hooks — Event Hooks

| Key | Default | Meaning |
| --- | --- | --- |
| `hooks.on_motion_begin` | `""` | Command run when motion begins. |
| `hooks.on_motion_end` | `""` | Command run when motion ends. |
| `hooks.on_motion_preview_save` | `""` | Command run after the recording and thumbnails are saved successfully. |
| `hooks.on_timelapse_end` | `""` | Command run after the timelapse ends and is composed. |

### 9.9 schedules — Scheduled Commands

| Key | Default | Meaning |
| --- | --- | --- |
| `schedules` | `[]` | Array of scheduled commands. Each entry has `days` (weekday), `time` (`HH:MM`), `interval_minutes` (fixed interval in minutes, takes priority when greater than 0), `command`, and `enabled`. |

### 9.10 presets — Configuration Presets

| Key | Default | Meaning |
| --- | --- | --- |
| `presets` | `{}` | Named configuration presets, each holding a fragment of the configuration. Activating one merges it into the current configuration; if the resolution or frame rate changes, capture restarts automatically. |

### 9.11 Editing the Configuration by Hand

```bash
# Change the port
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home()/"pikrellcam-lite/config.json"
c = json.loads(p.read_text()); c["web"]["port"] = 8090
p.write_text(json.dumps(c, indent=2))
EOF
systemctl --user restart pikrellcam-lite.service
```

The service hot-reloads the configuration file (scheduled commands and region presets take effect immediately), but keys that affect the capture chain (resolution, frame rate, rotation, flip, capture path, device) only take effect after a service restart.

---

## 10. API Reference

There are **54 HTTP endpoints** in total: 49 `/api/*` endpoints plus 5 page and static-file routes. Once password protection is enabled, every `/api/` endpoint except `/api/auth`, `/api/auth/login`, and `/login` returns `401` when unauthenticated.

### 10.1 Read-Only Endpoints

| Method | Path | Returns | Purpose |
| --- | --- | --- | --- |
| GET | `/api/auth` | `{required, authenticated}` | Whether a password is required and whether you are logged in. |
| GET | `/api/state` | state object | Runtime state, detection result, media statistics, current version, camera info, release info. |
| GET | `/api/config` | configuration object | The full merged configuration, as in `config.json`. |
| GET | `/api/cameras` | `{cameras, current, format, active}` | All available cameras (CSI and USB) plus the current selection. |
| GET | `/api/regions` | `{regions, presets}` | Motion regions and region presets. |
| GET | `/api/algorithms` | algorithms object | The `far` and `near` algorithm parameters. |
| GET | `/api/presets` | `{presets}` | All configuration presets. |
| GET | `/api/timelapse` | status object | Timelapse state (`running`/`hold`/`period`/`index`/`session`). |
| GET | `/api/events` | array of events | The event index. |
| GET | `/api/videos` | array of files | Video file list, newest first. |
| GET | `/api/stills` | array of files | Snapshot file list, newest first. |
| GET | `/api/schedules` | array of entries | Scheduled commands from the configuration plus `at-commands.conf`. |
| GET | `/api/servo` | status object | Servo backend, current position, pins, and limits. |
| GET | `/api/hooks` | `{hooks, history}` | Hook configuration and recent execution history. |
| GET | `/api/log` | `{lines}` | The last 300 lines of the log file. |
| GET | `/api/help` | `{sections}` | Built-in help text. |
| GET | `/api/release` | `{version, release, current, releases, root}` | The running version and all retained historical versions. |
| GET | `/api/system` | status object | Model, system version, Python version, directories, hostname, uptime. |
| GET | `/api/i18n` | `{language, available, strings}` | Current language, all available languages, and the string dictionary. |
| GET | `/snapshot.jpg` | JPEG | The most recent frame as a still image. |
| GET | `/video_feed` | multipart stream | The MJPEG live preview stream. |

### 10.2 Write Endpoints

| Method | Path | Request body | Purpose |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | `{"password": "..."}` | Log in and mark the session as authenticated. |
| POST | `/api/auth/logout` | none | Log out. |
| POST | `/api/password` | `{"password": "..."}` | Set a new password; an empty string disables password protection. |
| POST | `/api/config` | configuration fragment | Update the configuration. Accepts **only** the eight top-level sections `camera`, `motion`, `record`, `timelapse`, `web`, `media`, `servo`, and `hooks`; `web.password_hash` is ignored. Changes to capture-related keys rebuild the pipeline. |
| POST | `/api/config/reset` | none | Restore the default configuration and restart capture. |
| POST | `/api/cameras/select` | `{"device": "/dev/video0", "format": "MJPEG"}` | Switch camera and capture path immediately. `format` accepts `AUTO` / `MJPEG` / `RGB888` / `XBGR8888` / `YUYV` / `YUV420`. |
| POST | `/api/service` | `{"action": "start"\|"stop"\|"restart"}` | Start, stop, or restart the service. |
| POST | `/api/motion` | `{"enabled": true}` | Turn motion detection on or off. |
| POST | `/api/regions` | `{"regions": [...]}` | Save the region array, up to 32 entries; coordinates are clamped to 0–1. |
| POST | `/api/regions/preset` | `{"name": "...", "regions": [...]}` | Save a named region preset. |
| POST | `/api/regions/preset/activate` | `{"name": "..."}` | Load a named region preset. |
| DELETE | `/api/regions/preset/<name>` | none | Delete a named region preset. |
| POST | `/api/algorithms` | `{"far": {...}, "near": {...}}` | Update algorithm parameters: `enabled`, `magnitude_limit`, `count_limit`, `consecutive_frames`, `noise_filter`. |
| POST | `/api/presets` | `{"name": "...", "config": {...}}` | Save a configuration preset. |
| POST | `/api/presets/activate` | `{"name": "..."}` | Activate a configuration preset. |
| DELETE | `/api/presets/<name>` | none | Delete a configuration preset. |
| POST | `/api/record` | `{"action": "on"\|"off"\|"resume"\|"pause"}` | Turn recording on or off. |
| POST | `/api/still` | none | Capture the current frame into `media/stills/`. |
| POST | `/api/timelapse` | `{"action": "start"\|"hold"\|"end", "period": 30, "on": true}` | Control the timelapse. |
| POST | `/api/schedules` | `{"days": "*", "time": "08:00", "interval_minutes": 0, "command": "record on", "enabled": true}` | Add or update a scheduled command. Including `index` or `uid` updates an existing entry; otherwise a new one is added. |
| DELETE | `/api/schedules/<index>` | none | Delete a scheduled command. The path parameter accepts a **numeric index only** — the internal handler also understands a `uid`, but the HTTP route is declared as `<int:index>`, so a non-numeric value returns 404. |
| POST | `/api/schedules/reload` | none | Reload the scheduled command table. |
| POST | `/api/command` | `{"command": "record on"}` | Execute an internal command immediately (an unrecognized command returns `unknown command: …`). |
| POST | `/api/servo` | `{"action": "enable"\|"disable"\|"goto"\|"set"\|"save_position"\|"delete_position", ...}` | Control the servo. |
| POST | `/api/hooks` | `{"on_motion_begin": "...", ...}` | Update the hook commands. |
| POST | `/api/i18n` | `{"language": "en-US"}` | Switch the interface language and persist it to `config.json`. |
| POST | `/api/upgrade` | none | Run `git pull --ff-only` and restart the service. Returns an error if the deployment directory is not a git repository. |

### 10.3 Media Endpoints

| Method | Path | Request body | Purpose |
| --- | --- | --- | --- |
| GET | `/media/<kind>/<name>` | none | Download a media file; `<kind>` is `videos`, `stills`, or `timelapse`. |
| DELETE | `/api/events/<eid>` | none | Delete an event along with its recording and thumbnails. |
| POST | `/api/purge` | `{"what": "all"\|"videos"\|"stills"}` | Bulk-delete media files; returns the number removed. |
| POST | `/api/archive` | `{"id": "20261111_203015"}` | `scp` the event recording to `media.archive_target`. |

### 10.4 Page Routes

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | The main management interface. |
| GET | `/login` | The login page. |

### 10.5 Example Calls

```bash
# Check the state
curl -s http://pi.local:8080/api/state | python3 -m json.tool

# Read the current configuration
curl -s http://pi.local:8080/api/config | python3 -m json.tool

# Tune the far algorithm
curl -X POST http://pi.local:8080/api/algorithms \
  -H 'Content-Type: application/json' \
  -d '{"far": {"enabled": true, "magnitude_limit": 10, "count_limit": 0.004, "consecutive_frames": 2, "noise_filter": 2}}'

# Set the pre-roll and post-roll durations
curl -X POST http://pi.local:8080/api/config \
  -H 'Content-Type: application/json' \
  -d '{"record": {"pre_seconds": 10, "post_seconds": 15}}'

# List the most recent recordings
curl -s http://pi.local:8080/api/videos | python3 -m json.tool
```

---

## 11. Multiple Languages

As of v2.5.0 the interface supports Simplified Chinese and English, and you can switch at any time.

### 11.1 Switching Languages

**Method 1: the language dropdown in the top bar.** The change takes effect immediately, **with no service restart**.

**Method 2: edit the configuration file.** Edit `~/pikrellcam-lite/config.json`:

```json
{
  "web": {
    "language": "en-US"
  }
}
```

| Value | Meaning |
| --- | --- |
| `auto` | **The default.** The language is chosen from the browser's `Accept-Language` request header: a browser that prefers English gets English, and everything else gets Simplified Chinese. |
| `zh-CN` | Always Simplified Chinese. |
| `en-US` | Always English. |

**Method 3: call the API**:

```bash
# Read the current language and string dictionary
curl -s http://pi.local:8080/api/i18n | python3 -m json.tool

# Switch to English (persisted to config.json)
curl -X POST http://pi.local:8080/api/i18n \
  -H 'Content-Type: application/json' \
  -d '{"language": "en-US"}'

# Go back to automatic selection
curl -X POST http://pi.local:8080/api/i18n \
  -H 'Content-Type: application/json' \
  -d '{"language": "auto"}'
```

The response to `POST /api/i18n` contains `language`, `available`, and `strings`. Passing an unregistered language code returns `400` with an error message; passing `auto` re-resolves the language against the current request's `Accept-Language` header.

### 11.2 Language Pack Files

Language packs live in the `core/locales/` directory as flat JSON dictionaries:

```
core/locales/zh-CN.json
core/locales/en-US.json
```

The structure looks like this:

```json
{
  "app.title": "pikrellcam-lite",
  "tab.preview": "实时预览"
}
```

The same pack is shared by the front end and the back end: the back end uses it to translate the messages it generates, and the front end fetches the whole pack through `GET /api/i18n` and substitutes the keys in the browser. Missing keys are filled in automatically from the fallback language (Simplified Chinese), so nothing ever renders blank.

### 11.3 Adding a New Language

1. Copy `core/locales/zh-CN.json` to a new language code, for example `ja-JP.json`, and translate the strings.
2. Register it in the `LANGUAGES` dictionary in `core/i18n.py`:

```python
LANGUAGES: dict[str, dict[str, str]] = {
    "zh-CN": {"name": "Chinese (Simplified)", "native": "简体中文"},
    "en-US": {"name": "English", "native": "English"},
    "ja-JP": {"name": "Japanese", "native": "日本語"},
}
```

3. Restart the service. The new language appears in the top-bar dropdown automatically, and you can also switch to it directly with `{"language": "ja-JP"}`.

> Matching is lenient: `ja`, `ja-jp`, and `ja_JP` all resolve to `ja-JP`, and `zh`, `zh-cn`, and `zh-hans` all resolve to `zh-CN`.

---

## 12. Version Management and Rollback

### 12.1 Directory Layout

```
~/pikrellcam-lite/
├── current -> releases/20261110-2328-v2.4.0   # symlink to the running version
├── releases/                                   # every historical version, each complete and independent
│   ├── 20261110-2327-v2.4.0/
│   └── 20261110-2328-v2.4.0/
├── media/                                       # recordings / snapshots / event index (shared)
│   ├── videos/
│   ├── stills/
│   ├── timelapse/
│   └── events.json
├── logs/                                        # runtime logs (shared)
├── venv/                                        # Python virtual environment (shared)
└── config.json                                  # configuration (shared)
```

**The boundary between version directories and shared data**:

- **Inside the version directory**: source code, `templates/`, `static/`, `core/` (including language packs and the compiled C kernel), and the per-version scripts.
- **In the shared root**: `media/`, `logs/`, `venv/`, and `config.json`.

Upgrading and rolling back therefore **never lose recordings and never lose settings**, and each version does not write its own copy of the data.

### 12.2 Publishing a New Version

Run this on your **development machine** (`PKC_HOST` and `PKC_KEY` can be overridden with environment variables):

```bash
# Publish the current working directory
bash deploy.sh

# List all versions retained on the remote host plus the running version
bash deploy.sh --list

# Roll back to a historical version (matches the newest directory with that version number)
bash deploy.sh --rollback v2.4.0
```

The default target is `pi@pi.local` with the key `~/.ssh/id_ed25519_pi_mcode`:

```bash
PKC_HOST=pi@pi.local PKC_KEY=~/.ssh/id_ed25519_pi_mcode bash deploy.sh
```

What `deploy.sh` does:

1. Packs the current directory (excluding `versions/`, `__pycache__`, `*.pyc`, and `deploy.sh`).
2. Uploads it over ssh with tar into `~/pikrellcam-lite/releases/<timestamp>-v<version>/`.
3. Points the `current` symlink at the new directory, runs `daemon-reload`, and restarts the service.
4. Compiles the native acceleration kernel on the remote host; if that fails, it falls back to the pure Python implementation automatically.
5. Prints the current version and the service status.

**Nothing is ever overwritten**: release directory names are precise to the minute, and republishing within the same minute automatically appends `-r2` or `-r3` so that historical versions stay intact.

### 12.3 Manual Rollback

```bash
# Run this on the Raspberry Pi
ln -sfn releases/20261110-2327-v2.4.0 ~/pikrellcam-lite/current
systemctl --user restart pikrellcam-lite.service
```

### 12.4 Checking Version Information

- Web interface: the **System** tab → **Version and Release**.
- API: `GET /api/release` returns `{version, release, current, releases, root}`.
- Command line: `bash deploy.sh --list`.

### 12.5 First-Time Install versus Versioned Publishing

- **First-time install**: copy the source to the Raspberry Pi and run `bash ~/pikrellcam-lite/install.sh`. The script performs the installation and publishes the first version at the same time.
- **Later upgrades**: always publish with `deploy.sh`. Editing code directly on the Raspberry Pi means the next publish will overwrite it.

---

## 13. Packaging and Release

As of v2.5.0 the repository ships a packaging script that produces the complete archive needed for a GitHub Release.

### 13.1 Generate the Archive

Run this in the project root:

```bash
bash package.sh
```

The generated archive contains:

| Content | Description |
| --- | --- |
| All source code | `core/`, `templates/`, `static/`, `krellcam.py` |
| The C kernel source | `core/_pkc_native.c` (without the compiled `.so`, which each target machine builds for itself) |
| Front-end assets | `static/app.js`, `static/style.css`, `templates/index.html`, `templates/login.html` |
| Bilingual documentation | `docs/使用文档.md`, `docs/USAGE.en.md`, `README.md` |
| License and changelog | `LICENSE`, `CHANGELOG.md` |
| Checksum | A SHA-256 checksum file for the archive, so downloads can be verified for integrity |

### 13.2 Publish to a GitHub Release

```bash
# 1. Tag and push
git tag -a v2.5.0 -m "pikrellcam-lite v2.5.0"
git push origin v2.5.0

# 2. Build the release archive
bash package.sh

# 3. Upload (replace the file names with the ones the script actually produced)
gh release create v2.5.0 ./dist/pikrellcam-lite-v2.5.0.tar.gz \
  ./dist/pikrellcam-lite-v2.5.0.tar.gz.sha256 \
  --title "pikrellcam-lite v2.5.0" \
  --notes "Bilingual interface (Chinese/English), packaging script, detection and recording stability improvements"
```

### 13.3 How Users Install a Release

After publishing to GitHub, users download the archive, extract it, and follow [Section 3](#3-installation):

```bash
# On the Raspberry Pi
tar xzf pikrellcam-lite-v2.5.0.tar.gz
cd pikrellcam-lite
bash install.sh
```

---

## 14. Native Acceleration

### 14.1 What It Is

pikrellcam-lite moves the three most expensive stages of the frame-processing chain out of Python/numpy and into C:

| Kernel function | Purpose |
| --- | --- |
| `pkc_gray_ds()` | RGB888 to a downsampled grayscale image |
| `pkc_detect()` | The full frame-differencing detection pipeline (both algorithms, density filtering, region ratios, bounding boxes) |
| `pkc_jpeg()` | RGB888 to JPEG (libjpeg-turbo) |

The source lives in `core/_pkc_native.c` and compiles to `core/_libpkc.so`, which `core/native.py` loads through ctypes.

**Acceleration is optional**: if the compiled library is missing, fails to load, or is incompatible with the platform, the service automatically falls back to the pure Python + numpy implementation, with **identical functionality and only lower speed**.

### 14.2 Compiling

```bash
# Compile in a version directory (the output goes to core/_libpkc.so)
bash build_native.sh

# Force a rebuild
bash build_native.sh --force
```

You need `gcc` and `libjpeg62-turbo-dev` (the script installs the latter automatically if it is missing). On aarch64 the NEON instruction set is enabled explicitly.

Both `install.sh` and `deploy.sh` run this step for you.

### 14.3 Checking the Active Backend

```bash
# Method 1: look at the log
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -n 50 | grep -i native

# Method 2: ask Python directly
cd ~/pikrellcam-lite/current
~/pikrellcam-lite/venv/bin/python -c "import sys;sys.path.insert(0,'.');from core import native;print(native.backend())"
```

`native` means the C kernel is in use; `python` means the service is running in fallback mode. The log also contains `native acceleration enabled (...)` or `native acceleration unavailable, falling back to pure python`.

### 14.4 Turning Native Acceleration Off

To disable acceleration temporarily for comparison or troubleshooting, set the `PKC_NO_NATIVE=1` environment variable:

```bash
# Affects this run only
PKC_NO_NATIVE=1 ~/pikrellcam-lite/venv/bin/python ~/pikrellcam-lite/current/krellcam.py

# Or write it into the systemd service
systemctl --user edit pikrellcam-lite.service
```

Add this to the editor:

```ini
[Service]
Environment=PKC_NO_NATIVE=1
```

Then:

```bash
systemctl --user daemon-reload
systemctl --user restart pikrellcam-lite.service
```

To restore it, remove that block and run `daemon-reload` plus `restart` again.

### 14.5 Performance Reference

Raspberry Pi 4, 1280x720, detection resolution 320x180:

| Stage | Pure Python | Native C | Speedup |
| --- | --- | --- | --- |
| Grayscale downsampling | 35.77 ms | 0.85 ms | 42.1x |
| Dual-algorithm motion detection | 22.76 ms | 2.26 ms | 10.1x |
| JPEG encoding | 18.62 ms | 13.29 ms | 1.4x |
| **Full per-frame chain** | **77.16 ms** | **16.40 ms** | **4.71x** |

The C kernel was compared bit for bit against the pure Python implementation: frame-difference ratios, bounding boxes, and consecutive-hit counts are identical; JPEG output has the same byte length and a PSNR above 138 dB (visually equivalent).

> Note: on the **ISP hardware JPEG** path, JPEG encoding never happens on the CPU at all (`jpeg_ms = 0.0`), and the C kernel only handles grayscale downsampling and detection.

---

## 15. Troubleshooting

### 15.1 Black Screen

1. **Confirm the camera is detected**: `libcamera-hello --list-cameras` (CSI) or `v4l2-ctl --list-devices` (USB).
2. **Confirm the right device is selected**: the **System** tab → **Camera**, and check the backend and format shown in the camera details.
3. **Try the other capture path**: switch between ISP hardware JPEG and raw RGB to see which one produces an image.
4. **Read the log**: `journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f`, and search for `error`.
5. **Camera frontend timeout** (the log shows `Camera frontend has timed out!`): the sensor is hung and **must be reset by cutting power** — unplug the power for 10 seconds and plug it back in. A Raspberry Pi `reboot` does not cut the 3.3V rail, so rebooting does not help.

### 15.2 Picture Frozen

1. **Wait a moment**: the service includes a frame-fetch watchdog (rebuilds the pipeline after 8 seconds without a new frame by default) plus automatic degradation, so it usually recovers on its own within seconds.
2. **Look for degradation messages in the log**: "连续 N 次取帧失败，降级分辨率至 …", "降级帧率至 …", and "回退到 RGB888 采集通路".
3. **Reset manually**: under **System** → **Camera**, click "Switch" to rebuild the pipeline, or click "Restart Service".
4. **Make sure nothing else holds the camera**: `ps aux | grep -E 'rpicam|libcamera|ffmpeg'`.

### 15.3 Picture Looks Purple or Otherwise Off-Color

1. **Re-seat the ribbon with the power off**: a loose or reversed ribbon shifts the color channels. Always power down first.
2. **Compare capture paths**: the ISP hardware JPEG and raw RGB paths differ in how the ISP processes the image, which quickly tells you whether the problem is path-specific.
3. **Check the camera module**: non-official or clone modules often lack correct ISP tuning, and the colors are noticeably off.
4. **Reduce the impact of compression**: raising `camera.jpeg_quality` to 85 or above reduces the color banding caused by compression.

### 15.4 No Recordings Are Being Produced

Check in this order:

1. **Is recording paused?** Look at the "Pause Recording" button on the Live Preview tab, and at the `record.paused` configuration key.
2. **Is detection enabled?** **Detection Tuning** → "Enable Motion Detection", and the `motion.enabled` key.
3. **Is the event gap too long?** `record.event_gap_seconds` defaults to 10 seconds, and motion arriving sooner than that after the previous event is swallowed.
4. **Is the disk full?** Check the "Disk" indicator in the top bar or run `du -sh ~/pikrellcam-lite/media`; files beyond `max_disk_gb` are deleted automatically.
5. **Is ffmpeg available?** Run `which ffmpeg`; without it the service cannot encode.
6. **Read the log**: `journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f | grep -i "ffmpeg\|event"`.
7. **Confirm events are actually triggering**: the bottom-left OSD on the Live Preview tab shows the matched algorithm, region, and change ratio.

### 15.5 The Port Is Already in Use

```bash
# See who holds port 8080
sudo lsof -i :8080
# or
ss -ltnp | grep 8080
```

Two ways forward:

- Stop the process that holds the port.
- Change the port: edit `web.port` in `~/pikrellcam-lite/config.json`, then run `systemctl --user restart pikrellcam-lite.service`.

### 15.6 The Camera Is in Use by Another Process

The log shows `Pipeline handler in use by another process`, meaning another process holds the camera:

```bash
# Find the process holding it
ps aux | grep -E 'rpicam-vid|libcamera|camera-app' | grep -v grep

# End it
pkill -f rpicam-vid
```

Common culprits: the official camera application, a manual `rpicam-vid` test, or a second pikrellcam-lite instance.

### 15.7 Permission Problems

| Symptom | Fix |
| --- | --- |
| `sudo loginctl enable-linger` fails | Without sudo you may need to run it manually; otherwise the service will not start at boot. |
| Cannot write to the media directory | Check that the directory `media.dir` points to is writable by the user running the service; for USB disks run `sudo chown -R $USER:$USER /mnt/usb`. |
| `~/.pikrellcam` permissions are too open | Run `chmod 700 ~/.pikrellcam` (the install script does this automatically). |
| The servo does not move | Confirm the servo is enabled and that the GPIO pins are not used by anything else; on Pi 5 the `servoblaster` or `lgpio` backend is preferable. |

### 15.8 Forgotten Password

The password hash lives in `web.password_hash` in `config.json`. Clearing it disables password protection:

```bash
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home()/"pikrellcam-lite/config.json"
c = json.loads(p.read_text()); c["web"]["password_hash"] = ""
p.write_text(json.dumps(c, indent=2))
EOF
systemctl --user restart pikrellcam-lite.service
```

### 15.9 Reading the Logs

```bash
# systemd live log (recommended)
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f

# File log (rotated automatically, 3 copies of up to 2 MB each)
tail -f ~/pikrellcam-lite/logs/pikrellcam.log

# Service status
systemctl --user status pikrellcam-lite.service

# Restart the service
systemctl --user restart pikrellcam-lite.service
```

> On some systems `journalctl --user` is unavailable; use `journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service` instead.
> The **System** tab → **Live Log** panel shows the same content, refreshed every second.

### 15.10 Other Common Symptoms

| Symptom | Explanation and fix |
| --- | --- |
| Constant false positives | A camera pointed at a monitor treats changing screen content as motion; raise `count_limit` and `magnitude_limit`, or shrink the detection region. |
| Constant triggers when the lights are switched | Frame differencing is sensitive to sudden lighting changes; raise the thresholds or increase `noise_filter`. |
| Choppy preview, high latency | Lower `camera.fps`. A USB camera that only supports YUYV is transcoded in software, which costs more CPU. |
| The USB camera is not listed | The libcamera stack in Debian 13 cannot enumerate USB devices; use the V4L2 backend and select `/dev/videoN` under "System → Camera". |
| The upgrade button reports an error | The deployment directory is not a git repository and cannot be upgraded online; publish with `deploy.sh` instead. |

---

## 16. Security Recommendations

1. **Always set an access password.** After installing, set one under **System** → **Upgrade and Password**. The default configuration has **no** password protection.
2. **Do not expose port 8080 directly to the public internet.** The service uses Flask's built-in server, with no TLS, no request rate limiting, and no CSRF protection.
3. **If you need internet access, put a reverse proxy in front of it**: use Nginx or Caddy to terminate HTTPS, restrict source IPs, and add basic authentication.
4. **Changing the default port is not a security measure.** It only reduces scan hits; pair it with the access controls above.
5. **Mind the other devices on your LAN.** Any device on the same subnet can reach the console and change the configuration.
6. **Passwords are stored hashed** (`sha256:<hex>`), but the configuration file itself is readable in plaintext, so **do not put `config.json` into a public backup or code repository**.
7. **Event hooks can run arbitrary shell commands**, and `/api/upgrade` runs `git pull` in the deployment directory. Once password protection is on, use a strong password and review the hook configuration regularly.
8. **Lock down `~/.pikrellcam`**: `chmod 700 ~/.pikrellcam`, since it holds the FIFO and the command configuration file.
9. **Keep the software current.** Publish new versions with `bash deploy.sh`. Old version directories stay in `releases/`, so once you are satisfied that a new version is stable, you can delete the directories you no longer need to reclaim space.
10. **Use a least-privilege account for remote archiving.** The SSH account behind `media.archive_target` only needs write access to the destination directory.

---

## Appendix: Command Cheat Sheet

```bash
# Service
systemctl --user status  pikrellcam-lite.service
systemctl --user restart pikrellcam-lite.service
systemctl --user stop     pikrellcam-lite.service

# Logs
journalctl _SYSTEMD_USER_UNIT=pikrellcam-lite.service -f
tail -f ~/pikrellcam-lite/logs/pikrellcam.log

# Directories
ls -1 ~/pikrellcam-lite/releases        # all retained versions
readlink ~/pikrellcam-lite/current      # the running version
du -sh ~/pikrellcam-lite/media          # media disk usage

# Cameras
libcamera-hello --list-cameras
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
ps aux | grep -E 'rpicam-vid|libcamera' | grep -v grep

# Version management (run on the development machine)
bash deploy.sh
bash deploy.sh --list
bash deploy.sh --rollback v2.4.0

# Packaging
bash package.sh
```
