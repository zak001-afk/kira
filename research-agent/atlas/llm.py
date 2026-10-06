"""Cerveau de l'agent : streaming LLM local (Ollama) ou cloud OpenAI-compatible.

Robustesse cloud :
  - rotation automatique de modèles si le primaire est en503/saturation ;
  - retry sur429/500/502/503 avec backoff court ;
  - découverte du modèle si l'API répond 404 avec une suggestion ;
  - plafond de génération côté Ollama pour rester réactif.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator

import httpx

from .config import Config

_TIMEOUT = httpx.Timeout(30.0, connect=8.0)
_SSE_DATA = "data:"
_RETRY_STATUS = {429, 500, 502, 503}
_RETRY_DELAYS = (0.4, 1.2)        # backoff court par modèle (la rotation
                                    # vers le modèle suivant est plus rapide)
_MODEL_HINT = re.compile(r"use (?:models/)?([A-Za-z0-9._\-]+)")


def _candidates(cfg: Config) -> list[str]:
    """Modèle principal + modèles de secours (rotation en cas de saturation)."""
    seen: list[str] = []
    for model in [cfg.model, *(cfg.models or [])]:
        if model and model not in seen:
            seen.append(model)
    return seen


def stream_llm(cfg: Config, messages: list[dict]) -> Iterator[str]:
    """Itère les tokens de la réponse (boucle de génération en flux)."""
    if cfg.kind == "ollama":
        yield from _stream_ollama(cfg, messages)
    else:
        yield from _stream_openai(cfg, messages)


def complete(cfg: Config, messages: list[dict], timeout: float = 8.0,
             temperature: float = 0.2, attempts: int = 3) -> str:
    """Réponse courte non fluxée (planification).

    `attempts` s'applique par modèle candidat ; les cloud échouent vite et
    tournent, l'appelant doit rester dans son budget.
    """
    if cfg.kind == "ollama":
        return _complete_ollama(cfg, messages, timeout, temperature)
    for model in _candidates(cfg):
        for attempt in range(max(1, attempts)):
            try:
                resp = httpx.post(
                    f"{cfg.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                    json={"model": model, "messages": messages, "stream": False,
                          "temperature": temperature},
                    timeout=httpx.Timeout(timeout, connect=5.0),
                )
            except Exception:
                break  # modèle suivant
            if resp.status_code in _RETRY_STATUS:
                if attempt < attempts - 1:
                    time.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
                    continue
                break  # modèle suivant
            if resp.status_code == 404:
                hinted = _hinted_model(resp.text)
                if hinted and hinted != model:
                    model = hinted
                    continue
                break
            if resp.status_code >= 400:
                break
            try:
                content = resp.json()["choices"][0]["message"].get("content")
            except Exception:
                break
            if content:
                cfg.model = model  # mémorise le modèle qui répond
                return content
            break
    return ""


def _complete_ollama(cfg: Config, messages: list[dict], timeout: float,
                     temperature: float) -> str:
    try:
        resp = httpx.post(
            f"{cfg.ollama_url}/api/chat",
            json={"model": cfg.model, "messages": messages, "stream": False,
                  "think": False, "options": {"temperature": temperature,
                                              "num_ctx": cfg.num_ctx}},
            timeout=httpx.Timeout(timeout, connect=3.0),
        )
        resp.raise_for_status()
        return (resp.json().get("message", {}) or {}).get("content", "") or ""
    except Exception:
        return ""


def _hinted_model(body: str) -> str | None:
    """Extrait le modèle suggéré par une erreur 404 (« use models/xxx »)."""
    match = _MODEL_HINT.search(body)
    return match.group(1) if match else None


def _stream_ollama(cfg: Config, messages: list[dict]) -> Iterator[str]:
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": True,
        "think": False,  # qwen3 sans réflexion = réponses ~7x plus rapides
        "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx,
                    "num_predict": cfg.max_tokens},
    }
    with httpx.stream("POST", f"{cfg.ollama_url}/api/chat", json=payload,
                      timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("error"):
                raise RuntimeError(str(data["error"]))
            yield (data.get("message") or {}).get("content", "") or ""
            if data.get("done"):
                break


def _stream_openai(cfg: Config, messages: list[dict]) -> Iterator[str]:
    payload: dict = {"model": cfg.model, "messages": messages, "stream": True,
                     "temperature": cfg.temperature}
    last_error = "erreur inconnue"
    candidates = _candidates(cfg)

    for index, model in enumerate(candidates):
        payload["model"] = model
        for attempt in range(len(_RETRY_DELAYS) + 1):
            try:
                with httpx.stream(
                    "POST",
                    f"{cfg.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.api_key}",
                             "Accept": "text/event-stream"},
                    json=payload,
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status_code in _RETRY_STATUS:
                        last_error = (f"{cfg.provider_label} sature "
                                      f"(HTTP {resp.status_code}, modèle {model})")
                        if attempt < len(_RETRY_DELAYS):
                            time.sleep(_RETRY_DELAYS[attempt])
                            continue
                        break  # modèle suivant

                    if resp.status_code == 404:
                        body = resp.read().decode("utf-8", "replace")
                        hinted = _hinted_model(body)
                        if hinted and hinted not in candidates:
                            candidates.insert(index + 1, hinted)  # essai du suggéré
                        last_error = f"modèle {model} introuvable"
                        break  # modèle suivant

                    if resp.status_code >= 400:
                        body = resp.read().decode("utf-8", "replace")[:300]
                        raise RuntimeError(f"{cfg.provider_label} HTTP "
                                           f"{resp.status_code} : {body}")

                    emitted = False
                    saw_end = False
                    for line in resp.iter_lines():
                        if not line.startswith(_SSE_DATA):
                            continue
                        data = line[len(_SSE_DATA):].strip()
                        if data == "[DONE]":
                            saw_end = True
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        if (choices[0].get("finish_reason") or
                                (choices[0].get("delta") or {}).get("finish_reason")):
                            saw_end = True
                        content = (choices[0].get("delta") or {}).get("content")
                        if content:
                            emitted = True
                            yield content
                    if emitted:
                        cfg.model = model  # ce modèle a répondu : on le garde
                        if not saw_end:
                            # Connexion coupée en plein milieu : on ne présente
                            # pas une réponse tronquée comme une réponse finale.
                            raise RuntimeError("flux de réponse interrompu "
                                               "(connexion) — réessayez")
                        return
                    last_error = f"{model} a répondu vide"
                    break  # modèle suivant

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"{cfg.provider_label} : {type(exc).__name__} ({model})"
                if attempt < len(_RETRY_DELAYS):
                    time.sleep(_RETRY_DELAYS[attempt])
                    continue
                break  # modèle suivant
            except RuntimeError:
                raise  # erreur non transitoire : remontée telle quelle
        if index == len(candidates) - 1:
            break

    raise RuntimeError(f"{last_error} — réessayez, ou le cerveau local prendra "
                       "le relais.")
