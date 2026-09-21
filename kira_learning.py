"""Teach KIRA tricks: macro recording, correction handling, skill promotion.

- **Macro recording** ("learn this routine" ... "call it deploy mode"):
  executed actions are captured as steps and saved as a config shortcut.
- **Correction** ("no, not that one"): demotes the offending learning and
  acknowledges the mistake so the next plan differs.
- **Skill consolidation**: once a learning reaches N successes, KIRA offers
  to make it a permanent shortcut; "make it a shortcut" / "skip the shortcut"
  answer the offer. The pending offer is flagged in user memory so it is
  only offered once per command.
"""
from __future__ import annotations

import re

_save_shortcut_fn = None

PROMOTE_AFTER = 10

# actions that must never be captured into a macro
_META_ACTIONS = {
    "none", "exit", "agent_learnings", "agent_forget", "routine_start",
    "routine_stop", "routine_cancel", "routine_name", "correct_last",
    "skill_promote", "skill_skip", "self_report", "self_review",
    "habit_hint", "conversation_on", "conversation_off", "chat_reset",
    "undo_last", "unlock_lab",
    # building a project takes minutes and cannot replay from a macro
    "project_build", "project_fix", "projects_list", "monitor_on",
    "monitor_off", "secure_lab", "privacy_blur", "weather", "home_control",
}

_recording = False
_steps: list[dict] = []
_pending_promotion: dict | None = None


def set_save_shortcut(fn) -> None:
    """The voice agent injects its config-persisting function here."""
    global _save_shortcut_fn
    _save_shortcut_fn = fn


# ── macro recording ──────────────────────────────────────────────────────────

def start_recording() -> None:
    global _recording, _steps
    _recording = True
    _steps = []


def stop_recording() -> None:
    global _recording
    _recording = False


def is_recording() -> bool:
    return _recording


def recorded_steps() -> list[dict]:
    return list(_steps)


def capture(action: dict) -> None:
    if not _recording or not isinstance(action, dict):
        return
    name = str(action.get("action") or "").strip().lower()
    if not name or name in _META_ACTIONS:
        return
    _steps.append(action)


def finish_recording(name: str):
    """Save the recording as a shortcut. Returns (ok, shortcut_name)."""
    global _steps
    name = re.sub(r"\s+", " ", (name or "").strip().lower())
    steps = list(_steps)
    stop_recording()
    _steps = []
    if not name or not steps:
        return False, name
    if _save_shortcut_fn is None or not _save_shortcut_fn(name, steps):
        return False, name
    return True, name


def cancel_recording() -> int:
    global _steps
    count = len(_steps)
    stop_recording()
    _steps = []
    return count


def extract_routine_name(command: str):
    """'call it deploy mode' / 'appelle-la démo' / 'سمها وضع العمل' -> name."""
    patterns = [
        r"^(?:call|name)\s+(?:it|this|that)\s+(.+)$",
        r"^appelle[- ]la\s+(.+)$",
        r"^appelle[- ]le\s+(.+)$",
        r"^سمها\s+(.+)$",
        r"^سمه\s+(.+)$",
    ]
    text = (command or "").strip().lower()
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            return match.group(1).strip(" .")
    return None


# ── skill consolidation ─────────────────────────────────────────────────────

def check_promotion(command: str, learning: dict, promote_after: int = PROMOTE_AFTER):
    """Return a promotion offer dict once success_count hits the threshold."""
    if not learning:
        return None
    if learning.get("success_count", 0) != promote_after:
        return None
    global _pending_promotion
    _pending_promotion = {
        "command": command,
        "action": learning["action"],
    }
    return _pending_promotion


def pending_promotion():
    return _pending_promotion


def clear_promotion() -> None:
    global _pending_promotion
    _pending_promotion = None


# ── spoken lines ─────────────────────────────────────────────────────────────

