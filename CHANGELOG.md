# Changelog

All notable changes to KIRA are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [2.0.0] — 2026-09-21

### Added
- **Test suite**: 169 pytest tests covering the command parser (EN/FR/AR),
  text processing, vision intent detection, action execution, persistent
  memory, and config loading. Hardware-adjacent dependencies (pyautogui,
  audio, Ollama, pyttsx3) are stubbed, so tests run anywhere.
- **CI**: GitHub Actions workflow — lint, compile check and tests on
  Ubuntu + Windows × Python 3.11/3.12, plus a Windows dependency-resolution
  check.
- `scripts/setup_models.py`: one-command setup that checks/starts Ollama,
  pulls the configured chat + vision models, and optionally downloads a Vosk
  offline speech model and wires `offline_model_path`.
- `pyproject.toml` (project metadata, pytest + ruff config), `requirements-dev.txt`,
  `.env.example`, `CONTRIBUTING.md`, MIT `LICENSE`, proper `README.md` with
  setup, voice-command reference and troubleshooting.
- Wake-word tolerance: "kira, open chrome" / "kira: open chrome" now parse
  (separators after the wake word are stripped).

### Fixed
- `requirements.txt` was missing `customtkinter` and `Pillow` — a fresh clone
  could not start the UI. The file is now complete with pinned ranges.
- Wake-word normalization no longer leaves a leading ", " that broke parsing.

### Removed
- Dead code: `kira_theme.py` (unused 1,100-line UI prototype), the orphaned
  Three.js `ui/` experiment, duplicated icon files, duplicated/unreachable
  blocks in `kira_voice_agent.py` (double `forget_patterns` pass, unreachable
  returns).
- Patch-note readmes (`README.txt`, `README_DEV_MODE.txt`) — replaced by real
  docs.

### Changed
- UI palette constants renamed to semantic names (`CYAN/GREEN/PURPLE/BLUE`
  were all shades of red → `ACCENT`/`ACCENT_ALT`/`ACCENT_HOT`/`ACCENT_WARM`).
- `build_kira.bat` now builds from `KIRA.spec` instead of duplicating flags.

## [1.0.0] — initial import

Local voice assistant: Ollama chat + vision models, Vosk offline STT, rule-based
multilingual command parser, customtkinter UI, SQLite memory, PyInstaller build.
