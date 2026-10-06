"""KIRA's document memory: your files become searchable, locally.

Drop PDFs (soon), markdown and text notes into ``kira_docs/`` and every tool
that searches knowledge can find them. Deliberately RAG-*lite* for now:

- No embeddings dependency yet: a transparent keyword index (TF scoring) that
  runs anywhere. The ``kira_search_docs`` tool answers "qu'est-ce que j'ai
  noté sur le bail ?" today; upgrading the scorer to Ollama embeddings later
  changes nothing outside this module.
- Nothing ever leaves the machine: indexing and search are pure local files.
- Structured results ({ok, matches, ...}) like every other KIRA tool.
"""
from pathlib import Path
import math
import os
import re
from kira import paths

_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
_TEXT_EXTENSIONS = {".md", ".txt", ".py", ".js", ".json", ".html", ".css",
                    ".csv", ".log", ".yml", ".yaml", ".xml", ".rst"}
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_SNIPPET = 220

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]{2,}", re.IGNORECASE)
_STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "from", "have", "was", "are",
    "les", "des", "une", "est", "que", "qui", "pour", "dans", "sur", "avec",
    "pas", "plus", "cette", "aux", "mais", "nous", "vous", "elle", "tout",
}


def docs_root():
    """Where user documents live (KIRA_DOCS_DIR or kira_docs/)."""
    configured = str(os.environ.get("KIRA_DOCS_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return paths.root_path("kira_docs").resolve()


def _tokenize(text):
    return [token for token in _TOKEN_RE.findall(str(text or "").lower())
            if token not in _STOP_WORDS and len(token) > 2]


def _iter_files(base):
    for current, directories, names in os.walk(base):
        directories[:] = [d for d in directories if d not in _SKIP_DIRS]
        for name in names:
            candidate = Path(current) / name
            if candidate.suffix.lower() in _TEXT_EXTENSIONS and \
                    candidate.stat().st_size <= _MAX_FILE_BYTES:
                yield candidate


def _chunk_text(text, size=900, overlap=120):
    """Readable paragraph-ish chunks so matches can be quoted."""
    text = re.sub(r"\r\n", "\n", str(text or ""))
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size - 200, end)
            if cut > start + 200:
                end = cut + 1
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [chunk for chunk in chunks if chunk]


def _snippet(chunk, query_tokens, limit=_MAX_SNIPPET):
    lowered = chunk.lower()
    best, best_score = 0, -1
    for index in range(0, max(1, len(chunk) - 40), 20):
        window = lowered[index:index + 160]
        score = sum(window.count(token) for token in query_tokens)
        if score > best_score:
            best_score, best = score, index
    snippet = chunk[best:best + limit].strip()
    return snippet + "…" if best + limit < len(chunk) else snippet


def add_document(path, content=""):
    """Save a note into kira_docs/ (the voice/UI 'note this' path)."""
    relative = str(path or "").strip().replace("\\", "/")
    if not relative or ".." in relative or relative.startswith("/"):
        return {"ok": False, "error": "A relative file name is required.",
                "error_code": "invalid_name"}
    target = docs_root() / relative
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content or ""), encoding="utf-8")
        return {"ok": True, "path": target.name, "bytes": target.stat().st_size,
                "response": f"Note saved: {target.name} ({target.stat().st_size} bytes)"}
    except OSError as error:
        return {"ok": False, "error": str(error), "error_code": "write_failed"}


def search_docs(query, limit=4):
    """Keyword-scored search over kira_docs/ — {ok, matches: [{doc, snippet, score}]}."""
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "error": "A search query is required.",
                "error_code": "query_required"}
    tokens = _tokenize(query)
    base = docs_root()
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "matches": [], "count": 0, "docs_scanned": 0,
                "response": "The documents folder is empty — add files to kira_docs/."}
    matches = []
    scanned = 0
    for candidate in _iter_files(base):
        scanned += 1
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        chunks = _chunk_text(text)
        file_tokens = _tokenize(text)
        file_counts = {}
        for token in file_tokens:
            file_counts[token] = file_counts.get(token, 0) + 1
        for index, chunk in enumerate(chunks, 1):
            chunk_tokens = _tokenize(chunk)
            if not chunk_tokens:
                continue
            score = 0.0
            for token in set(tokens):
                hits = chunk_tokens.count(token)
                if hits:
                    score += (1 + math.log(hits)) * (1 + math.log(
                        1 + file_counts.get(token, 0) / max(1, len(file_tokens) // 200 + 1)))
            if score > 0:
                relative = candidate.relative_to(base).as_posix()
                matches.append({"doc": relative, "chunk": index,
                                "snippet": _snippet(chunk, tokens),
                                "score": round(score, 2)})
    matches.sort(key=lambda row: row["score"], reverse=True)
    matches = matches[:max(1, min(int(limit or 4), 10))]
    for rank, match in enumerate(matches, 1):
        match["rank"] = rank
    if not matches:
        return {"ok": True, "matches": [], "count": 0, "docs_scanned": scanned,
                "response": f"Nothing about “{query}” in your documents ({scanned} scanned)."}
    listed = "\n".join(f"- {match['doc']} (chunk {match['chunk']}): {match['snippet'][:100]}…"
                       for match in matches[:3])
    return {"ok": True, "matches": matches, "count": len(matches),
            "docs_scanned": scanned,
            "response": f"{len(matches)} extrait(s) de vos documents pour « {query} » :\n{listed}"
                        if True else listed}


def list_documents():
    """Inventory of kira_docs/ for the UI."""
    base = docs_root()
    if not base.exists():
        return {"ok": True, "documents": [], "count": 0,
                "response": "No documents folder yet."}
    documents = []
    for candidate in _iter_files(base):
        try:
            documents.append({"name": candidate.relative_to(base).as_posix(),
                              "bytes": candidate.stat().st_size})
        except OSError:
            continue
    documents.sort(key=lambda row: row["name"])
    return {"ok": True, "documents": documents, "count": len(documents),
            "response": f"{len(documents)} document(s) dans kira_docs/."}
