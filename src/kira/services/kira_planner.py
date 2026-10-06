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
    """'gemini' whenever the cloud is ready — the planner asks the linked
    agents (Atlas…) for the facts, and a local model that never answers must
    not sit on that path. KIRA_PLANNER_PROVIDER=ollama/local forces the old
    local behavior back; 'gemini'/'cloud' mean the same as leaving it unset."""
    try:
        import kira_ai
        kira_ai.ensure_env_loaded()  # KIRA_PLANNER_PROVIDER from .env
    except Exception:
        pass
    value = os.environ.get("KIRA_PLANNER_PROVIDER", "").strip().lower()
    if value in {"ollama", "local"}:
        return "ollama"
    if value in {"gemini", "cloud", ""}:
        try:
            import kira_ai
            if kira_ai.cloud_ready():
                return "gemini"
        except Exception:
            pass
    return "ollama"


def planner_route():
    """(provider, model) for planning. The KIRA_MODEL_PLANNER role wins
    (e.g. 'groq:llama-3.1-8b-instant' — tool picking needs speed, not
    genius); otherwise the legacy KIRA_PLANNER_PROVIDER choice."""
    try:
        import kira_ai
        provider, model = kira_ai.role_route("planner")
        if provider:
            return provider, model
    except Exception:
        pass
    return planner_provider(), ""


def build_planner_prompt(catalog, command):
    lines = []
    for spec in catalog:
        args = ", ".join(
            f"{name}:{rules['type']}{'' if rules['required'] else '?'}"
            for name, rules in spec["args"].items())
        if not args:
            args = "any arguments" if spec.get("accepts_extra") else "no arguments"
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


# ── Multi-step plans: two to four tool calls, one approval summary ──────────

_MULTI_STEP_HINTS = re.compile(
    r"\b(?:puis|ensuite|after that|then|also|et aussi|and also|et ensuite)\b"
    r"|\b(?:and then|first.*then)\b", re.IGNORECASE)


def plan_steps(command, ask=None, timeout=8):
    """[{tool, args}, ...] (2-4 steps) for explicit multi-action requests,
    else None. Only fires on clear sequencing words (puis/then/ensuite...):
    a single request keeps the fast one-tool path. The model sees the same
    catalog; unknown tools or non-list shapes mean 'no plan'."""
    command = str(command or "").strip()
    if not command or not planner_enabled():
        return None
    if not _MULTI_STEP_HINTS.search(command):
        return None
    if _PERSONAL.search(command):
        return None
    import kira_agents
    catalog = kira_agents.tool_catalog()
    names = {spec["name"] for spec in catalog}
    lines = []
    for spec in catalog:
        args = ", ".join(
            f"{name}:{rules['type']}{'' if rules['required'] else '?'}"
            for name, rules in spec["args"].items())
        if not args:
            args = "any arguments" if spec.get("accepts_extra") else "no arguments"
        lines.append(f"- {spec['name']} ({args}): {spec['description']}")
    prompt = (
        "You split a user request into tool steps. Reply with ONE JSON array "
        'only, 2 to 4 items, no prose: [{"tool": "<name>", "args": {...}}, '
        '...] — or [] when the request is a single action or not tool-shaped. '
        "Never invent tool names or arguments. Each step must be one of the "
        "listed tools.\n"
        f"Tools:\n" + "\n".join(lines) + f"\nUser request: {command}\n"
        "JSON:"
    )
    try:
        if ask is None:
            import kira_ai
            provider, model = planner_route()
            reply = kira_ai.chat(prompt, provider=provider, model=model,
                                 timeout=timeout, options={"temperature": 0,
                                                           "num_predict": 220},
                                 think=False)
            text = reply.text if reply.ok else ""
        else:
            text = ask(prompt) or ""
    except Exception:
        logger.warning("Planner steps call failed", exc_info=True)
        return None
    match = re.search(r"\[.*\]", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        steps = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(steps, list) or not 2 <= len(steps) <= 4:
        return None
    plan = []
    for step in steps:
        if not isinstance(step, dict):
            return None
        tool = str(step.get("tool") or "").strip()
        if tool not in names:
            return None
        args = step.get("args")
        plan.append({"tool": tool,
                     "args": dict(args) if isinstance(args, dict) else {}})
    if len({step["tool"] for step in plan}) < len(plan):
        return None  # the same tool twice is a loop, not a plan
    logger.info("Planner steps: '%s' -> %s", command[:80],
                [step["tool"] for step in plan])
    return plan


def plan_command(command, ask=None, timeout=6):
    """A (tool, args) plan for the request, or None for 'just chat'.

    The model call is tuned for one-word JSON decisions: reasoning phase
    off (``think=False`` — the registry, not the model, is the contract),
    tiny token cap, short timeout. Any failure means "no plan": the message
    falls through to normal chat, never an error to the user.
    """
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
            provider, model = planner_route()
            reply = kira_ai.chat(prompt, provider=provider, model=model,
                                 timeout=timeout, options={"temperature": 0,
                                                           "num_predict": 96},
                                 think=False)
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
