"""KIRA writes real code: the supervised build loop.

The scaffolder lays down templates; this module lets KIRA generate *custom*
files for a project. The flow is deliberately boring and observable:

1. ``plan_build`` asks the coding brain (KIRA_MODEL_CODE role, else the chat
   brain) for a file plan: [{path, purpose, content_hint}, ...].
2. ``generate_file`` writes ONE file's full content for the plan.
3. ``code_build`` orchestrates: per file, generate -> write (the registry's
   syntax guard rejects broken Python/JSON) -> on failure feed the error back
   to the model once. Every file is written through kira_code so the
   workspace jail and approval gate stay the ONLY trust boundary.
4. ``verify_build`` runs the project's entry file and captures output; the
   result is fed back in the next build round.

The model writes code; it never runs anything by itself and never leaves the
workspace. Everything is a tool: activity feed, validation, structured
failures — for free.
"""
from pathlib import Path
import json
import re

_MAX_FILES = 8
_MAX_ROUNDS = 3


def _code_brain():
    """(ask, provider_label) — the code role when configured, else chat."""
    try:
        import kira_ai
        provider, model = kira_ai.role_route("code")
        if provider:
            return (lambda prompt: _ask(prompt, provider, model)), f"{provider}:{model}"
    except Exception:
        pass
    try:
        import kira_ai
        provider, model = kira_ai.role_route("chat")
        if provider:
            return (lambda prompt: _ask(prompt, provider, model)), f"{provider}:{model}"
    except Exception:
        pass
    return None, ""


def _ask(prompt, provider, model):
    import kira_ai
    reply = kira_ai.chat(prompt, provider=provider, model=model, timeout=60,
                         options={"temperature": 0.2}, think=False)
    if not reply.ok:
        raise RuntimeError(reply.error or "model unavailable")
    return reply.text or ""


