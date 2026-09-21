"""'Take that back' — a shallow undo stack for reversible actions.

Only genuinely reversible, non-destructive actions are recorded:

    type {text}          -> ctrl+z
    volume_up/down       -> opposite step
    mute, show_desktop, media_play_pause -> toggle again
    media_next/previous  -> opposite

Clicking, opening apps and anything touchy stays deliberately un-undoable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_MAX_STACK = 10


@dataclass
class UndoStack:
    entries: list = field(default_factory=list)

    def push(self, command: str, inverse: dict):
        self.entries.append({"command": command, "inverse": inverse})
        del self.entries[:-_MAX_STACK]

    def pop(self):
        return self.entries.pop() if self.entries else None

    def peek(self):
        return self.entries[-1] if self.entries else None

    def clear(self):
        self.entries.clear()


_stack = UndoStack()


# inverse map for symmetric actions (maps action name -> its inverse name)
_TOGGLE = {
    "mute": "mute",
    "show_desktop": "show_desktop",
    "media_play_pause": "media_play_pause",
}
_MIRROR = {
    "volume_up": "volume_down",
    "volume_down": "volume_up",
    "media_next": "media_previous",
    "media_previous": "media_next",
}


def inverse_for(action: dict):
    """Return the action dict that reverses ``action``, or None."""
    if not isinstance(action, dict):
        return None
    name = str(action.get("action") or "").strip().lower()
    if name == "type":
        return {"action": "press_combo", "keys": ["ctrl", "z"]}
    if name in _TOGGLE:
        return {"action": _TOGGLE[name]}
    if name in _MIRROR:
        return {"action": _MIRROR[name]}
    return None


def record(command: str, action: dict) -> None:
    inverse = inverse_for(action)
    if inverse is not None:
        _stack.push(command, inverse)


def last():
    return _stack.peek()


def take_last():
    return _stack.pop()


def clear() -> None:
    _stack.clear()
