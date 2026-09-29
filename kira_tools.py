"""Standard tool-result shape and timing for KIRA's command routes.

Convention (incremental adoption, shared-knowledge search first):

- Tools RETURN data. They never speak, never touch the UI and never block a
  HTTP response on audio playback; the interface that displays a result
  decides whether to speak it afterwards.
- Every tool result carries wall-clock timing (``elapsed_ms``) so slow paths
  show up in payloads instead of being guessed at.
- Failures are structured (``error`` + ``error_code``), not tracebacks leaking
  into HTTP responses.

``ToolResult.to_payload`` produces the same dict shape that
``kira_commands.process_command`` already returns everywhere else, so existing
clients (native window, web UI, HTTP API) keep working unchanged and simply
gain the ``elapsed_ms`` key.
"""
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Uniform result of one tool invocation. Data only — no speech, no UI."""

    action: str
    ok: bool = True
    response: str = ""
    data: object = None
    error: str = ""
    error_code: str = ""
    elapsed_ms: int = 0
    extra: dict = field(default_factory=dict)

    def to_payload(self, **metadata):
        """Flatten into the dict shape process_command clients already parse."""
        payload = {"action": self.action, "success": bool(self.ok),
                   "elapsed_ms": int(self.elapsed_ms), **self.extra, **metadata}
        if self.ok:
            payload["response"] = self.response
        else:
            payload["error"] = self.error or "The tool failed."
            payload["error_code"] = self.error_code or "tool_failed"
            # Clients that only render `response` still show something honest.
            payload["response"] = self.error or "The tool failed."
        return payload


def run_tool(action, function, *args, **kwargs):
    """Run one tool call with timing and structured failure.

    The tool's return value becomes ``response`` when it is text, otherwise it
    is kept in ``data`` with a string rendering in ``response``. Exceptions are
    captured as a failed ToolResult; they are never re-raised so a broken
    optional dependency cannot take down the whole command route.
    """
    started = time.perf_counter()
    try:
        value = function(*args, **kwargs)
    except Exception as error:  # Structured failure, no traceback to clients.
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.warning("Tool %s failed after %d ms: %s", action, elapsed, error)
        return ToolResult(action=action, ok=False, error=str(error),
                          error_code="tool_failed", elapsed_ms=elapsed)
    elapsed = int((time.perf_counter() - started) * 1000)
    if isinstance(value, str):
        return ToolResult(action=action, ok=True, response=value, data=value, elapsed_ms=elapsed)
    if isinstance(value, dict) and isinstance(value.get("response"), str) and value["response"]:
        # Structured tools (kira_code) carry a ready-made sentence next to
        # their data; show that instead of a dict repr.
        return ToolResult(action=action, ok=bool(value.get("ok", True)), data=value,
                          response=value["response"], elapsed_ms=elapsed)
    if isinstance(value, dict) and value.get("ok") is False and isinstance(value.get("error"), str) and value["error"]:
        # Same for structured failures: a sentence, not a dict repr.
        return ToolResult(action=action, ok=False, data=value,
                          error=value["error"],
                          error_code=str(value.get("error_code") or "tool_failed"),
                          response=value["error"], elapsed_ms=elapsed)
    return ToolResult(action=action, ok=True, data=value,
                      response="" if value is None else str(value), elapsed_ms=elapsed)
