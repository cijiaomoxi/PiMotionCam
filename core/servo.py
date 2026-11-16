"""舵机控制（对应官方 PiKrellCam 的内置 servo 控制）。

官方支持 Pi 硬件 PWM GPIO 或 ServoBlaster 两种方式，这里按可用性自动选择：
  1. RPi.GPIO  —— Pi 3B/4 自带 PWM，简单可靠
  2. ServoBlaster —— Pi 5 等没有 RPi.GPIO 的新板子可用
  3. 禁用      —— 没有硬件或库时优雅降级，不影响其它功能

每个舵机位置预设可以绑定一组设置预设（对应官方"每个位置预设有自己的设置预设"）。
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time

PULSE_MIN = 500      # 0 度
PULSE_MAX = 2500     # 180 度
PERIOD_US = 20000


def _angle_to_pulse(angle: float) -> int:
    angle = max(0.0, min(180.0, float(angle)))
    return int(PULSE_MIN + (PULSE_MAX - PULSE_MIN) * (angle / 180.0))


class Servo:
    def __init__(self, config, state, log=None, on_move=None, on_preset=None):
        self.config = config
        self.state = state
        self.log = log or (lambda *a, **k: None)
        self._lock = threading.Lock()
        self._backend = None
        self._pwms = {}
        self._current = {"pan": None, "tilt": None}
        self.on_move, self.on_preset = on_move, on_preset
        self._move_lock = threading.RLock()
        self._scan_stop = threading.Event()
        self._scan_thread = None
        self._chip = None

    # ------------------------------------------------------------------
    def _detect_backend(self) -> str:
        want = (self.config.get("servo", "backend", default="auto") or "auto").lower()
        if want == "none":
            return "none"
        try:
            import RPi.GPIO  # noqa: F401
            if want in ("auto", "rpi"):
                return "rpi"
        except Exception:
            pass
        if want in ("auto", "servoblaster") and shutil.which("servoblaster"):
            return "servoblaster"
        try:
            import lgpio  # noqa: F401
            if want in ("auto", "lgpio"):
                return "lgpio"
        except Exception:
            pass
        return "none"

    @property
    def backend(self) -> str:
        return self._backend or "none"

    def status(self) -> dict:
        return {
            "enabled": bool(self.state.get("servo_enabled")),
            "backend": self.backend,
            "positions": self.config.get("servo", "positions", default=[]),
            "current": dict(self._current),
            "pan_pin": self.config.get("servo", "pan_pin", default=18),
            "tilt_pin": self.config.get("servo", "tilt_pin", default=17),
            "pan_min": self.config.get("servo", "pan_min", default=0),
            "pan_max": self.config.get("servo", "pan_max", default=180),
            "tilt_min": self.config.get("servo", "tilt_min", default=0),
            "tilt_max": self.config.get("servo", "tilt_max", default=180),
            "scanning": bool(self._scan_thread and self._scan_thread.is_alive()),
        }

    # ------------------------------------------------------------------
    def enable(self) -> dict:
        with self._lock:
            if self._backend is None:
                self._backend = self._detect_backend()
            backend = self._backend
            if backend == "none":
                self.state.set("servo_enabled", False)
                return {"ok": False, "error": "没有可用的舵机后端（缺少 RPi.GPIO / ServoBlaster）"}
            if backend == "rpi":
                import RPi.GPIO as GPIO
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                for key, pin in (("pan", self.config.get("servo", "pan_pin", default=18)),
                                 ("tilt", self.config.get("servo", "tilt_pin", default=17))):
                    if key not in self._pwms:
                        GPIO.setup(pin, GPIO.OUT)
                        pwm = GPIO.PWM(pin, 50)
                        pwm.start(0)
                        self._pwms[key] = pwm
            self.state.set("servo_enabled", True)
            if backend == "lgpio" and self._chip is None:
                import lgpio
                try:
                    self._chip = lgpio.gpiochip_open(int(self.config.get("servo", "gpiochip", default=0)))
                    for axis in ("pan", "tilt"):
                        lgpio.gpio_claim_output(self._chip, int(self.config.get("servo", axis+"_pin")))
                except Exception:
                    if self._chip is not None:
                        lgpio.gpiochip_close(self._chip)
                    self._chip = None
                    self.state.set("servo_enabled", False)
                    raise
        self.log(f"servo enabled, backend={backend}")
        return {"ok": True, "backend": backend}

    def disable(self) -> dict:
        self.scan(False)
        with self._lock:
            if self._backend == "rpi" and self._pwms:
                try:
                    import RPi.GPIO as GPIO
                    for pwm in self._pwms.values():
                        pwm.stop()
                    GPIO.cleanup([self.config.get("servo", "pan_pin"), self.config.get("servo", "tilt_pin")])
                except Exception:
                    pass
            self._pwms.clear()
            if self._chip is not None:
                import lgpio
                lgpio.gpiochip_close(self._chip)
                self._chip = None
            self._backend = None
            self.state.set("servo_enabled", False)
        return {"ok": True}

    # ------------------------------------------------------------------
    def set_angle(self, pan: float | None = None, tilt: float | None = None,
                  smooth_ms: int | None = None) -> dict:
        with self._move_lock:
            return self._set_angle(pan, tilt, smooth_ms)

    def _set_angle(self, pan, tilt, smooth_ms):
        if not self.state.get("servo_enabled"):
            self.enable()
        if self.backend == "none":
            return {"ok": False, "error": "舵机后端不可用"}

        pan_min = float(self.config.get("servo", "pan_min", default=0))
        pan_max = float(self.config.get("servo", "pan_max", default=180))
        tilt_min = float(self.config.get("servo", "tilt_min", default=0))
        tilt_max = float(self.config.get("servo", "tilt_max", default=180))

        target = {}
        if self.on_move:
            self.on_move(float(self.config.get("motion", "settle_seconds", default=1)) +
                         max(0, int(smooth_ms or self.config.get("servo", "smooth_ms", default=0)))/1000)
        if pan is not None:
            target["pan"] = max(pan_min, min(pan_max, float(pan)))
        if tilt is not None:
            target["tilt"] = max(tilt_min, min(tilt_max, float(tilt)))

        smooth = max(0, min(5000, int(smooth_ms if smooth_ms is not None else self.config.get("servo", "smooth_ms", default=0) or 0)))
        if smooth > 0 and self._current.get("pan") is not None:
            self._smooth_move(target, smooth)
        else:
            for key, angle in target.items():
                self._write(key, angle)
        with self._lock:
            self._current.update(target)
        self.state.set("servo_position", dict(self._current))
        return {"ok": True, "current": dict(self._current)}

    def _smooth_move(self, target: dict, duration_ms: int):
        steps = max(1, duration_ms // 20)
        for step in range(1, steps + 1):
            frac = step / steps
            for key, angle in target.items():
                start = self._current.get(key)
                if start is None:
                    continue
                self._write(key, start + (angle - start) * frac)
            time.sleep(0.02)

    def _write(self, key: str, angle: float):
        if self.config.get("servo", key+"_invert", default=False):
            angle = 180-angle
        pulse = _angle_to_pulse(angle)
        if self.backend == "rpi":
            pwm = self._pwms.get(key)
            if pwm:
                pwm.ChangeDutyCycle(pulse * 100.0 / PERIOD_US)
        elif self.backend == "servoblaster":
            pin = self.config.get("servo", f"{key}_pin", default=18 if key == "pan" else 17)
            try:
                with open("/dev/servoblaster", "w") as fh:
                    fh.write(f"{pin}={pulse}\n")
            except Exception as exc:
                raise OSError("ServoBlaster output failed") from exc
        elif self.backend == "lgpio":
            import lgpio
            lgpio.tx_servo(self._chip, int(self.config.get("servo", key+"_pin")), pulse, 50)

    # ------------------------------------------------------------------
    def goto(self, name: str) -> dict:
        positions = self.config.get("servo", "positions", default=[]) or []
        for p in positions:
            if p.get("name") == name:
                result = self.set_angle(p.get("pan"), p.get("tilt"))
                if result.get("ok") and p.get("preset") and self.on_preset:
                    self.on_preset(p["preset"])
                return result
        return {"ok": False, "error": f"没有名为 {name} 的位置预设"}

    def step(self, axis, direction=1, multiple=False):
        if axis not in ("pan", "tilt"):
            raise ValueError("Unknown servo axis")
        amount = float(self.config.get("servo", "step_degrees", default=2))
        if multiple:
            amount *= max(1, min(50, int(self.config.get("servo", "multi_steps", default=5))))
        current = self._current.get(axis)
        return self.set_angle(**{axis: (90 if current is None else current) + amount*(1 if float(direction)>0 else -1)})

    def scan(self, enabled=True):
        self._scan_stop.set()
        if self._scan_thread and self._scan_thread is not threading.current_thread():
            self._scan_thread.join(timeout=6)
        if not enabled:
            return {"ok": True, "scanning": False}
        if not (self.config.get("servo", "positions", default=[]) or []):
            raise ValueError("No servo positions are configured")
        self._scan_stop.clear()
        def worker():
            while not self._scan_stop.is_set():
                positions = self.config.get("servo", "positions", default=[]) or []
                if not positions:
                    return
                for position in positions:
                    if self._scan_stop.is_set():
                        return
                    try:
                        if not self.goto(position["name"]).get("ok"):
                            return
                    except Exception as exc:
                        self.log("servo scan: %s" % exc)
                        return
                    self._scan_stop.wait(max(1, float(self.config.get("servo", "scan_seconds", default=10))))
        self._scan_thread = threading.Thread(target=worker, name="servo-scan", daemon=True)
        self._scan_thread.start()
        return {"ok": True, "scanning": True}

    def save_position(self, name: str, pan: float, tilt: float, preset: str = "") -> dict:
        positions = list(self.config.get("servo", "positions", default=[]) or [])
        entry = {"name": name, "pan": pan, "tilt": tilt}
        if preset:
            entry["preset"] = preset
        for i, p in enumerate(positions):
            if p.get("name") == name:
                positions[i] = entry
                break
        else:
            positions.append(entry)
        self.config.set({"servo": {"positions": positions}})
        return {"ok": True, "positions": positions}

    def delete_position(self, name: str) -> dict:
        positions = list(self.config.get("servo", "positions", default=[]) or [])
        remaining = [p for p in positions if p.get("name") != name]
        if len(remaining) == len(positions):
            return {"ok": False, "error": f"没有名为 {name} 的位置预设"}
        self.config.set({"servo": {"positions": remaining}})
        return {"ok": True, "positions": remaining}
