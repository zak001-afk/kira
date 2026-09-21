"""The morning briefing: a time-aware spoken status summary.

Composed from the personality greeting, the clock, the battery, and the
live reminder list — everything local, everything testable with stubs.
"""
from __future__ import annotations

from datetime import datetime

import kira_personality
import kira_reminders


def briefing(
    language: str = "en",
    humor: str = "neutral",
    battery_percent: "float | None" = None,
    now: "datetime | None" = None,
) -> str:
    """Build the spoken briefing. ``battery_percent``/``now`` are injected
    so the function itself never touches hardware."""
    now = now or datetime.now()
    greet = kira_personality.greeting(now.hour, language, humor=humor)
    clock = now.strftime("%H:%M")
    date = now.strftime("%A %d %B")

    active = kira_reminders.active()
    sentences = [greet]
    if language == "fr":
        sentences.append(f"nous sommes le {date} et il est {clock}.")
        if battery_percent is not None:
            sentences.append(f"la batterie est à {battery_percent:.0f} pour cent.")
        if active:
            sentences.append(
                f"vous avez {len(active)} rappel{'s' if len(active) != 1 else ''} en attente."
            )
    elif language == "ar":
        sentences.append(f"اليوم هو {date} والساعة {clock}.")
        if battery_percent is not None:
            sentences.append(f"البطارية عند {battery_percent:.0f} بالمئة.")
        if active:
            sentences.append(f"لديك {len(active)} تذكيرات بانتظارك.")
    else:
        sentences.append(f"it is {clock} on {date}.")
        if battery_percent is not None:
            sentences.append(f"battery is at {battery_percent:.0f} percent.")
        if active:
            sentences.append(
                f"you have {len(active)} reminder{'s' if len(active) != 1 else ''} pending."
            )
    return " ".join(sentences)
