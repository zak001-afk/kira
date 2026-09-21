# Changelog

All notable changes to KIRA are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [2.2.0] — 2026-09-21

### Added
- **The agent's mind** (`kira_thought.py`): commands the parser can't handle
  now run through an explicit *think → act → reflect* loop.
  - **Think**: recall agent memory first (exact + fuzzy command matching),
    then plan with the local LLM inside a `{"thought", "action"}` envelope.
    Every action — including nested sequence steps — is validated against a
    whitelist before execution. The thought is displayed in the UI as a dim
    `MIND` chat line (and in `kira.log`), never spoken.
  - **Agent memory** (new SQLite tables): `agent_episodes` (understanding,
    plan, action, outcome per command) and `agent_learnings` (command →
    action with success/failure counters).
  - **Reflect**: successes strengthen a mapping — the next identical or
    similar command is executed instantly with *no model call*. Failures
    demote it, and once failures level with successes the mapping becomes
    ineligible again: KIRA stops repeating mistakes (reflexion).
- New commands: **"what did you learn"** (lists learned commands, EN/FR/AR)
  and **"forget what you learned"** (wipes the learnings).
- 33 new tests: episode/learning CRUD, fuzzy recall, envelope parsing,
  reflexion (tie-breaking against reuse), end-to-end plan→act→learn→recall,
  and the new voice commands. **323 tests passing.**

### Changed
- UI chat panel gains a `MIND` (muted) line type for the thought trace;
  the legacy one-shot `ask_agent` planner remains for compatibility but the
  CLI and UI loops now think via `kira_thought`.

## [2.1.0] — 2026-09-21

### Added
- **Calculator** (`kira_calculator.py`): "calculate 2 to the power of 10",
  "what is 15% of 200", spoken numbers ("twenty five times two") in EN/FR/AR —
  evaluated through a strict AST whitelist, never raw `eval`.
- **Reminders** (`kira_reminders.py`): "remind me in 5 minutes to call mom",
  "rappelle-moi dans 2 heures de …", "ذكرني بعد 10 دقائق …", plus
  list/cancel commands. Daemon timers, spoken on fire.
- **Known websites**: "open github / gmail / stack overflow / netflix…"
  routes to URLs (works after `ouvrir` too). Users can register their own
  apps and sites via the new `app_aliases` and `websites` config keys.
- **Configurable confirmations**: `require_confirmation` in config controls
  which actions ask for voice confirmation (empty list disables prompts).
- **121 new tests**: LLM agent JSON extraction (fences, prose, garbage,
  outages), chat/memory deterministic flows, the full vision
  locate → click → verify pipeline, calculator safety (injection attempts,
  exponent bombs), reminders scheduling/cancellation, routing regressions.

### Fixed
- **CLI never spoke text results**: `time`, `date`, `system info`,
  `read clipboard`, `help` and sequence summaries parsed and executed but
  `main()` discarded the spoken string (`continue` without `speak`). They are
  now announced, matching the UI behavior.
- **French/Arabic "open google/youtube"** tried to launch a non-existent
  `google.exe`; now opens the website like the English path.
- `require_wake_word: true` was silently ignored — it is now enforced
  (conversation mode keeps listening).

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
