"""Add AI provider keys to .env — without pasting them in any chat.

Reads GROQ_API_KEY and OPENROUTER_API_KEY via getpass (hidden input,
nothing echoed, nothing logged) and writes them into the project .env,
replacing the commented placeholders if present. Then optionally pings
both providers through kira_ai's own resolution logic.

Usage (from the project root):
    python tools_add_provider_keys.py          # interactive
    python tools_add_provider_keys.py --check  # verify without asking
"""

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

TARGETS = (
    ("GROQ_API_KEY", "Groq (gsk_...)", "gsk_"),
    ("OPENROUTER_API_KEY", "OpenRouter (sk-or-v1-...)", "sk-or-v1-"),
)


def load_env_text():
    return ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""


def upsert_key(text, key, value):
    """Replace an existing active line, or insert under the right comment."""
    pattern = re.compile(rf"^{key}=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(f"{key}={value}", text, count=1)
    # Insert after the commented placeholder for that key, if any.
    comment = re.compile(rf"^(#\s*{key}=.*|.*{key}\.\.\..*)$", re.MULTILINE)
    match = comment.search(text)
    line = f"{key}={value}"
    if match:
        return text[:match.start()] + line + text[match.end():]
    if not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def env_value(text, key):
    match = re.search(rf"^{key}=(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def ask_and_store(text, key, label):
    """Hide-typed input; empty input keeps the current value."""
    current = env_value(text, key)
    hint = " (déjà défini — Entrée pour garder)" if current else ""
    value = getpass.getpass(f"{label}{hint} : ").strip()
    if not value:
        return text, False
    text = upsert_key(text, key, value)
    return text, True


def verify():
    """Live ping of both providers through KIRA's own chain."""
    import os
    sys.path.insert(0, str(ROOT))
    import kira_ai
    kira_ai._ENV_LOADED = True  # we just wrote the file; re-read manually
    for line in load_env_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

    import requests

    groq = os.environ.get("GROQ_API_KEY", "")
    router = os.environ.get("OPENROUTER_API_KEY", "")

    print()
    if groq:
        model = kira_ai.groq_model()
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq}"},
                json={"model": model,
                      "messages": [{"role": "user", "content": "Réponds juste: OK"}],
                      "max_tokens": 5},
                timeout=15)
            ok = response.status_code == 200
            reply = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  GROQ        {'✅ OK' if ok else '❌ HTTP ' + str(response.status_code)}"
                  f"  modèle={model}  réponse={reply[:20]!r}")
        except Exception as exc:
            print(f"  GROQ        ❌ {exc}")
    else:
        print("  GROQ        — non défini")

    if router:
        model = kira_ai.openrouter_model()
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {router}"},
                json={"model": model,
                      "messages": [{"role": "user", "content": "Réponds juste: OK"}],
                      "max_tokens": 5},
                timeout=20)
            ok = response.status_code == 200
            reply = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  OPENROUTER  {'✅ OK' if ok else '❌ HTTP ' + str(response.status_code)}"
                  f"  modèle={model}  réponse={reply[:20]!r}")
        except Exception as exc:
            print(f"  OPENROUTER  ❌ {exc}")
        # Show which :free model KIRA's auto-discovery would pick.
        try:
            discovered = kira_ai._discover_openrouter_model(router)
            print(f"  auto-détection :free -> {discovered or 'aucun'}")
        except Exception:
            pass
    else:
        print("  OPENROUTER  — non défini")

    print("\n  cloud_ready (gemini):", kira_ai.cloud_ready())
    print("  Redémarrez KIRA pour que le moteur charge les nouvelles clés.")


def main():
    args = set(sys.argv[1:])
    if "--check" in args:
        verify()
        return
    text = load_env_text()
    for key, label, _prefix in TARGETS:
        text, changed = ask_and_store(text, key, label)
        if changed:
            ENV_PATH.write_text(text, encoding="utf-8")
            print(f"  {key} écrit dans .env ✅")
    verify()


if __name__ == "__main__":
    main()
