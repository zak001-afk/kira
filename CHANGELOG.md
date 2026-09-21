# Changelog

All notable changes to KIRA are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [2.4.0] — 2026-09-21

### Added — project builder (`kira_builder.py`)
- **"build me a project that …"** turns an idea into a real project on disk:
  the model plans a strict JSON spec (name, language, files, test command),
  every file is generated, the tests run **for real**, and failures are
  repaired by showing the model its own code plus the exact error output.
- **It never claims success it did not verify**: the report distinguishes
  "tests passing" from "TESTS FAILING" and adds a diagnosis (missing module,
  syntax error, timeout, no tests collected) and the project location.
- **Safety**: file paths are validated before writing (no absolute paths, no
  `..` escapes, no drive letters); test commands are allow-listed to real
  test runners and executed without a shell; builds ask for confirmation and
  are never captured into macros.
- **Robustness**: an empty model response never overwrites working files; a
  tiny `conftest.py` bootstrap makes generated tests importable; bytecode
  caches are cleared before each run so a same-size fix in the same second is
  not masked by a stale `.pyc`; the repair loop stops early when the model has
  nothing further to change; model/disk errors are reported, never crash the
  agent.
- Supporting commands: **"fix the project"** (re-test and repair an existing
  project) and **"list my projects"**. New config: `projects_dir`,
  `builder_model`, `project_test_timeout`, `project_max_attempts`.

### Changed
- `pytest` moved into `requirements.txt` — KIRA runs tests for the projects
  it generates.

### Tests
- 79 new tests, including end-to-end builds that execute **real pytest** on
  generated code, a self-repair scenario, an honest-failure scenario, and a
  regression test for the stale-bytecode hazard. **580 passing.**

## [2.3.1] — 2026-09-21

### Changed
- **Charming is the new default personality** (`personality.humor: "charming"`):
  warm acknowledgements ("Consider it done, sir.", "Right away, sir.",
  "With pleasure, sir."), caring time-aware greetings ("Good morning sir. I
  hope you slept well — everything is ready for you.", "It's late, sir...
  do rest soon."), a welcoming boot closer, and gentle failure lines
  ("That didn't quite work, sir — no trouble at all, we'll find another
  way."). `neutral`, `dry` and `formal` remain available; unknown values
  fall back to charming.
- **A voice to match**: KIRA now selects the sweetest installed English
  voice — Windows 11 *Natural* voices first (Aria, Jenny, Michelle), then
  the older desktop voices — instead of a single hardcoded voice, and speaks
  slightly slower in charming mode (SAPI rate −1, pyttsx3 160 wpm vs 180).
  Voice scoring and pacing are pure, unit-tested functions.

### Fixed
- A failed or cancelled action now says so kindly instead of falling through
  to a default "Done" line (`build_reply("none")` was mis-routed).

### Removed
- Dead `build_acknowledgement()` helper (superseded by the personality
  layer's acknowledgement variants).

### Tests
- 13 new voice tests plus expanded personality coverage. **501 passing.**

## [2.3.0] — 2026-09-21

### Added — "suit mode": the JARVIS layer
- **Proactive watchdog** (`kira_monitor.py`): daemon thread sampling battery,
  CPU, memory and disk with localized spoken alerts, sustained-CPU logic and
  per-alert cooldowns. `enable/disable watchdog` commands; fully configurable
  under `monitor` in the config.
- **Self-awareness** (`kira_thought`): `systems check` (uptime, operations,
  success rate, skills, facts, model connectivity), `review your day` (daily
  episode review that names failures), `what do I usually do now?` (habit
  hint from episode hour distribution).
- **Learning on demand** (`kira_learning.py`): `learn this routine` records
  executed actions, `call it <name>` persists them as an atomic config
  shortcut, `stop learning` discards. `no, not that one` demotes the last
  learning (human-side reflexion).
- **Skill consolidation**: at `skill_promote_after` successful uses KIRA
  offers to promote a learning to a permanent shortcut; `make it a shortcut`
  / `skip the shortcut`.
- **Lab protocols** (`kira_security.py`): `secure the lab` locks the
  workstation and gates all commands behind a voice unlock with optional
  `lab_passphrase`; `eyes down` shows the desktop and mutes.
- **Undo** (`kira_undo.py`): `take that back` reverses the last reversible
  action (typing → Ctrl+Z, volume, mute, media, show-desktop) from a
  bounded stack.
- **Personality** (`kira_personality.py`): `personality.humor` —
  neutral / dry / formal; time-aware greetings; boot banner with memory
  counts followed by a spoken **morning briefing** (time, date, battery,
  pending reminders, `kira_briefing.py`).
- **Optional bridges**: `weather in <city>` via wttr.in (the only network
  feature, injectable for tests) and **Home Assistant** device control
  (`turn on the desk lamp`) — inert until configured.
- Backend/UI/gate integration: promotion follow-ups, macro capture, undo
  recording, watchdog lifecycle (`start_background_tasks`), locked-lab gate
  in both the CLI and the GUI routing.

### Changed
- Config additions (all optional): `personality`, `monitor`,
  `lab_passphrase`, `home_assistant`, `skill_promote_after`.
- `set_address` now persists through the new atomic `save_config()` helper.
- Startup sequence: status banner + briefing instead of two fixed lines.
- **153 new tests — 476 passing**, still fully stubbed hardware.

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
