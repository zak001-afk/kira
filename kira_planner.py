"""KIRA as controller: an optional planner that maps a natural-language
request to ONE registered tool call.

Experimental and OFF by default — set KIRA_PLANNER=1 in .env to enable.

Design rules (enforced here and by the registry):
- The model only CHOOSES among registered tools; it cannot invent actions.
- Arguments are validated by the registry; consequential tools still require
  the user's approval — the planner has no bypass.
- Personal statements/questions never reach the planner model.
- Any failure (timeout, bad JSON, unknown tool) means "no plan": the message
  falls through to normal chat, never an error to the user.
"""

import json
import logging
import os
import re

logger = logging.getLogger("kira.planner")

_TRUE = {"1", "true", "on", "yes"}

_PERSONAL = re.compile(
    r"(?:\bmy\s+name\b|\bremember\b|\bmemorize\b|\bforget\b|\bcall\s+me\b"
    r"|mon\s+nom|je\s+m'appelle|souviens[\s-]toi|rappelle[\s-]toi|oublie"
    r"|اسمي|تذكر|انس)", re.IGNORECASE)


def planner_enabled():
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()
    except Exception:
        pass
    return os.environ.get("KIRA_PLANNER", "").strip().lower() in _TRUE


def planner_provider():
    """'ollama' unless the user explicitly opted the planner into Gemini
    (KIRA_PLANNER_PROVIDER=gemini) AND the cloud is ready."""
    value = os.environ.get("KIRA_PLANNER_PROVIDER", "").strip().lower()
    if value in {"gemini", "cloud"}:
        try:
            import kira_ai
            if kira_ai.cloud_ready():
                return "gemini"
        except Exception:
            pass
    return "ollama"


def build_planner_prompt(catalog, command):
    lines = []
    for spec in catalog:
        args = ", ".join(
            f"{name}:{rules['type']}{'' if rules['required'] else '?'}"
            for name, rules in spec["args"].items()) or "no arguments"
        lines.append(f"- {spec['name']} ({args}): {spec['description']}")
    tools = "\n".join(lines)
    return (
        "You route user requests to tools. Reply with ONE JSON object only, "
        'no other text: {"tool": "<name>", "args": {...}} or {"tool": "none"} '
        "when no tool clearly matches. Questions, chat, opinions, jokes and "
        "anything ambiguous are none. Never invent tool names or arguments.\n"
        f"Tools:\n{tools}\n"
        f"User request: {command}\n"
        "JSON:"
    )


def parse_plan(text, catalog):
    """(tool_name, args) from the model's reply, or None. Tolerates code
    fences and prose around the JSON; refuses unknown tools."""
    names = {spec["name"] for spec in catalog}
    match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        plan = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(plan, dict):
        return None
    tool = str(plan.get("tool") or "").strip()
    if tool not in names:
        return None
    args = plan.get("args")
    return tool, (dict(args) if isinstance(args, dict) else {})


def plan_command(command, ask=None, timeout=6):
    """A (tool, args) plan for the request, or None for 'just chat'."""
    command = str(command or "").strip()
    if not command or not planner_enabled():
        return None
    if _PERSONAL.search(command):
        return None  # personal content never reaches the planner model
    import kira_agents
    catalog = kira_agents.tool_catalog()
    prompt = build_planner_prompt(catalog, command)
    try:
        if ask is None:
            import kira_ai
            reply = kira_ai.chat(prompt, provider=planner_provider(), timeout=timeout)
            text = reply.text if reply.ok else ""
        else:
            text = ask(prompt) or ""
    except Exception:
        logger.warning("Planner model call failed", exc_info=True)
        return None
    plan = parse_plan(text, catalog)
    if plan:
        logger.info("Planner: '%s' -> %s %s", command[:80], plan[0], plan[1])
    return plan
