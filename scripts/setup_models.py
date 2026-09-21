#!/usr/bin/env python3
"""One-time environment setup for KIRA.

Does three things, in order:

1. Verifies the Ollama server is reachable (starts `ollama serve` on demand).
2. Pulls the chat and vision models named in ``kira_config.json``.
3. Optionally downloads a small Vosk model for offline speech recognition
   and points ``offline_model_path`` at it.

Everything is stdlib-only so the script and its helpers can run anywhere.

Usage:
    python scripts/setup_models.py            # full guided setup
    python scripts/setup_models.py --yes      # no prompts
    python scripts/setup_models.py --skip-vosk
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "kira_config.json"
MODELS_DIR = ROOT / "models"

DEFAULT_CHAT_MODEL = "qwen3:0.6b"
DEFAULT_VISION_MODEL = "qwen3-vl:2b"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

VOSK_MODELS = {
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "fr": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
}
VOSK_DIR_NAMES = {
    "en": "vosk-model-small-en-us-0.15",
    "fr": "vosk-model-small-fr-0.22",
}


# ── config helpers (unit-testable) ──────────────────────────────────────────

def read_config_models(config_path: Path) -> tuple[str, str]:
    """Return (chat_model, vision_model), falling back to KIRA defaults."""
    chat, vision = DEFAULT_CHAT_MODEL, DEFAULT_VISION_MODEL
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            chat = str(data.get("model") or chat)
            vision = str(data.get("vision_model") or vision)
    except (OSError, json.JSONDecodeError):
        pass
    return chat, vision


def update_config_offline_path(config_path: Path, model_dir: Path) -> dict:
    """Write ``offline_model_path`` into the config, preserving other keys."""
    config_path = Path(config_path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data["offline_model_path"] = str(Path(model_dir))
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return data


# ── ollama helpers ───────────────────────────────────────────────────────────

def ollama_running(url: str = OLLAMA_TAGS_URL, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def start_ollama() -> bool:
    """Try to launch the Ollama server in the background."""
    exe = shutil.which("ollama")
    if not exe:
        return False
    try:
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    for _ in range(15):  # give the server a few seconds to come up
        if ollama_running():
            return True
        time.sleep(1)
    return ollama_running()


def pull_model(model: str) -> bool:
    exe = shutil.which("ollama")
    if not exe:
        print(f"  [skip] 'ollama' not found in PATH; pull '{model}' manually.")
        return False
    print(f"  Pulling {model} ...")
    result = subprocess.run([exe, "pull", model], check=False)
    return result.returncode == 0


# ── vosk helpers ─────────────────────────────────────────────────────────────

def download_vosk_model(lang: str, dest_dir: Path) -> Path | None:
    """Download and extract a small Vosk model; return its directory."""
    url = VOSK_MODELS[lang]
    target = Path(dest_dir) / VOSK_DIR_NAMES[lang]
    if target.is_dir():
        print(f"  Vosk model already present: {target}")
        return target
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    archive = Path(dest_dir) / (VOSK_DIR_NAMES[lang] + ".zip")
    print(f"  Downloading {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(
            archive, "wb"
        ) as fh:
            shutil.copyfileobj(response, fh, length=1024 * 256)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest_dir)
    except (urllib.error.URLError, OSError, zipfile.BadZipFile) as exc:
        print(f"  [error] Vosk download failed: {exc}")
        return None
    finally:
        archive.unlink(missing_ok=True)
    return target if target.is_dir() else None


# ── main flow ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up KIRA's local models.")
    parser.add_argument("--yes", action="store_true", help="answer yes to prompts")
    parser.add_argument("--skip-vosk", action="store_true", help="skip the offline STT model")
    parser.add_argument(
        "--vosk-lang",
        choices=sorted(VOSK_MODELS),
        default="en",
        help="Vosk language pack to download (default: en)",
    )
    args = parser.parse_args(argv)

    chat_model, vision_model = read_config_models(CONFIG_PATH)

    print("=" * 60)
    print("KIRA setup — local models")
    print("=" * 60)
    print(f"Config:  {CONFIG_PATH}")
    print(f"Chat:    {chat_model}")
    print(f"Vision:  {vision_model}")
    print()

    print("[1/3] Checking Ollama server...")
    if not ollama_running():
        print("  Not running; trying to start 'ollama serve'...")
        if not start_ollama():
            print(
                "  [error] Could not reach Ollama. Install it from https://ollama.com\n"
                "          and re-run this script."
            )
            return 1
    print("  Ollama is up.")

    print("[2/3] Pulling models (this can take a while)...")
    ok = pull_model(chat_model) & pull_model(vision_model)
    if not ok:
        print("  [warn] At least one model failed to pull; KIRA will still run")
        print("         its rule-based commands without them.")

    if args.skip_vosk:
        print("[3/3] Skipping Vosk offline speech model (--skip-vosk).")
    else:
        lang = args.vosk_lang
        if not args.yes:
            answer = input(
                f"[3/3] Download the {lang} Vosk model for offline speech? [Y/n] "
            ).strip().lower()
            if answer in {"n", "no"}:
                print("  Skipped. You can re-run with --vosk-lang later.")
                return 0
        target = download_vosk_model(lang, MODELS_DIR)
        if target:
            update_config_offline_path(CONFIG_PATH, target)
            print(f"  offline_model_path set to: {target}")

    print()
    print("Setup finished. Start KIRA with:  python kira_app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
