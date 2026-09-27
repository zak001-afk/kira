"""Provider-independent AI layer: local Ollama by default, Gemini opt-in.

Privacy rules (enforced here, not left to callers' goodwill):

- The LOCAL provider (Ollama) is the default. Nothing leaves the machine.
- The CLOUD provider (Gemini) is DISABLED unless the environment explicitly
  sets ``KIRA_CLOUD_AI`` to ``1``/``true``/``on``/``yes``. Without it, cloud
  requests are refused before any network activity.
- The API key comes from backend environment variables only
  (``GEMINI_API_KEY``, or ``GOOGLE_API_KEY`` as a fallback). It is sent as a
  request header, never embedded in URLs, never logged, and scrubbed from
  error messages.
- Callers remain responsible for WHAT they send: personal memory, code and
  screenshots must not be forwarded to a cloud model without explicit user
  approval. This module only guarantees the transport-level gates.

Replies are data (`AIReply`), in the same spirit as kira_tools.ToolResult:
structured errors, wall-clock timing, no speech, no UI.
"""
from dataclasses import dataclass
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

LOCAL_PROVIDER = "ollama"
CLOUD_PROVIDER = "gemini"
PROVIDERS = (LOCAL_PROVIDER, CLOUD_PROVIDER)

DEFAULT_TIMEOUT = 30
_TRUE_VALUES = {"1", "true", "on", "yes"}


@dataclass
class AIReply:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    error: str = ""
    error_code: str = ""
    elapsed_ms: int = 0


_ENV_LOADED = False


def ensure_env_loaded(path=None):
    """Load .env (next to the code) into os.environ without any dependency.

    Real environment variables always win (setdefault). Tolerates a Windows
    Notepad BOM and quoted values. Values are never logged or printed."""
    global _ENV_LOADED
    if path is None:
        if _ENV_LOADED:
            return
        _ENV_LOADED = True
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except OSError:
        pass


def cloud_enabled() -> bool:
    """Cloud AI is opt-in via KIRA_CLOUD_AI; absence means local-only."""
    ensure_env_loaded()
    return os.environ.get("KIRA_CLOUD_AI", "").strip().lower() in _TRUE_VALUES


def cloud_ready() -> bool:
    """True only when the user opted in AND a key is configured."""
    return cloud_enabled() and bool(_gemini_key())


def _gemini_key() -> str:
    ensure_env_loaded()
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def gemini_model() -> str:
    return os.environ.get("KIRA_GEMINI_MODEL", "").strip() or "gemini-2.5-flash"


def ollama_url() -> str:
    return os.environ.get("KIRA_OLLAMA_URL", "").strip() or "http://127.0.0.1:11434"


def ollama_model(default: str = "") -> str:
    configured = os.environ.get("KIRA_OLLAMA_MODEL", "").strip()
    if configured:
        return configured
    if default:
        return default
    try:  # The desktop app's model choice lives in kira_config.json.
        from pathlib import Path
        config = json.loads((Path(__file__).resolve().parent / "kira_config.json").read_text(encoding="utf-8"))
        return str(config.get("model", "")).strip() or "qwen3:0.6b"
    except Exception:
        return "qwen3:0.6b"


def availability() -> dict:
    """Booleans only — never key material. Safe to expose over the local API."""
    return {
        "providers": list(PROVIDERS),
        "default": LOCAL_PROVIDER,
        "ollama": {"url": ollama_url(), "model": ollama_model()},
        "gemini": {
            "cloud_enabled": cloud_enabled(),
            "key_present": bool(_gemini_key()),
            "model": gemini_model(),
        },
    }


def _scrub(text: str) -> str:
    """Keep the API key out of error strings and logs, whatever happens."""
    key = _gemini_key()
    return text.replace(key, "***") if key else text


def _as_messages(prompt_or_messages) -> list:
    if isinstance(prompt_or_messages, str):
        return [{"role": "user", "content": prompt_or_messages}]
    return [{"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in (prompt_or_messages or [])]


def chat(prompt_or_messages, provider: str = "", model: str = "",
         timeout: int = DEFAULT_TIMEOUT, options: dict = None) -> AIReply:
    """One chat call against the selected provider, as structured data.

    `prompt_or_messages` is a plain string or a list of
    ``{"role": ..., "content": ...}`` dicts (roles: system/user/assistant).
    """
    provider = (provider or LOCAL_PROVIDER).strip().lower()
    messages = _as_messages(prompt_or_messages)
    started = time.perf_counter()

    def fail(code, message):
        return AIReply(ok=False, provider=provider, model=model, error=_scrub(message),
                       error_code=code, elapsed_ms=int((time.perf_counter() - started) * 1000))

    if provider not in PROVIDERS:
        return fail("unknown_provider", f"Unknown AI provider '{provider}'. Available: {', '.join(PROVIDERS)}.")
    if not messages or not any(m["content"].strip() for m in messages):
        return fail("empty_prompt", "There is nothing to send to the model.")

    try:
        if provider == CLOUD_PROVIDER:
            if not cloud_enabled():
                return fail("cloud_disabled",
                            "Cloud AI is disabled. Set KIRA_CLOUD_AI=1 in the backend "
                            "environment to allow Gemini; local Ollama remains the default.")
            key = _gemini_key()
            if not key:
                return fail("missing_api_key",
                            "GEMINI_API_KEY is not set in the backend environment (.env).")
            return _chat_gemini(messages, model or gemini_model(), key, timeout, started)
        return _chat_ollama(messages, model or ollama_model(), timeout, started, options or {})
    except requests.Timeout:
        return fail("timeout", f"The {provider} request exceeded {timeout} seconds.")
    except requests.RequestException as error:
        return fail("provider_unreachable", f"Could not reach {provider}: {error}")
    except Exception as error:  # Structured failure, never a traceback upstream.
        logger.warning("AI provider %s failed: %s", provider, _scrub(str(error)))
        return fail("provider_failed", f"{provider} failed: {error}")


def _chat_ollama(messages, model, timeout, started, options) -> AIReply:
    response = requests.post(
        f"{ollama_url()}/api/chat",
        json={"model": model, "messages": messages, "stream": False,
              **({"options": options} if options else {})},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    text = str(((payload or {}).get("message") or {}).get("content", "")).strip()
    elapsed = int((time.perf_counter() - started) * 1000)
    if not text:
        return AIReply(ok=False, provider=LOCAL_PROVIDER, model=model, elapsed_ms=elapsed,
                       error="Ollama returned an empty reply.", error_code="empty_reply")
    return AIReply(ok=True, text=text, provider=LOCAL_PROVIDER, model=model, elapsed_ms=elapsed)


def _chat_gemini(messages, model, key, timeout, started) -> AIReply:
    system_parts = [m["content"] for m in messages if m["role"] == "system" and m["content"].strip()]
    contents = [{"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]}
                for m in messages if m["role"] != "system" and m["content"].strip()]
    body = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},  # Header, never the URL.
        json=body,
        timeout=timeout,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        detail = _scrub(str(response.text)[:300])
        return AIReply(ok=False, provider=CLOUD_PROVIDER, model=model, elapsed_ms=elapsed,
                       error=f"Gemini returned HTTP {response.status_code}: {detail}",
                       error_code="provider_error")
    payload = response.json()
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(str(part.get("text", "")) for part in parts).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        return AIReply(ok=False, provider=CLOUD_PROVIDER, model=model, elapsed_ms=elapsed,
                       error="Gemini returned no usable text (the reply may have been blocked).",
                       error_code="empty_reply")
    return AIReply(ok=True, text=text, provider=CLOUD_PROVIDER, model=model, elapsed_ms=elapsed)
