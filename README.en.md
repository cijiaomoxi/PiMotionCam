# PiMotionCam v2.8.2

[Bilingual home](README.md) · [简体中文](README.zh-CN.md)

PiMotionCam monitors cameras and records events on Raspberry Pi using libcamera / picamera2. It supports CSI and USB cameras with a Simplified Chinese / English web interface.

- Live preview, editable regions, dual far / near detection and software direction/vector analysis.
- Pre/post-roll, manual recording, motion photos, loop recording and full-frame/object thumbnails.
- MP4 with sound, live listening, microphone gain, sound triggers and audio-only MP3 recording.
- CSI / USB rotation and mirroring, optional crop, software effects, stabilization and burned-in captions.
- Timelapse, pan/tilt presets and patrol, preset copy/move, fixed and solar schedules.
- FIFO, event hooks, optional signed TCP / multicast control, calendar archives, external storage and disk guards.

Raspberry Pi 4B with 64-bit Raspberry Pi OS / Debian 13 is recommended. Python / Flask and optional C acceleration are retained. No OS reinstall is needed. Runtime dependencies remain distro numpy, Pillow, ffmpeg, ALSA and camera tools.

```bash
git clone https://github.com/cijiaomoxi/PiMotionCam.git
cd PiMotionCam
bash install.sh
```

Open `http://<Pi-IP>:8080`. Set an access password on the System tab if needed. Live listening is off by default: enable it on Media, save, then click Listen live.

Upgrade an existing device with `PKC_HOST=pi@<Pi-IP> bash deploy.sh`. The runtime directory remains `~/pikrellcam-lite` and the service remains `pikrellcam-lite.service`. Configuration, media and historical releases retain their paths; previous releases remain available for rollback.

See the [usage guide](docs/USAGE.en.md), [2.8.2 controls](docs/V2.8.2.md), [upstream comparison](docs/上游功能对照.md) and [validation record](docs/V2.8.2-VALIDATION.md). The validation record distinguishes implemented features from completed hardware checks.

Software analysis replaces legacy MMAL vectors. Legacy exposure modes, the complete upstream OSD menu tree and raw network wire formats are not advertised as compatible. USB rotation, crop, effects, stabilization and burned-in captions decode and re-encode frames, adding CPU load. Untransformed USB MJPEG remains passthrough.

Independently implemented under MIT, inspired by the GPL-3.0 [Bill Wilson / PiKrellCam](https://github.com/billw2/pikrellcam) project.
