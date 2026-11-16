"""Additional v2.8.2 controls; all routes use the main application's auth guard."""

from __future__ import annotations
import json
import re
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file
from .config import DEFAULT_CONFIG
from .media_stats import list_media
from .media_tools import archive_calendar, archive_event, repair_thumbnails, safe_path
from .solar import solar_times
from .video_processing import EFFECTS


def validate_patch(patch, config):
    if not isinstance(patch, dict):
        raise ValueError("Settings must be an object")

    def visit(value, reference, path=""):
        if isinstance(reference, dict):
            if not isinstance(value, dict):
                raise ValueError(path + " must be an object")
            for key, item in value.items():
                if key in reference:
                    visit(item, reference[key], path + "." + key)
        elif isinstance(reference, bool):
            if not isinstance(value, bool):
                raise ValueError(path + " must be true or false")
        elif isinstance(reference, (float, int)):
            import math

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(path + " must be a finite number")
        elif isinstance(reference, list):
            if not isinstance(value, list):
                raise ValueError(path + " must be a list")
        elif isinstance(reference, str):
            if not isinstance(value, str) or len(value) > 8192:
                raise ValueError(path + " must be text")

    visit(patch, DEFAULT_CONFIG)
    camera = patch.get("camera", {})
    if "rotation" in camera and camera["rotation"] not in (0, 90, 180, 270):
        raise ValueError("Invalid rotation")
    if "flip" in camera and camera["flip"] not in (
        "none",
        "horizontal",
        "vertical",
        "both",
    ):
        raise ValueError("Invalid mirror mode")
    processing = camera.get("processing", {})
    if processing.get("effect", "none") not in EFFECTS:
        raise ValueError("Unknown image effect")
    if "crop" in processing:
        try:
            x, y, w, h = map(float, processing["crop"])
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Invalid normalized crop") from None
    for key in ("resolution", "detect_resolution", "stills_resolution"):
        size = camera.get(key)
        if size is not None and (
            not isinstance(size, list)
            or len(size) != 2
            or any(
                isinstance(v, bool) or not isinstance(v, int) or v < 16 or v > 12000
                for v in size
            )
            or size[0] * size[1] > 60_000_000
        ):
            raise ValueError("Invalid " + key)
    record = patch.get("record", {})
    if "name_template" in record:
        try:
            example = record["name_template"].format(
                kind="still", date="20260101", time="120000", seq=1, hostname="pi"
            )
        except (ValueError, KeyError, AttributeError, IndexError):
            raise ValueError("Invalid media name template") from None
        if not re.fullmatch(r"[\w.-]{1,160}", example) or example in (".", ".."):
            raise ValueError("Invalid media name template")
    if "direction" in patch.get("motion", {}).get("analysis", {}) and patch["motion"][
        "analysis"
    ]["direction"] not in ("any", "left", "right", "up", "down"):
        raise ValueError("Invalid motion direction")
    location = patch.get("location", {})
    for key, limit in [("latitude", 89.9), ("longitude", 180)]:
        if (
            key in location
            and location[key] is not None
            and not -limit <= float(location[key]) <= limit
        ):
            raise ValueError("Invalid " + key)
    if location.get("timezone"):
        from zoneinfo import ZoneInfo

        ZoneInfo(location["timezone"])
    network = {**(config.get("network", default={}) or {}), **patch.get("network", {})}
    if network.get("tcp_enabled") or network.get("multicast_enabled"):
        if len(str(network.get("secret") or "")) < 16:
            raise ValueError(
                "A network shared secret of at least 16 characters is required"
            )
    for key in ("tcp_port", "multicast_port"):
        if not 0 <= int(network.get(key, 3000)) <= 65535:
            raise ValueError("Invalid network port")
    web = patch.get("web", {})
    if web.get("theme", "dark") not in ("dark", "light", "auto"):
        raise ValueError("Invalid theme")
    for link in web.get("custom_links", []):
        if not isinstance(link, dict) or not re.match(
            r"^https?://", str(link.get("url", ""))
        ):
            raise ValueError("Extension links must use http:// or https://")


