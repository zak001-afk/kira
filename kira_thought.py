"""KIRA's mind: an explicit think -> act -> reflect loop with its own memory.

Two distinct kinds of memory exist in KIRA:

- **user memory** (kira_memory.memories): facts the *user* stated about
  themselves ("my name is ..."), used to personalise answers.
- **agent memory** (this module): what the *agent itself* experienced and
  concluded — episodes of (thought, action, outcome) and learned
  command -> action mappings that let it recall instead of re-planning.

The thinking process, for commands the deterministic parser can't handle:

1. **Recall** — has KIRA successfully handled this (or a similar
   phrasing) before? Reuse the stored plan without calling the model.
2. **Think** — otherwise ask the local LLM for a JSON envelope
   ``{"thought": "...", "action": {...}}``. The thought is KIRA's
   plan/understanding (shown in the UI/log, never spoken); the action is
   validated against the whitelist before it can run.
3. **Reflect** — after execution the outcome is recorded: successes are
   strengthened, failures recorded as episodes AND demoted so KIRA stops
   repeating mistakes (reflexion).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import kira_memory

log = logging.getLogger(__name__)

# Actions the planner may legitimately produce (validated before executing
# anything the model or the learnings table claims).
ALLOWED_ACTIONS = frozenset(
    {
        "none", "exit", "open_app", "open_url", "open_folder", "type", "press",
        "search", "mouse_move", "click", "close_window", "minimize_window",
        "maximize_window", "switch_app", "screenshot", "volume_up",
        "volume_down", "mute", "media_play_pause", "media_next",
        "media_previous", "lock_pc", "show_desktop", "copy", "paste",
        "read_clipboard", "system_info", "help", "time", "date",
        "set_address", "shortcut", "remember", "sequence", "calc", "remind",
        "reminders_list", "reminders_clear", "conversation_on",
        "conversation_off", "chat_reset", "mode_info", "agent_learnings",
        "agent_forget",
        "self_report", "self_review", "habit_hint", "monitor_on",
        "monitor_off", "privacy_blur", "secure_lab", "unlock_lab",
        "undo_last", "routine_start", "routine_stop", "routine_cancel",
        "routine_name", "correct_last", "skill_promote", "skill_skip",
        "weather", "home_control", "press_combo",
        "look_at_screen", "vision_click",
        "project_build", "project_fix", "projects_list",
    }
)

THINK_SYSTEM_PROMPT = """
You are KIRA, a smart local AI computer assistant. Think before you act.

The deterministic command parser could not handle the user's request, so it
is your turn. Respond with EXACTLY ONE JSON object of the form:

{"thought": "...", "action": {...}}

- "thought": one short sentence describing what the user wants and, if
  relevant, how you will do it. Never more than 25 words.
- "action": ONE of the allowed action objects:

  open_app {"target":"notepad"}        open_url {"target":"https://..."}
  open_folder {"target":"downloads"}   type {"text":"..."}
  press {"target":"enter"}             search {"query":"..."}
  mouse_move {"x":500,"y":300}         click {}
  close_window {}  minimize_window {}  maximize_window {}  switch_app {}
  screenshot {}    volume_up {}        volume_down {}      mute {}
  media_play_pause {}  media_next {}   media_previous {}
  lock_pc {}       show_desktop {}     copy {}  paste {}  read_clipboard {}
  system_info {}   none {}
  look_at_screen {"question":"what is on my screen?"}
  vision_click {"target":"the save button"}
  sequence {"steps":[{...},{...}]}

Rules:
- Valid JSON only. No markdown, no commentary, no extra keys.
- Never invent actions that are not in the allowed list.
- Use "sequence" only for a few directly related steps.
- Use the vision actions when the task has to be done by looking at the
  screen: "look_at_screen" to read it, "vision_click" to click something on
  it. vision_click moves the real mouse, so KIRA asks the user first.
- If the request cannot be mapped to a computer action, use {"action":"none"}
  and put the reason in "thought".