_L = {
    "recording_started": {
        "en": "I'm listening to learn, sir. Perform the routine, then say 'call it' followed by a name.",
        "fr": "J'écoute pour apprendre, monsieur. Faites la routine, puis dites 'appelle-la' et un nom.",
        "ar": "أنا أستمع لأتعلم، سيدي. نفذ الحركة ثم قل 'سمها' متبوعاً باسم.",
    },
    "recording_already": {
        "en": "I'm already recording, sir — {count} step{s} so far.",
        "fr": "J'enregistre déjà, monsieur — {count} étape{s} jusqu'ici.",
        "ar": "أنا أسجل بالفعل، سيدي — {count} خطوات حتى الآن.",
    },
    "recording_empty": {
        "en": "There was nothing to save, sir — no steps were recorded.",
        "fr": "Rien à enregistrer, monsieur — aucune étape n'a été capturée.",
        "ar": "لا شيء للحفظ، سيدي — لم تُسجل أي خطوة.",
    },
    "recording_saved": {
        "en": "Understood sir. Routine '{name}' learned with {count} step{s} — say it anytime.",
        "fr": "Compris, monsieur. La routine '{name}' est apprise avec {count} étape{s}.",
        "ar": "فهمت، سيدي. تعلمت الحركة '{name}' بـ {count} خطوات.",
    },
    "recording_cancelled": {
        "en": "Recording discarded, sir.",
        "fr": "Enregistrement annulé, monsieur.",
        "ar": "تم إلغاء التسجيل، سيدي.",
    },
    "not_recording": {
        "en": "I'm not recording anything right now, sir.",
        "fr": "Je n'enregistre rien pour le moment, monsieur.",
        "ar": "لا أسجل شيئاً الآن، سيدي.",
    },
    "promotion_offer": {
        "en": "Sir, I've now done '{command}' {count} times successfully. Shall I make it a permanent shortcut?",
        "fr": "Monsieur, j'ai réussi '{command}' {count} fois. Voulez-vous en faire un raccourci permanent ?",
        "ar": "سيدي، نفذت '{command}' {count} مرات بنجاح. هل أجعله اختصاراً دائماً؟",
    },
    "promotion_saved": {
        "en": "Done sir. '{name}' is now a permanent shortcut.",
        "fr": "C'est fait, monsieur. '{name}' est désormais un raccourci permanent.",
        "ar": "تم، سيدي. '{name}' أصبح اختصاراً دائماً.",
    },
    "promotion_none": {
        "en": "There's no shortcut offer waiting, sir.",
        "fr": "Aucune proposition de raccourci en attente, monsieur.",
        "ar": "لا يوجد عرض اختصار بانتظارك، سيدي.",
    },
    "promotion_skipped": {
        "en": "Understood sir — I'll keep it learned, but not permanent.",
        "fr": "Compris, monsieur — je le garde appris, mais pas permanent.",
        "ar": "فهمت، سيدي — سأحتفظ به متعلماً، لكن ليس دائماً.",
    },
    "correction_ack": {
        "en": "Noted, sir — I've marked that as a mistake. It won't be my first choice next time.",
        "fr": "Noté, monsieur — j'ai marqué cela comme une erreur. Ce ne sera plus mon premier choix.",
        "ar": "سجلت ذلك، سيدي — اعتبرته خطأ. لن يكون خياري الأول في المرة القادمة.",
    },
    "correction_none": {
        "en": "There's nothing recent to correct, sir.",
        "fr": "Il n'y a rien de récent à corriger, monsieur.",
        "ar": "لا يوجد شيء حديث لتصحيحه، سيدي.",
    },
}


def say(key: str, language: str = "en", **kwargs) -> str:
    template = _L.get(key, {}).get(language) or _L[key]["en"]
    count = kwargs.get("count")
    if count is not None:
        kwargs = dict(kwargs, s="" if count == 1 else "s")
        if language == "fr":
            kwargs["s"] = "" if count == 1 else "s"
    return template.format(**kwargs)
