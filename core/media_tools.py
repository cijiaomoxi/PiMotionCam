"""Persistent media names, verified calendar archives and thumbnail repair."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path


def next_name(config, kind, suffix):
    root = config.path.parent
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ".media-sequence", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            seq = int(fh.read() or 0) + 1
        except ValueError:
            seq = 1
        fh.seek(0)
        fh.truncate()
        fh.write(str(seq))
        fh.flush()
        os.fsync(fh.fileno())
    template = config.get(
        "record", "name_template", default="{kind}_{date}_{time}_{seq:06d}"
    )
    now = datetime.now()
    try:
        name = template.format(
            kind=kind,
            date=now.strftime("%Y%m%d"),
            time=now.strftime("%H%M%S"),
            seq=seq,
            hostname=socket.gethostname(),
        )
    except (ValueError, KeyError, AttributeError, IndexError):
        raise ValueError("Invalid media name template") from None
    if not re.fullmatch(r"[\w.-]{1,160}", name) or name in (".", ".."):
        raise ValueError(
            "Media names must be plain file names (letters, numbers, _, - or .)"
        )
    return name + suffix


def safe_path(root, name):
    root = Path(root).resolve()
    path = (root / str(name)).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path is outside the media directory")
    return path


def _digest(path):
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def verified_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _digest(source) != _digest(target):
            raise FileExistsError("A different file already exists in the archive")
        return
    fd, tmp = tempfile.mkstemp(prefix=".copy-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as out, open(source, "rb") as inp:
            shutil.copyfileobj(inp, out, 1 << 20)
            out.flush()
            os.fsync(out.fileno())
        if _digest(source) != _digest(tmp):
            raise OSError("Archive verification failed")
        # link publishes atomically without replacing a concurrent archive.
        os.link(tmp, target)
    finally:
        Path(tmp).unlink(missing_ok=True)


def archive_event(config, entry, target=None):
    target = str(target or config.get("media", "archive_target", default="")).strip()
    if not target:
        raise ValueError("Configure an archive target first")
    source = safe_path(config.media_sub("videos"), entry["video"])
    if not source.is_file():
        raise FileNotFoundError("Recording not found")
    if ":" in target and not target.startswith("/"):
        # Retain the existing SSH archive option without interpolating a shell.
        if not re.fullmatch(r"[\w.@-]+:/[\w/ .-]+", target):
            raise ValueError("Invalid SSH archive destination")
        result = subprocess.run(
            ["scp", "-q", "-oBatchMode=yes", "--", str(source), target],
            capture_output=True,
            timeout=600,
        )
        if result.returncode:
            raise OSError(result.stderr.decode("utf-8", "replace")[-400:])
        return {"target": target, "verified": False, "mode": "ssh"}
    root = Path(target).expanduser().absolute()
    if not root.is_absolute() or str(root) == "/":
        raise ValueError("Choose a dedicated archive directory")
    if config.get(
        "media", "archive_require_mount", default=False
    ) and not os.path.ismount(root):
        raise OSError("The archive mount is unavailable")
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    reserve = (
        float(config.get("media", "archive_min_free_percent", default=5))
        / 100
        * usage.total
    )
    files = [(source, "videos")]
    for key in ("thumb", "thumb_object"):
        name = entry.get(key)
        if name:
            p = safe_path(config.media_sub("stills"), name)
            if p.is_file():
                files.append((p, "stills"))
    if usage.free - sum(p.stat().st_size for p, _ in files) < reserve:
        raise OSError("Insufficient free archive space")
    date = datetime.fromtimestamp(entry["start"]).strftime("%Y/%m/%d")
    folder = root / date
    for p, kind in files:
        verified_copy(p, folder / kind / p.name)
    meta = folder / "events" / (entry["id"] + ".json")
    meta.parent.mkdir(parents=True, exist_ok=True)
    # Publish metadata last: the calendar lists only complete verified copies.
    temp = meta.with_suffix(".tmp")
    temp.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
    temp.replace(meta)
    return {"target": str(folder), "verified": True, "mode": "calendar"}


def archive_calendar(config, day=None):
    target = str(config.get("media", "archive_target", default=""))
    if not target or ":" in target:
        return []
    root = Path(target).expanduser()
    if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Invalid archive date")
    pattern = day.replace("-", "/") + "/events/*.json" if day else "*/*/*/events/*.json"
    entries = []
    for path in sorted(root.glob(pattern), reverse=True)[:5000]:
        try:
            value = json.loads(path.read_text())
            value["archive_day"] = "-".join(path.relative_to(root).parts[:3])
            entries.append(value)
        except (OSError, ValueError):
            continue
    return entries


def repair_thumbnails(config, events):
    repaired, failed = [], []
    for entry in events[:500]:
        src = safe_path(config.media_sub("videos"), entry["video"])
        name = entry.get("thumb") or entry["id"] + ".jpg"
        out = safe_path(config.media_sub("stills"), name)
        if out.exists() or not src.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".repair.jpg")
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-frames:v",
                "1",
                "-vf",
                "scale=320:180:force_original_aspect_ratio=decrease",
                str(tmp),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode == 0 and tmp.exists():
            tmp.replace(out)
            repaired.append(entry["id"])
        else:
            tmp.unlink(missing_ok=True)
            failed.append(entry["id"])
    return {"repaired": repaired, "failed": failed}