def _extract_json(text):
    """First JSON object/array in the reply (tolerates fences)."""
    match = re.search(r"[\[{].*[\]}]", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None


def plan_build(request, project=""):
    """[{path, purpose}] — the files KIRA intends to write, or an error."""
    brain, label = _code_brain()
    if brain is None:
        return {"ok": False, "error": "No AI brain available for planning.",
                "error_code": "brain_unavailable"}
    project = str(project or "").strip()
    prompt = (
        "You are a software architect. Reply with ONE JSON array only, no "
        "prose: [{\"path\": \"relative/file.py\", \"purpose\": \"what it does\", "
        "\"entry\": true}, ...]. Max 8 files. Include only code files worth "
        "generating (no binaries, no lock files). The entry file is the one "
        "to run first.\n"
        f"Project folder: {project or '(new)'}\n"
        f"Request: {request}\n"
        "JSON:"
    )
    try:
        plan = _extract_json(brain(prompt))
    except Exception as error:
        return {"ok": False, "error": str(error), "error_code": "plan_failed"}
    if not isinstance(plan, list) or not plan:
        return {"ok": False, "error": "The model returned no usable plan.",
                "error_code": "plan_empty"}
    files = []
    for row in plan[:_MAX_FILES]:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path", "")).strip().replace("\\", "/")
        if not path or ".." in path or path.startswith("/"):
            continue
        files.append({"path": path, "purpose": str(row.get("purpose", "")).strip(),
                      "entry": bool(row.get("entry"))})
    if not files:
        return {"ok": False, "error": "The plan contains no valid file paths.",
                "error_code": "plan_empty"}
    if not any(row.get("entry") for row in files):
        files[0]["entry"] = True
    return {"ok": True, "project": project, "files": files, "brain": label,
            "response": f"Plan: {len(files)} file(s) — " +
                        ", ".join(row["path"] for row in files)}


def generate_file(path, purpose, project="", context=""):
    """Full content of ONE file, written straight into the workspace.

    Consequential: goes through the approval gate like every write.
    """
    import kira_code
    brain, label = _code_brain()
    if brain is None:
        return {"ok": False, "error": "No AI brain available.",
                "error_code": "brain_unavailable"}
    target = project / path if project else path
    exists = ""
    try:
        resolved, failure = kira_code.resolve_path(str(target))
        if failure is None and resolved.exists():
            exists = resolved.read_text(encoding="utf-8", errors="replace")[:3000]
    except Exception:
        exists = ""
    prompt = (
        "You are a senior developer. Reply with the COMPLETE content of one "
        "file only — no explanations, no markdown fences, no commentary.\n"
        f"File path: {path}\n"
        f"What it must do: {purpose}\n"
        + (f"Current content to improve or fix:\n{exists}\n" if exists else "")
        + (f"Project context:\n{context}\n" if context else "")
        + "File content:"
    )
    try:
        content = brain(prompt)
    except Exception as error:
        return {"ok": False, "error": str(error), "error_code": "generation_failed"}
    # Strip accidental markdown fences.
    content = re.sub(r"^```[a-zA-Z0-9]*\n", "", content).replace("```", "").strip() + "\n"
    result = kira_code.write_file(str(target), content)
    if result.get("ok"):
        result["brain"] = label
        result["lines"] = content.count("\n")
    return result


def verify_build(project, entry):
    """Run the entry file once; (ok, output) for the feedback loop."""
    import kira_code
    relative = f"{project}/{entry}" if project else entry
    result = kira_code.run_command(f"{'python' if entry.endswith('.py') else 'node'} {relative}")
    return result.get("ok", False), str(result.get("output", ""))[:2000], result


def code_build(request, project=""):
    """The whole supervised loop. Returns a build report."""
    import kira_code
    if not str(request or "").strip():
        return {"ok": False, "error": "Describe what to build.",
                "error_code": "request_required"}
    project = str(project or "").strip().strip("\"'/\\")
    # The project folder must already exist in the workspace (scaffold first)
    # or be creatable as a new empty one.
    root = kira_code.workspace_root()
    folder = (root / project) if project else root
    if project and not folder.exists():
        created = kira_code.scaffold_project(project, template="empty")
        if not created.get("ok"):
            return created
    plan = plan_build(request, project)
    if not plan.get("ok"):
        return plan
    written, errors = [], []
    entry = next((row["path"] for row in plan["files"] if row.get("entry")),
                 plan["files"][0]["path"])
    context = f"Project: {project or 'workspace root'}. Request: {request}"
    for row in plan["files"]:
        result = generate_file(row["path"], row["purpose"] or request, project, context)
        if result.get("ok"):
            written.append({"path": row["path"], "bytes": result.get("bytes", 0),
                            "warning": result.get("warning", "")})
        else:
            # One self-fix round: feed the syntax/write error back.
            fix = generate_file(row["path"],
                                f"{row['purpose'] or request}\n"
                                f"Previous attempt failed with: {result.get('error', '')}. "
                                f"Return corrected complete file.",
                                project, context)
            if fix.get("ok"):
                written.append({"path": row["path"], "bytes": fix.get("bytes", 0),
                                "warning": fix.get("warning", "")})
            else:
                errors.append({"path": row["path"], "error": fix.get("error", "generation failed")})
    verified_ok, output, run_result = verify_build(project, Path(entry).name)
    report = {"ok": bool(written) and not errors, "project": project or ".",
              "files": written, "errors": errors, "entry": entry,
              "run_ok": verified_ok, "run_output": output[:800],
              "brain": plan.get("brain", ""),
              "response": _report_text(project, written, errors, verified_ok, output)}
    return report


def _report_text(project, written, errors, verified_ok, output):
    parts = []
    if written:
        listed = ", ".join(row["path"] for row in written)
        parts.append(f"{len(written)} fichier(s) écrit(s) : {listed}."
                     if True else f"Wrote {len(written)} file(s): {listed}.")
    if errors:
        parts.append("Échecs : " + ", ".join(f"{row['path']} ({row['error'][:60]})"
                                              for row in errors))
    if written and verified_ok:
        parts.append("Exécution : OK." if True else "Run: OK.")
        if output.strip():
            parts.append(f"Sortie : {output.strip()[:200]}")
    elif written:
        parts.append("Exécution en échec — voir la sortie." if True else "Run failed.")
        if output.strip():
            parts.append(f"Sortie : {output.strip()[:300]}")
    if not parts:
        return "Rien n'a été généré."
    return " ".join(parts)
