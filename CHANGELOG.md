# Changelog

All notable changes to KIRA are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [2.7.0] — 2026-09-21

### Changed — the desktop app is now the browser interface
- **One interface.** `main_window.py` (1,786 lines of customtkinter) is
  deleted. The app is `kira_app.py`: it starts `kira_server` in-process on an
  ephemeral `127.0.0.1` port, shows `ui/` in a native window through
  **pywebview** (Edge WebView2 on Windows), and shuts the server down when the
  window closes. The HUD is not copied, embedded or re-implemented — it *is*
  the interface, so every panel and every future fix lands once.
- **It degrades instead of failing.** No pywebview, or no WebView2 runtime →
  an app-mode Edge/Chrome window (`--app`, no tabs, no URL bar), configured to
  the same 1540×930. No Chromium-family browser either → the default browser.
  Whichever path runs, the microphone, the confirmation round-trip and the
  command pipeline are identical, because they live in `kira_server.py`.
- **The desktop chrome was ported into the HUD** rather than dropped, so the
  new app is not a smaller app: the module rail (Chat, Voice, Commands,
  Vision, Files, Tools, Memory, Settings), the five-state strip, the voice
  activity line, and the media bar with a 24-hour clock and date.
- Confirmation now behaves the same everywhere, because there is only one
  confirmation implementation left.
- Runtime dependencies shrink: `customtkinter` and `Pillow` are no longer
  needed by the app (`Pillow` moves to the dev requirements for the preview
  script); `pywebview` is added.
- `KIRA.spec` bundles `ui/` and pywebview; `dev.py` now watches `.html`,
  `.css`, `.js` and `.mjs`, so editing the interface restarts the window and
  reloads it.

### Added — the ported controls do real work
- **The rail is wired, not decorative.** Chat focuses the command bar; Voice
  opens the microphone; Commands focuses the bar and highlights the quick
  actions; Vision sends *"what is on my screen"*; Files opens the downloads
  folder; Memory asks *"what did you learn"*; Settings toggles voice output.
  **Tools is marked inert and says so** when clicked instead of pretending.
- **The media bar posts commands the parser already knows** (`previous track`,
  `play pause`, `next track`) — a test cross-checks every `data-command` in the
  markup against `parse_simple_command`, so a button that says nothing real
  cannot be shipped.
- `KiraService.watchdog_running` — a public answer to "is the watchdog up?",
  which the app's banner reports honestly.

### Fixed
- `scripts/check_ui.mjs` **awaited nothing**: an `async` check body escaped as
  an unhandled rejection, so a *failing* check could be counted as passing.
  Every check is now awaited, and the three failures it was hiding were fixed.
- The HUD clock is built by hand instead of via `toLocaleTimeString`, so it
  reads the same 24-hour time in every locale (it showed `07:00 PM` in some).
- `find_app_browser` no longer probes Windows install paths off Windows, where
  `%ProgramFiles%` can never expand (found by a test).
- **Offline mode no longer calls itself a simulation.** `KiraService.version`
  returned `"sim"` whenever the backend could not be imported, so a
  half-installed agent reported itself as a demo — and the ported sidebar
  displays that string. It now reads the version from `pyproject.toml`, which
  is also the one place the number is written down.

### Tests
- 730 tests (**728 passing, 2 skipped** without Pillow): the retired tkinter
  renderer's 9 canvas tests are replaced by 22 `kira_app` tests that drive the
  real shell — including one that opens the URL handed to the window and
  asserts the live HUD is being served there — plus 7 markup tests pinning the
  ported chrome. The Node smoke check grew from 29 to **38 checks** (media,
  clock, state strip, voice line, every rail module, and that an unwired
  module says so).

## [2.6.0] — 2026-09-21

### Added — the browser interface (`kira_server.py` + `ui/`)
- **KIRA now runs in a browser**, and it is the *same* agent: commands go
  through `normalize_command → lab gate → parser / think_about →
  confirmation → execute_action → learn_from`, then flow into the learning
  and undo subsystems. The page is a HUD, not a mock-up.
- **`kira_server.py`** — stdlib-only (`http.server`, threading) JSON API:
  `/api/state`, `/api/history`, `/api/health`, `/api/command`, `/api/listen`,
  `/api/reset`, plus static serving of `ui/` with a traversal guard.
  Flags: `--host`, `--port`, `--simulate`, `--open`, `--no-watchdog`.