"""


@dataclass
class Thought:
    """The outcome of one thinking pass."""

    command: str
    text: str = ""                    # the plan/understanding (never spoken)
    action: dict = field(default_factory=lambda: {"action": "none"})
    source: str = "invalid"           # "memory" | "llm" | "invalid"
    explanation: str = ""             # why (recall hit, model used, failure)


_LAST_THOUGHT: "Thought | None" = None


def last_thought() -> "Thought | None":
    return _LAST_THOUGHT


def _set_last(thought: Thought) -> Thought:
    global _LAST_THOUGHT
    _LAST_THOUGHT = thought
    if thought.text:
        log.info("THOUGHT [%s]: %s", thought.source, thought.text)
    return thought


# ── action validation ────────────────────────────────────────────────────────

def validate_action(action) -> bool:
    """True only if every (nested) action name is whitelisted."""
    if not isinstance(action, dict):
        return False
    name = str(action.get("action") or "").strip().lower()
    if name not in ALLOWED_ACTIONS:
        return False
    if name == "sequence":
        steps = action.get("steps")
        if not isinstance(steps, list) or not steps:
            return False
        return all(
            isinstance(step, dict)
            and str(step.get("action") or "").strip().lower() != "sequence"
            and validate_action(step)
            for step in steps
        )
    return True


def _extract_json(text: str):
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def _parse_envelope(payload: dict):
    """Return (thought_text, action_dict) from a planner response."""
    if not isinstance(payload, dict):
        return "", {"action": "none"}
    # preferred envelope: {"thought": ..., "action": {...}}
    inner = payload.get("action")
    if isinstance(inner, dict):
        return str(payload.get("thought", "") or "").strip(), inner
    # legacy direct action object (thinking omitted by the model)
    return str(payload.get("thought", "") or "").strip(), payload


# ── the thinking pass ───────────────────────────────────────────────────────

def think(command: str, ollama_fn) -> Thought:
    """Reason about an unhandled command.

    ``ollama_fn(messages, options)`` must behave like
    ``kira_voice_agent.call_ollama``: return {"message": {"content": str}}.
    """
    normalized = kira_memory.normalize_agent_command(command)

    # 1) exact recall — identical phrasing succeeded before
    recalled = kira_memory.recall_action(normalized)
    if recalled and validate_action(recalled["action"]):
        return _set_last(
            Thought(
                command=normalized,
                text=f"I have done this before ({recalled['success_count']} time(s) successfully).",
                action=recalled["action"],
                source="memory",
                explanation="exact recall",
            )
        )

    # 2) fuzzy recall — a similar phrasing succeeded before
    similar = kira_memory.find_similar_learnings(normalized)
    if similar and validate_action(similar[0]["action"]):
        return _set_last(
            Thought(
                command=normalized,
                text=f"This resembles '{similar[0]['command']}', which worked before.",
                action=similar[0]["action"],
                source="memory",
                explanation="similarity recall",
            )
        )

    # 3) ask the local model to plan, inside the thought/action envelope
    try:
        response = ollama_fn(
            messages=[
                {"role": "system", "content": THINK_SYSTEM_PROMPT},
                {"role": "user", "content": normalized},
            ],
            options={"num_ctx": 4096, "temperature": 0, "num_predict": 500},
        )
    except Exception as exc:
        log.warning("thinking failed: %s", exc)
        return _set_last(
            Thought(
                command=normalized,
                text="I cannot reach my reasoning model right now.",
                action={"action": "none"},
                source="invalid",
                explanation=f"ollama error: {exc}",
            )
        )

    content = response.get("message", {}).get("content", "")
    payload = _extract_json(content)
    if payload is None:
        return _set_last(
            Thought(
                command=normalized,
                text="I could not form a valid plan.",
                action={"action": "none"},
                source="invalid",
                explanation="model returned no usable JSON",
            )
        )

    thought_text, action = _parse_envelope(payload)
    if not validate_action(action):
        return _set_last(
            Thought(
                command=normalized,
                text=thought_text or "I could not form a valid plan.",
                action={"action": "none"},
                source="invalid",
                explanation="model returned an invalid or unknown action",
            )
        )

    return _set_last(
        Thought(
            command=normalized,
            text=thought_text or "Here is what I intend to do.",
            action=action,
            source="llm",
            explanation="llm plan",
        )
    )


# ── reflection ───────────────────────────────────────────────────────────────

def reflect(command: str, action: dict, source: str, outcome: str) -> None:
    """Record what happened and update the learning that led to it."""
    outcome = outcome if outcome in {"success", "failed", "unknown"} else "unknown"
    if not isinstance(action, dict) or not action:
        return
    if action.get("action") in {"none", ""}:
        return

    thought_text = ""
    if _LAST_THOUGHT is not None and _LAST_THOUGHT.command == kira_memory.normalize_agent_command(command):
        thought_text = _LAST_THOUGHT.text

    kira_memory.save_episode(command, thought_text, action, source, outcome)

    # Only the planner's own decisions are learnable — parser decisions are
    # deterministic and need no memory.
    if source in {"llm", "memory"}:
        kira_memory.learn_from_outcome(
            command,
            action,
            outcome == "success",
        )
        log.info("REFLECT [%s/%s]: %s -> %s", source, outcome, command, action)


# ── spoken reports about the agent's mind ────────────────────────────────────

def describe_learnings(limit: int = 5, language: str = "en") -> str:
    top = kira_memory.top_learnings(limit)
    if not top:
        return {
            "en": "I have not learned any new commands yet, sir.",
            "fr": "Je n'ai encore appris aucune nouvelle commande, monsieur.",
            "ar": "لم أتعلم أي أوامر جديدة بعد، سيدي.",
        }.get(language)
    items = "; ".join(
        f"'{entry['command']}' → {entry['action'].get('action', '?')}"
        f" ({entry['success_count']}×)"
        for entry in top
    )
    return {
        "en": f"Here is what I have learned so far, sir: {items}.",
        "fr": f"Voici ce que j'ai appris jusqu'ici, monsieur : {items}.",
        "ar": f"إليك ما تعلمته حتى الآن، سيدي: {items}.",
    }.get(language)


def cleared_message(count: int, language: str = "en") -> str:
    if count == 0:
        return describe_learnings(language=language)
    return {
        "en": f"Done sir. I have forgotten all {count} learned command{'s' if count != 1 else ''}.",
        "fr": f"C'est fait, monsieur. J'ai oublié les {count} commandes apprises.",
        "ar": f"تم، سيدي. لقد نسيت {count} أمراً متعلماً.",
    }.get(language)


# ── self-awareness: reports, reviews and habit anticipation ──────────────────

import time as _time

_STARTED_AT = _time.time()


def _rate(success: int, failed: int) -> int:
    total = success + failed
    return round(100 * success / total) if total else 0


def self_report(language: str = "en", models_online: bool = True) -> str:
    """'How are you feeling, KIRA?' — the agent reads its own mind aloud."""
    counts = kira_memory.episode_counts()
    learnings = kira_memory.learnings_summary()
    facts = kira_memory.load_memories()
    uptime_minutes = max(1, int((_time.time() - _STARTED_AT) // 60))
    rate = _rate(counts["success"], counts["failed"])

    if language == "fr":
        report = (
            f"Tous les systèmes sont nominaux, monsieur. En service depuis "
            f"{uptime_minutes} minutes, {counts['total']} opérations exécutées "
            f"avec un taux de réussite de {rate}%. J'ai appris {learnings['count']} "
            f"compétences et je retiens {len(facts)} faits vous concernant. "
            f"{'Modèles locaux opérationnels.' if models_online else 'Mes modèles locaux sont injoignables pour le moment.'}"
        )
    elif language == "ar":
        report = (
            f"جميع الأنظمة تعمل بشكل طبيعي، سيدي. في الخدمة منذ "
            f"{uptime_minutes} دقيقة، نفذت {counts['total']} عملية "
            f"بنسبة نجاح {rate}%. تعلمت {learnings['count']} مهارات "
            f"وأتذكر {len(facts)} حقائق عنك. "
            f"{'النماذج المحلية متصلة.' if models_online else 'النماذج المحلية غير متاحة حالياً.'}"
        )
    else:
        report = (
            f"All systems nominal, sir. {uptime_minutes} minutes on duty, "
            f"{counts['total']} operations handled with a {rate}% success rate. "
            f"I currently hold {learnings['count']} learned skills and "
            f"{len(facts)} remembered facts about you. "
            f"{'Local models responding normally.' if models_online else 'My local models are unreachable right now — commands still work, thinking does not.'}"
        )
    return report


def self_review(language: str = "en", today_iso: str = "") -> str:
    """End-of-day reflection: rates today, names failures, keeps it honest."""
    from datetime import datetime as _dt

    day = today_iso or _dt.now().date().isoformat()
    episodes = kira_memory.episodes_on(day)
    success = sum(1 for e in episodes if e["outcome"] == "success")
    failed = sum(1 for e in episodes if e["outcome"] == "failed")
    rate = _rate(success, failed)
    failures = [e["command"] for e in episodes if e["outcome"] == "failed"][:3]

    if not episodes:
        return {
            "en": "A quiet day so far, sir — nothing on record yet.",
            "fr": "Une journée calme jusqu'ici, monsieur — rien d'enregistré.",
            "ar": "يوم هادئ حتى الآن، سيدي — لا شيء مسجل بعد.",
        }.get(language)

    if language == "fr":
        text = (
            f"Bilan du jour, monsieur : {len(episodes)} opérations, "
            f"{success} réussies, taux de {rate}%."
        )
        if failures:
            text += (
                f" Points d'échec : {', '.join(failures)}. "
                "Je les ai rétrogradés — je les aborderai différemment la prochaine fois."
            )
        else:
            text += " Aucun échec aujourd'hui. Journée impeccable."
    elif language == "ar":
        text = (
            f"مراجعة اليوم، سيدي: {len(episodes)} عملية، "
            f"{success} ناجحة، بنسبة {rate}%."
        )
        if failures:
            text += f" إخفاقات في: {'، '.join(failures)}. خفضت أولويتها وسأتصرف بشكل مختلف لاحقاً."
        else:
            text += " لا إخفاقات اليوم. يوم مثالي."
    else:
        text = (
            f"Today's review, sir: {len(episodes)} operations, {success} successful, "
            f"{rate}% success rate."
        )
        if failures:
            text += (
                f" Failures involved: {', '.join(failures)}. "
                "I've demoted those approaches — I'll play them differently next time."
            )
        else:
            text += " Not a single failure today. A clean sheet, sir."
    return text


def habit_hint(language: str = "en", hour: "int | None" = None) -> str:
    """'What do I usually do right now?' — patterns from successful episodes."""
    from collections import Counter
    from datetime import datetime as _dt

    now_hour = _dt.now().hour if hour is None else hour
    pairs = kira_memory.successful_episode_hours()
    by_command = Counter(command for command, _ in pairs)
    if not by_command:
        return {
            "en": "I don't have enough history to spot a habit yet, sir.",
            "fr": "Pas encore assez d'historique pour détecter une habitude, monsieur.",
            "ar": "لا يوجد سجل كافٍ لتمييز عادة بعد، سيدي.",
        }.get(language)

    candidates = []
    for command, uses in by_command.most_common():
        hours = [h for c, h in pairs if c == command]
        hour_hits = sum(1 for h in hours if abs(h - now_hour) <= 1)
        if uses >= 3 and hour_hits >= (uses + 1) // 2:
            candidates.append((command, uses, hour_hits))
    if not candidates:
        return {
            "en": "No clear habit for this hour has emerged yet, sir.",
            "fr": "Aucune habitude claire pour cette heure pour l'instant, monsieur.",
            "ar": "لم تظهر عادة واضحة لهذه الساعة بعد، سيدي.",
        }.get(language)

    command, uses, hour_hits = candidates[0]
    return {
        "en": f"Pattern detected, sir: around this time you usually say '{command}' — {hour_hits} of {uses} times. Shall I?",
        "fr": f"Habitude repérée, monsieur : à cette heure vous dites souvent '{command}' — {hour_hits} fois sur {uses}. Je le fais ?",
        "ar": f"لاحظت نمطاً، سيدي: في هذا الوقت عادة تقول '{command}' — {hour_hits} من {uses} مرات. هل أنفذ؟",
    }.get(language)
