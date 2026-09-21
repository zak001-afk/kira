# Contributing to KIRA

Thanks for your interest! KIRA is a small personal project — contributions
that keep it **local-first, safe and readable** are the most welcome.

## Set up a dev environment

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Ground rules

1. **Tests must pass.** Run `pytest` before opening a PR. The suite stubs all
   hardware and Ollama, so it runs anywhere — if a test needs hardware,
   stub it in `tests/conftest.py` instead.
2. **Lint clean.** `ruff check .` should report no errors.
3. **Local-first.** Don't add cloud APIs or telemetry. New models must run
   through Ollama (or be optional).
4. **Safety:** anything that moves the mouse, clicks, types into other apps,
   locks the PC or changes system state must either route through
   `confirm_action` or be clearly user-initiated. Vision clicks must keep the
   locate → click → verify flow and respect `vision_click_confidence`.
5. **Small, focused PRs.** The backend is being gradually de-duplicated —
   prefer extracting small pure functions (easy to unit-test) over growing
   the big modules.

## Useful commands

```powershell
dev_mode.bat        # hot-restart dev loop (Windows)
pytest -q           # run tests
ruff check .        # lint
python scripts/setup_models.py   # fresh-machine model setup
```

Open an issue first for anything larger than a bug fix so we can agree on the
direction. Merci & chokran! 🙏
