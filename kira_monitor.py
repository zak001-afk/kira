"""KIRA's watchdog: proactive system monitoring with spoken alerts.

A daemon thread samples CPU / memory / battery / disk through psutil and
raises a localized alert when a threshold trips, with a per-kind cooldown
so KIRA never nags. All decision logic is pure and unit-testable; the only
side effects live in the tiny ``start``/``stop`` wrapper.
"""
from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass, field

DEFAULT_CONFIG = {
    "enabled": True,
    "interval_seconds": 60,
    "battery_below": 20,
    "cpu_above": 90.0,
    "cpu_sustained_checks": 3,
    "memory_above": 92.0,
    "disk_below_gb": 5.0,
    "cooldown_seconds": 600,
}


@dataclass
class Reading:
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    battery_percent: "float | None" = None
    battery_plugged: bool = True
    disk_free_gb: float = 999.0


@dataclass
class WatchState:
    cpu_streak: int = 0
    last_alert: dict = field(default_factory=dict)  # kind -> timestamp


_MESSAGES = {
    "battery": {
        "en": "Sir, I should mention the battery is at {value:.0f} percent.",
        "fr": "Monsieur, la batterie est à {value:.0f} pour cent.",
        "ar": "سيدي، البطارية عند {value:.0f} بالمئة.",
    },
    "cpu": {
        "en": "Sir, the CPU has been under heavy load ({value:.0f} percent).",
        "fr": "Monsieur, le processeur est fortement sollicité ({value:.0f} pour cent).",
        "ar": "سيدي، المعالج تحت ضغط عالٍ ({value:.0f} بالمئة).",
    },
    "memory": {
        "en": "Sir, memory usage is at {value:.0f} percent — things may slow down.",
        "fr": "Monsieur, la mémoire est à {value:.0f} pour cent — cela peut ralentir.",
        "ar": "سيدي، الذاكرة عند {value:.0f} بالمئة — قد يتباطأ الجهاز.",
    },
    "disk": {
        "en": "Sir, only {value:.1f} gigabytes of disk space remain.",
        "fr": "Monsieur, il ne reste que {value:.1f} gigaoctets d'espace disque.",
        "ar": "سيدي، تبقى {value:.1f} جيجابايت فقط من مساحة القرص.",
    },
}


def evaluate(reading: Reading, config: dict, state: WatchState, now=None):
    """Return (alerts, state) for one sample. Pure — no I/O."""
    now = time.time() if now is None else now
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    cooldown = float(cfg["cooldown_seconds"])
    alerts = []

    def allowed(kind: str) -> bool:
        previous = state.last_alert.get(kind)
        return previous is None or now - previous >= cooldown

    # battery: only when discharging
    if (
        reading.battery_percent is not None
        and not reading.battery_plugged
        and reading.battery_percent <= float(cfg["battery_below"])
        and allowed("battery")
    ):
        alerts.append(("battery", reading.battery_percent))

    # cpu: only after a sustained streak of hot samples
    if reading.cpu_percent >= float(cfg["cpu_above"]):
        state.cpu_streak += 1
    else:
        state.cpu_streak = 0
    if state.cpu_streak >= int(cfg["cpu_sustained_checks"]) and allowed("cpu"):
        alerts.append(("cpu", reading.cpu_percent))
        state.cpu_streak = 0

    if reading.memory_percent >= float(cfg["memory_above"]) and allowed("memory"):
        alerts.append(("memory", reading.memory_percent))

    if reading.disk_free_gb <= float(cfg["disk_below_gb"]) and allowed("disk"):
        alerts.append(("disk", reading.disk_free_gb))

    for kind, _value in alerts:
        state.last_alert[kind] = now

    return alerts, state


def format_alert(kind: str, value: float, language: str = "en") -> str:
    table = _MESSAGES.get(kind, {})
    template = table.get(language) or table["en"]
    return template.format(value=value)


def sample(psutil_module, disk_path: str = "C:\\") -> Reading:
    battery = psutil_module.sensors_battery()
    usage = shutil.disk_usage(disk_path)
    return Reading(
        cpu_percent=float(psutil_module.cpu_percent(interval=None)),
        memory_percent=float(psutil_module.virtual_memory().percent),
        battery_percent=(float(battery.percent) if battery else None),
        battery_plugged=(bool(battery.power_plugged) if battery else True),
        disk_free_gb=usage.free / (1024**3),
    )


class Watchdog:
    """Thin daemon wrapper around ``evaluate``."""

    def __init__(self, sampler, on_alert, config: dict, language: str = "en"):
        self.sampler = sampler
        self.on_alert = on_alert
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.language = language
        self.state = WatchState()
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.running:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # first sample establishes the cpu baseline without alerting
        interval = float(self.config["interval_seconds"])
        while not self._stop.wait(interval):
            try:
                reading = self.sampler()
                alerts, self.state = evaluate(reading, self.config, self.state)
                for kind, value in alerts:
                    self.on_alert(format_alert(kind, value, self.language))
            except Exception:
                continue  # the watchdog never takes KIRA down


_watchdog: "Watchdog | None" = None


def start(sampler, on_alert, config: dict, language: str = "en") -> "Watchdog | None":
    """Idempotent global watchdog starter used by the voice agent."""
    global _watchdog
    if not {**DEFAULT_CONFIG, **(config or {})}.get("enabled", True):
        return None
    if _watchdog is None:
        _watchdog = Watchdog(sampler, on_alert, config, language)
    if _watchdog.running:
        return _watchdog
    _watchdog.start()
    return _watchdog


def stop() -> None:
    global _watchdog
    if _watchdog is not None:
        _watchdog.stop()
        _watchdog = None