def register_extensions(app, service):
    api = Blueprint("extended", __name__)
    maintenance = {"running": False, "result": None, "error": ""}
    maintenance_lock = threading.Lock()

    @api.errorhandler(ValueError)
    @api.errorhandler(TypeError)
    def bad_request(error):
        return jsonify(ok=False, error=str(error)), 400

    @api.errorhandler(KeyError)
    @api.errorhandler(FileNotFoundError)
    def missing(error):
        return jsonify(ok=False, error=str(error)), 404

    @api.errorhandler(OSError)
    @api.errorhandler(RuntimeError)
    def unavailable(error):
        return jsonify(ok=False, error=str(error)), 409

    @api.route("/api/audio/record", methods=["GET", "POST"])
    def audio_record():
        if request.method == "GET":
            return jsonify(service.audio_recorder.status())
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        if action == "start":
            return jsonify(service.audio_recorder.start(data.get("seconds", 120)))
        if action == "stop":
            return jsonify(service.audio_recorder.stop())
        raise ValueError("Unknown audio recording action")

    @api.route("/api/audio/files")
    def audio_files():
        return jsonify(list_media(service.config.media_sub("audio"), ".mp3"))

    @api.route("/api/manual", methods=["POST"])
    def manual():
        data = request.get_json(silent=True) or {}
        if data.get("action") not in ("start", "stop"):
            raise ValueError("Unknown manual recording action")
        if data["action"] == "start" and not service.state.get("camera_ready"):
            raise RuntimeError("Camera is not ready")
        return jsonify(
            service.recorder.manual(data["action"] == "start", data.get("seconds", 120))
        )

    @api.route("/api/motion/trigger", methods=["POST"])
    def trigger():
        return jsonify(
            service.recorder.trigger(
                (request.get_json(silent=True) or {}).get("seconds", 2)
            )
        )

    @api.route("/api/presets/transfer", methods=["POST"])
    def presets_transfer():
        data = request.get_json(silent=True) or {}
        result = service.presets.transfer(
            data.get("source"),
            data.get("target"),
            bool(data.get("move")),
            data.get("section"),
        )
        return jsonify(ok=True, presets=result)

    @api.route("/api/servo/step", methods=["POST"])
    def servo_step():
        data = request.get_json(silent=True) or {}
        return jsonify(
            service.servo.step(
                data.get("axis"), data.get("direction", 1), data.get("multiple", False)
            )
        )

    @api.route("/api/servo/scan", methods=["POST"])
    def servo_scan():
        return jsonify(
            service.servo.scan(
                bool((request.get_json(silent=True) or {}).get("enabled"))
            )
        )

    @api.route("/api/solar")
    def solar():
        location = service.config.get("location", default={}) or {}
        if location.get("latitude") is None or location.get("longitude") is None:
            return jsonify(configured=False, times={})
        day = datetime.strptime(
            request.args.get("date") or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d"
        ).date()
        times = solar_times(
            day,
            location["latitude"],
            location["longitude"],
            location.get("timezone", ""),
        )
        return jsonify(
            configured=True,
            date=str(day),
            times={k: v.isoformat() if v else None for k, v in times.items()},
        )

    @api.route("/api/archive/calendar")
    def calendar():
        return jsonify(archive_calendar(service.config, request.args.get("date")))

    @api.route("/api/archive/file/<day>/<kind>/<name>")
    def archive_file(day, kind, name):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or kind not in (
            "videos",
            "stills",
        ):
            raise ValueError("Invalid archive path")
        target = str(service.config.get("media", "archive_target", default=""))
        if not target or ":" in target:
            raise ValueError("A local or mounted archive is required")
        return send_file(
            safe_path(target, day.replace("-", "/") + "/" + kind + "/" + name),
            conditional=True,
        )

    @api.route("/api/maintenance/thumbnails", methods=["GET", "POST"])
    def thumbnails():
        if request.method == "POST":
            with maintenance_lock:
                if maintenance["running"]:
                    raise RuntimeError("Thumbnail repair is already running")
                maintenance.update(running=True, error="", result=None)

            def worker():
                try:
                    maintenance["result"] = repair_thumbnails(
                        service.config, service.recorder.events
                    )
                except Exception as exc:
                    maintenance["error"] = str(exc)
                finally:
                    maintenance["running"] = False

            threading.Thread(
                target=worker, name="thumbnail-repair", daemon=True
            ).start()
        return jsonify(maintenance)

    @api.route("/api/detection/log/<name>")
    def detection_log(name):
        if name not in ("motion.csv", "motion-events.jsonl"):
            raise ValueError("Unknown detection log")
        return send_file(service.config.path.parent / "logs" / name, as_attachment=True)

    @api.route("/api/camera/profile", methods=["GET", "POST"])
    def camera_profile():
        if request.method == "GET":
            response = jsonify(camera=service.config.get("camera"))
            response.headers["Content-Disposition"] = (
                'attachment; filename="pimotioncam-camera.json"'
            )
            return response
        data = request.get_json(silent=True) or {}
        patch = {"camera": data.get("camera", {})}
        validate_patch(patch, service.config)
        service.config.set(patch)
        service._restart_camera()
        return jsonify(ok=True)

    @api.route("/api/control/status")
    def control_status():
        return jsonify(
            error=service.control.error, tcp_address=service.control.tcp_address
        )

    app.register_blueprint(api)
