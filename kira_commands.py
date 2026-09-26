"""Lightweight command routing shared by all KIRA interfaces."""

import re

_LEARN = re.compile(
    r"^(?:learn about|research|study|teach yourself(?: about)?)(?:\s+(.*))?$",
    re.IGNORECASE,
)


def try_web_learning(text):
    """Return a web-learning reply, or None for unrelated commands.

    Deliberately exclude 'remember' and 'memorize': private notes must not
    accidentally become web queries or shared research.
    """
    match = _LEARN.fullmatch(str(text or "").strip())
    if not match:
        return None
    topic = (match.group(1) or "").strip()
    if not topic:
        return "What would you like me to learn about?"
    try:
        import kira_web
        return kira_web.search_and_learn(topic)
    except Exception as exc:
        return f"I tried to learn about that but encountered an error: {exc}"
