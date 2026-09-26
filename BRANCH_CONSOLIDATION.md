# Branch consolidation — MED takes priority

## Result and limits

The consolidation is on `arena/01a0df84-kira`. The intended final branch layout
is `main`, `zakaria`, and `arena/01a0df8a-kira-MED`. This session cannot create
or push to `zakaria` or delete other remote branches. No branches were deleted;
`main` and MED were not modified.

MED commit `0d358bd` is the design authority. Its French black/gold UI, avatar,
settings, and telemetry are retained. Integration changes to its frontend are
limited to a bundle identifier, same-origin API requests, and propagating the
selected voice language to both speech engines. This is not the competing
holographic cockpit interface.

## Branch decisions

| Source tip | Treatment |
| --- | --- |
| `main` / `42ceca5` | Already in the combined version. |
| `backend` / `e27325a` | Already ancestral; no additional changes required. |
| `arena/01a0c41a-kira` / `532dacd` | Already ancestral. |
| `arena/01a0c581-kira` / `d51ed83` | Already ancestral. |
| `arena/01a0dae2-kira` / `db4a04c` | Already ancestral; retain current privacy-checked Supabase code. |
| `arena/01a0df8a-kira-MED` / `0d358bd` | Already merged; wins UI conflicts. |
| `arena/01a0dab7-kira` / `20701c3` | History-only merge: earlier Supabase implementation superseded by current code. |
| `arena/01a0df3f-kira` / `dbb28c1` | History-only merge: duplicate learning/search/speech fixes superseded by shared, tested helpers. Legacy DDG import fallback not added. |
| `arena/01a0cf8b-kira` / `ed0b331` | History-only merge: competing face/interface replacement not activated. |
| `arena/01a0c549-kira` / `2540846` | History-only merge: obsolete `kira_server`/`kira_app` architecture not reinstated. Its guarded API and vision pipeline are NOT ported into the current server. Do not treat this consolidation as adding API authentication. |
| `arena/01a0cf97-kira` / `b4fd1f9` | Integrate file/app opening, multilingual command helpers, bounded-answer helpers, TTS word timing, packaging and same-origin serving. Preserve MED UI and telemetry, current Supabase safeguards, web learning, and emoji sanitation. |

A history-only merge retains the old commits for recovery but deliberately does
not activate their file changes. Git ancestry alone is not proof that every old
feature is enabled. Alternative UI modules/assets retained from cf97 are not
wired into the MED layout; its language-selection/lip controls are not exposed.

## Verification

- Python: `.venv/bin/python -m unittest discover -s tests -q`
- JavaScript: `node --test tests/*.test.mjs`
- Optional real browser: `python tests/cockpit_browser.py` (Playwright + Chromium;
  set `KIRA_TEST_BROWSER` to an existing browser if needed).
- Desktop hardware, live Ollama/search/Supabase, and Windows audio require a
  Windows acceptance test. Never expose the unauthenticated agent API publicly.

## Finish the three-branch layout on Windows

Pause pushes with your friend first. Start with a **clean** checkout; save local
work before continuing. Run these commands yourself, outside the fixed Arena
session. Keep `main` as GitHub's default branch.

```powershell
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
# Stop if fetch fails. Keep this backup outside the source tree.
git bundle create ..\kira-before-branch-cleanup.bundle --all
# Stop if backup fails. Verify it before deleting any branch.
git bundle verify ..\kira-before-branch-cleanup.bundle

git switch -c zakaria origin/arena/01a0df84-kira
git push -u origin zakaria
```

If `zakaria` already exists, STOP and inspect it instead of overwriting it.
Test the app and confirm your friend approves before cleanup. Do not reset
`main` to the consolidated version; open a reviewed PR from `zakaria` later.

Delete obsolete branches individually, only after checking their CURRENT tip:

```powershell
# Example; repeat only for branches you intend to retire.
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
git merge-base --is-ancestor origin/arena/01a0c41a-kira origin/zakaria
if ($LASTEXITCODE -eq 0) {
    git push origin --delete arena/01a0c41a-kira
} else {
    Write-Host 'STOP: branch has unmerged changes. Review it first.'
}
```

Retire these only after the same check (including the temporary consolidation
branch last): `arena/01a0c41a-kira`, `arena/01a0c549-kira`,
`arena/01a0c581-kira`, `arena/01a0cf8b-kira`, `arena/01a0cf97-kira`,
`arena/01a0dab7-kira`, `arena/01a0dae2-kira`, `arena/01a0df3f-kira`,
`backend`, `arena/01a0df84-kira`.

Do NOT delete `main`, `zakaria`, or `arena/01a0df8a-kira-MED`. Deleting a branch
can close its open PR; retain this document and the bundle as the audit trail.
Future Arena work must be in a new session associated with your desired branch;
this session remains fixed to its original branch.
