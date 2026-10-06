"""Configuration de l'agent Atlas.

Charge le `.env` du projet, détecte le cerveau LLM disponible
(Ollama local par défaut, cloud optionnel si une clé existe) et fixe
les budgets de contexte selon le modèle choisi.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _load_kira_env() -> None:
    """Réutilise les clés cloud déjà déposées dans kira/.env (optionnel).

    Conditions : aucune clé cloud dans ce projet ET (opt-in cloud de KIRA
    `KIRA_CLOUD_AI=1` ou `ATLAS_ALLOW_KIRA_KEYS=1` ici). Les valeurs du
    `.env` du projet restent prioritaires.
    """
    cloud_keys = ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY",
                  "OPENAI_API_KEY")
    if any(_env(k) for k in cloud_keys):
        return
    kira_path = ROOT.parent / "kira" / ".env"
    if not kira_path.is_file():
        return
    entries: dict[str, str] = {}
    for line in kira_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        entries[key.strip()] = value.strip().strip('"').strip("'")
    gate = (entries.get("KIRA_CLOUD_AI", "") or "").lower()
    allowed = gate in ("1", "true", "yes", "on")
    if _env("ATLAS_ALLOW_KIRA_KEYS").lower() in ("1", "true", "yes", "on"):
        allowed = True
    if not allowed or not any(entries.get(k) for k in cloud_keys):
        return
    for key, value in entries.items():
        if value and key not in os.environ:
            os.environ[key] = value
    print("[atlas] clés cloud réutilisées depuis kira/.env (opt-in KIRA actif).")


_load_kira_env()


def _cloud_candidates() -> list[dict]:
    """Fournisseurs cloud compatibles OpenAI, par ordre de priorité."""
    candidates: list[dict] = []
    if _env("GROQ_API_KEY"):
        candidates.append({
            "name": "groq",
            "label": "Groq",
            "base_url": _env("ATLAS_GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            "api_key": _env("GROQ_API_KEY"),
            "model": _env("ATLAS_GROQ_MODEL", "llama-3.3-70b-versatile"),
        })
    if _env("OPENROUTER_API_KEY"):
        candidates.append({
            "name": "openrouter",
            "label": "OpenRouter",
            "base_url": _env("ATLAS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "api_key": _env("OPENROUTER_API_KEY"),
            "model": _env("ATLAS_OPENROUTER_MODEL", "deepseek/deepseek-chat-v3.1:free"),
        })
    if _env("GEMINI_API_KEY"):
        candidates.append({
            "name": "gemini",
            "label": "Gemini",
            "base_url": _env("ATLAS_GEMINI_BASE_URL",
                              "https://generativelanguage.googleapis.com/v1beta/openai"),
            "api_key": _env("GEMINI_API_KEY"),
            "model": _env("ATLAS_GEMINI_MODEL", "gemini-3.6-flash"),
            # Secours en cas de saturation du modèle principal (HTTP 503),
            # du plus rapide au plus complet — la vitesse prime.
            "models": [m.strip() for m in _env(
                "ATLAS_GEMINI_MODELS",
                "gemini-3.5-flash-lite, gemini-3.8-flash, gemini-3.1-flash-lite"
            ).split(",") if m.strip()],
        })
    if _env("OPENAI_API_KEY") or _env("ATLAS_OPENAI_BASE_URL"):
        candidates.append({
            "name": "openai",
            "label": "OpenAI-compatible",
            "base_url": _env("ATLAS_OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "api_key": _env("OPENAI_API_KEY"),
            "model": _env("ATLAS_OPENAI_MODEL", "gpt-4o-mini"),
        })
    return candidates


@dataclass
class Config:
    name: str
    kind: str                # "ollama" | "openai"
    provider_label: str
    model: str
    base_url: str = ""
    api_key: str = ""
    ollama_url: str = ""
    # Budgets de travail
    max_queries: int = 3
    search_per_query: int = 8
    max_sources: int = 8
    max_pages: int = 4
    page_chars: int = 1600
    snippet_chars: int = 170
    history_turns: int = 6
    num_ctx: int = 4096
    temperature: float = 0.4
    max_tokens: int = 900
    verbose: bool = False
    models: list = None          # modèles de secours (rotation si503)
    fallback: "Config | None" = None  # repli local si le cloud échoue

    @property
    def status_label(self) -> str:
        return f"{self.provider_label} · {self.model}"


def load_config() -> Config:
    """Résout le fournisseur LLM : explicite > auto (cloud si clé) > Ollama."""
    name = _env("ATLAS_NAME", "Atlas")
    choice = (_env("ATLAS_LLM_PROVIDER", "auto") or "auto").lower()
    candidates = _cloud_candidates()

    if choice in ("ollama", "local"):
        brain = None
    elif choice == "auto":
        brain = candidates[0] if candidates else None
    else:
        brain = next((c for c in candidates if c["name"] == choice), None)
        if brain is None and choice not in ("ollama", "local"):
            # Clé demandée mais absente : on retombe sur Ollama avec un avertissement.
            print(f"[atlas] clé introuvable pour '{choice}', utilisation d'Ollama en local.")

    local = Config(
        name=name,
        kind="ollama",
        provider_label="Ollama (local)",
        model=_env("ATLAS_OLLAMA_MODEL", _env("OLLAMA_MODEL", "qwen3:0.6b")),
        ollama_url=_env("ATLAS_OLLAMA_URL", _env("OLLAMA_URL", "http://127.0.0.1:11434")),
        num_ctx=int(_env("ATLAS_NUM_CTX", "4096")),
        # Le CPU est lent : on garde le prompt et la réponse courts.
        max_pages=3,
        page_chars=1200,
        snippet_chars=140,
        max_sources=8,
        max_tokens=800,
    )

    if brain is None:
        cfg = local
    else:
        cfg = Config(
            name=name,
            kind="openai",
            provider_label=brain["label"],
            model=brain["model"],
            base_url=brain["base_url"].rstrip("/"),
            api_key=brain["api_key"],
            # Le cloud a un grand contexte : on lit plus de pages, plus longues.
            # Plafonné pour rester rapide même les jours de forte demande.
            max_pages=6,
            page_chars=3200,
            snippet_chars=260,
            max_sources=12,
            num_ctx=0,
            models=list(brain.get("models") or []),
        )
        # Repli automatique : si le cloud tombe, Atlas répond en local.
        cfg.fallback = local

    # Surcharges manuelles.
    for attr, env in (("max_queries", "ATLAS_MAX_QUERIES"),
                      ("search_per_query", "ATLAS_SEARCH_PER_QUERY"),
                      ("max_pages", "ATLAS_MAX_PAGES"),
                      ("page_chars", "ATLAS_PAGE_CHARS"),
                      ("max_sources", "ATLAS_MAX_SOURCES"),
                      ("temperature", "ATLAS_TEMPERATURE")):
        raw = _env(env)
        if raw:
            try:
                setattr(cfg, attr, float(raw) if attr == "temperature" else int(raw))
            except ValueError:
                pass
    return cfg
