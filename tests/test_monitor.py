"""Watchdog evaluate logic (pure), cooldowns, and the daemon start/stop."""
import time

import kira_monitor
from kira_monitor import Reading, WatchState


def _config(**overrides):
    base = {"cooldown_seconds": 600}
    base.update(overrides)
    return base


class TestEvaluate:
    def test_low_battery_alerts_only_when_unplugged(self):
        state = WatchState()
        alerts, _ = kira_monitor.evaluate(
            Reading(battery_percent=15, battery_plugged=False), _config(), state, now=100.0
        )
        assert ("battery", 15) in alerts

        alerts, _ = kira_monitor.evaluate(
            Reading(battery_percent=15, battery_plugged=True), _config(), WatchState(), now=100.0
        )
        assert alerts == []

    def test_battery_boundary_and_none(self):
        alerts, _ = kira_monitor.evaluate(
            Reading(battery_percent=20, battery_plugged=False), _config(), WatchState(), now=1.0
        )
        assert alerts and alerts[0][0] == "battery"
        alerts, _ = kira_monitor.evaluate(
            Reading(battery_percent=None, battery_plugged=False), _config(), WatchState(), now=1.0
        )
        assert alerts == []

    def test_cpu_needs_a_sustained_streak(self):
        state = WatchState()
        for _ in range(2):  # below default sustained_checks = 3
            alerts, state = kira_monitor.evaluate(
                Reading(cpu_percent=95), _config(), state, now=50.0
            )
        assert alerts == []
        alerts, state = kira_monitor.evaluate(
            Reading(cpu_percent=95), _config(), state, now=51.0
        )
        assert alerts and alerts[0][0] == "cpu"
        assert state.cpu_streak == 0  # streak resets after firing

    def test_cpu_streak_resets_on_cool_sample(self):
        state = WatchState()
        kira_monitor.evaluate(Reading(cpu_percent=95), _config(), state, now=1.0)
        kira_monitor.evaluate(Reading(cpu_percent=95), _config(), state, now=2.0)
        alerts, state = kira_monitor.evaluate(
            Reading(cpu_percent=20), _config(), state, now=3.0
        )
        assert alerts == [] and state.cpu_streak == 0

    def test_memory_and_disk_thresholds(self):
        alerts, _ = kira_monitor.evaluate(
            Reading(memory_percent=95, disk_free_gb=2.0), _config(), WatchState(), now=1.0
        )
        kinds = {kind for kind, _ in alerts}
        assert kinds == {"memory", "disk"}

    def test_cooldown_suppresses_repeats(self):
        state = WatchState()
        alerts, state = kira_monitor.evaluate(
            Reading(memory_percent=95), _config(), state, now=100.0
        )
        assert alerts
        alerts, state = kira_monitor.evaluate(
            Reading(memory_percent=95), _config(), state, now=120.0
        )
        assert alerts == []  # still inside cooldown
        alerts, state = kira_monitor.evaluate(
            Reading(memory_percent=95), _config(), state, now=800.0
        )
        assert alerts  # cooldown elapsed

    def test_unknown_config_keys_are_ignored(self):
        state = WatchState()
        alerts, _ = kira_monitor.evaluate(
            Reading(memory_percent=95), _config(extra=True), state, now=1.0
        )
        assert alerts


class TestFormatAlert:
    def test_localized_alerts(self):
        assert "73" in kira_monitor.format_alert("memory", 73.0, "en")
        assert "pour cent" in kira_monitor.format_alert("cpu", 91.0, "fr")
        assert "سيدي" in kira_monitor.format_alert("battery", 12.0, "ar")


class TestWatchdogDaemon:
    def test_start_stop_and_alerts(self):
        fired = []
        samples = iter([Reading(cpu_percent=99)] * 20)

        watchdog = kira_monitor.Watchdog(
            sampler=lambda: next(samples, Reading(cpu_percent=99)),
            on_alert=fired.append,
            config={
                "interval_seconds": 0.01,
                "cpu_above": 90.0,
                "cpu_sustained_checks": 2,
                "cooldown_seconds": 0.05,
            },
        )
        assert watchdog.start() is True
        assert watchdog.start() is False  # already running
        deadline = time.time() + 2
        while time.time() < deadline and not fired:
            time.sleep(0.02)
        watchdog.stop()
        assert fired, "watchdog should have spoken at least one alert"
        assert any("CPU" in message for message in fired)

    def test_sampler_failures_never_kill_the_thread(self):
        fired = []
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("no sensors")
            return Reading(memory_percent=99)

        watchdog = kira_monitor.Watchdog(
            sampler=flaky,
            on_alert=fired.append,
            config={"interval_seconds": 0.01, "cooldown_seconds": 0.01},
        )
        watchdog.start()
        deadline = time.time() + 2
        while time.time() < deadline and not fired:
            time.sleep(0.02)
        watchdog.stop()
        assert fired


class TestGlobalStartStop:
    def teardown_method(self):
        kira_monitor.stop()

    def test_disabled_config_starts_nothing(self):
        assert (
            kira_monitor.start(
                sampler=Reading, on_alert=lambda m: None, config={"enabled": False}
            )
            is None
        )

    def test_start_is_idempotent(self):
        first = kira_monitor.start(
            sampler=Reading,
            on_alert=lambda m: None,
            config={"interval_seconds": 60},
        )
        second = kira_monitor.start(
            sampler=Reading,
            on_alert=lambda m: None,
            config={"interval_seconds": 60},
        )
        assert first is second
        kira_monitor.stop()