- **A neural HUD in the Three.js style** (`ui/index.html`, `app.js`,
  `style.css`): a bloom-lit reactor of armour plates, orbital rings, a
  neural core and 450 particles over matrix rain — its spin, bloom, energy
  and rain speed follow KIRA's real state (READY / LISTENING / THINKING /
  CONFIRM / EXECUTING / SPEAKING / ERROR).
- **A conversation that tells the truth**: replies, your lines, the
  thinking layer's **inner monologue** (labelled, never spoken), failures in
  their own colour, and the system watchdog's unprompted alerts.
- **Real telemetry** — live CPU / memory / disk / battery, the active model,
  learned skills, operations and uptime, polled every 1.5 s.
- **Confirmation in the page** — sensitive actions come back as a question
  with CONFIRM / CANCEL instead of executing behind your back.
- **Voice both ways** — the MIC button uses KIRA's own offline recognition on
  the server; replies are spoken by the browser's Web Speech API, so voice
  works on any OS without extra dependencies (and without two voices talking
  over each other). Toggle: VOICE: ON/OFF.
- **Offline-first** — Three.js r180 is vendored in `ui/vendor/` (MIT),
  so no CDN is required. If the module or WebGL is missing, the reactor
  degrades to a CSS core and the HUD keeps working. `--simulate` is the only
  mode that invents replies, and it labels them everywhere.
- **Honest failure** — without the desktop dependencies the page still
  loads, the chip reads OFFLINE, and each command answers with the real
  import error.

### Fixed
- Confirming an action over HTTP now actually runs it (the browser sends an
  empty `text` with `confirm: true`, which used to be swallowed by the
  empty-command guard); confirmed executions are also recorded in history
  and return the correct mode/state.
- `--simulate` no longer loads the real backend, so demo mode is a true
  simulation even on a machine where the agent imports fine.
- Aborted browser requests (reloads, cancelled polls) no longer raise inside
  the server's request thread.

### Tests
- 80 new tests: the service routing pipeline against a fake backend (lab
  gate, chat fallback, LLM/memory plans, confirmation, learning promotion,
  failure handling), simulation and offline modes, the watchdog alert
  callback, telemetry shape, real HTTP endpoints over a live socket,
  traversal/extension defence, preview headers, aborted clients, vendored
  module graph (every import resolves, nothing reaches a CDN), markup
  structure and click-through CSS. A Node smoke check
  (`scripts/check_ui.mjs`, 29 checks) drives the real `ui/app.js` headlessly.
  **709 passing.**

## [2.5.0] — 2026-09-21

### Added — 3D holographic core (`kira_orb.py`)
- **A real 3D orb**, not a decorated circle: Fibonacci-sphere point cloud
  (430 points), 6 meridians + 4 latitude rings, an equatorial scan ring, a
  glowing core with rim light, and 10 satellites on true 3D orbits. Every
  primitive is perspective-projected (camera at 3.2) and depth-shaded —
  size, brightness and draw order all follow the normalized depth, so the
  sphere reads as a solid object with a near and far side.
- **Two-layer matrix rain**: dense/dim columns behind the orb and
  sparse/bright columns in front, so the sphere sits *inside* the rain.
  Each column is a stream — a white-hot head with a long fading tail — over
  a font-safe glyph alphabet (the previous katakana set rendered as blank
  boxes in common monospace fonts).
- **Pure maths, separately testable**: `kira_orb.py` has no tkinter/PIL
  imports, so geometry, projection, colour and rain are unit-tested directly.
- **Offline preview**: `scripts/render_orb_preview.py` renders the same
  frame to a PNG through Pillow (`--state`, `--phase`, `--filmstrip`), which
  is how the artwork in the README was produced — no display needed.
- Six UI states drive spin, tilt, pulse, rain speed and hue; `orb_quality`
  (high/balanced/low) caps the render budget, and layer counts also scale
  down automatically on small canvases.

### Changed
- The old 2D orb (flat rings, waveform-only core, scattered digits) is
  replaced; the bottom audio waveform is retained as its own renderer.

### Tests
- 49 new tests: geometry invariants (points on the sphere, no polar
  clustering, great circles), rotation/orthogonality, projection and
  depth-sorting, colour maths, rain determinism and tails, state profiles —
  plus the **real tkinter renderer driven through a fake canvas**, so the
  drawing path is executed and asserted without a display. **629 passing.**

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
