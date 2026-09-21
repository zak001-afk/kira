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
  sequence {"steps":[{...},{...}]}

Rules:
- Valid JSON only. No markdown, no commentary, no extra keys.
- Never invent actions that are not in the allowed list.
- Use "sequence" only for a few directly related steps.
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
