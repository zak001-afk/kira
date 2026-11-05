"""Photos de publication — générées DIRECTEMENT par Gemini (compte Google).

À partir de la photo brute de l'utilisateur (ex. un pot de miel avec son
étiquette), Gemini crée un visuel carré mis en scène dans une combinaison
de décor JAMAIS répétée, avec une consigne impérative de fidélité au
produit : le pot, son étiquette, ses couleurs et sa forme restent
exactement identiques.

- plus AUCUN moteur local : la génération passe exclusivement par l'API
  Gemini, authentifiée par la connexion au compte Google (voir
  gemini_auth.py) — aucune image n'est jamais « inventée » en local ;
- si Gemini est indisponible (compte non connecté, facturation inactive,
  quota dépassé), une `GeminiError` claire est levée : l'agent reporte
  alors la publication à l'exécution suivante, sans jamais publier une
  image de substitution.
"""
from __future__ import annotations

import base64
import random
import time
from pathlib import Path

from . import config, gemini_auth, store

GeminiError = gemini_auth.GeminiError

# modèles image « Gemini Pro » du meilleur au plus rapide : le premier
# disponible sur le compte est utilisé (les noms évoluent selon les
# périodes — la liste couvre les générations récentes)
MODEL_CANDIDATES = (
    "gemini-3.1-pro-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-3-flash-image",
    "gemini-2.5-flash-image",
)
GEMINI_MODEL = MODEL_CANDIDATES[0]      # modèle réellement utilisé

_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "webp": "image/webp", "bmp": "image/bmp"}

# variété des scènes Gemini : à CHAQUE appel, une combinaison jamais vue
# (lieu × accessoires × lumière × ambiance × cadrage = dizaines de
# milliers de possibilités) — mais le PRODUIT reste strictement identique
_SCENES = [
    "sur un plan de travail en bois rustique",
    "sur un marbre clair près d'une fenêtre",
    "au milieu d'un pré avec des fleurs sauvages",
    "sur une table en rotin dans un jardin ensoleillé",
    "dans une cuisine chaleureuse avec des planches en bois",
    "sur un fond dégradé studio aux tons miel",
    "sur une étagère en bois entourée de plantes vertes",
    "sur un torchon en lin froissé",
    "dans une caisse en bois d'un marché provençal",
    "près d'un rayon de miel brut sur une souche de bois",
    "sur un comptoir en granit sombre et élégant",
    "devant une fenêtre donnant sur un champ de fleurs",
    "sur un rebord de fenêtre baigné de lumière naturelle",
    "au milieu de ruches en bois dans un champ",
    "sur une nappe à carreaux dans un pique-nique",
]
_PROPS = [
    "une cuillère en bois coulante de miel",
    "un pot de miel ouvert à côté",
    "un morceau de rayon de miel brut",
    "des fleurs fraîches posées à côté",
    "quelques amandes et noix",
    "une tasse de thé fumante",
    "des pommes fraîches",
    "une branche de lavande séchée",
    "une bougie allumée en arrière-plan",
    "une ruche décorative en bois",
    "une serviette en lin et un livre ancien",
    "quelques feuilles de eucalyptus",
]
_LIGHTS = [
    "lumière dorée de fin d'après-midi",
    "lumière douce du matin par la fenêtre",
    "éclairage studio doux et diffus",
    "ombres franches et soleil vif de midi",
    "lumière chaude de fin de journée en extérieur",
    "lumière rasante qui révèle les textures",
]
_MOODS = [
    "tons miel et crème",
    "tons verts sauge et naturels",
    "tons terracotta chaleureux",
    "tons bleu canard et or",
    "tons rose poudré doux",
    "tons émeraude et bois",
    "palette claire et épurée",
    "ambiance automnale chaleureuse",
]
_ANGLES = [
    "cadrage carré, produit au centre net",
    "légère plongée à 30°",
    "vue de face au niveau de la table",
    "contre-plongée douce valorisante",
    "composition décentrée, règle des tiers",
]

# contrainte de fidélité — TOUJOURS la même, impérative
_FIDELITY = (
    "STRICTE FIDÉLITÉ au produit de la photo d'origine : étiquette, texte, "
    "logo, couleurs, forme et taille doivent rester EXACTEMENT identiques — "
    "ne rien modifier, ne rien recolorer, ne rien déformer, aucun texte ajouté, "
    "traduit, retiré ou reformulé sur l'étiquette. Le pot lui-même reste "
    "identique, comme si c'était le même objet photographié dans un nouveau décor. "
    "Aucun cadre blanc ni collage : une vraie photo, cohérente et photoréaliste.")

_last_scene: str = ""          # mémoire de session : pas 2× la même scène


def _build_prompt() -> tuple[str, str]:
    """Prompt Gemini + étiquette courte de la scène (pour le journal).

    Chaque appel pioche une combinaison inédite (lieu, accessoires, lumière,
    ambiance, cadrage) — deux publications successives ne peuvent donc PAS
    recevoir la même image de décoration.
    """
    global _last_scene
    scene = props = light = mood = angle = sig = ""
    for _ in range(12):                    # cherche une scène non répétée
        scene = random.choice(_SCENES)
        props = " et ".join(random.sample(_PROPS, 2))
        light = random.choice(_LIGHTS)
        mood = random.choice(_MOODS)
        angle = random.choice(_ANGLES)
        sig = "|".join((scene, props, light, mood, angle))
        if sig != _last_scene:
            break
    _last_scene = sig
    prompt = ("Photo produit professionnelle pour publication sur les réseaux "
              "sociaux, format carré : le même produit que sur la photo "
              "d'origine, mis en scène " + scene + ", accompagné de " + props
              + ". " + light + ". Ambiance : " + mood + ". " + angle
              + ". Arrière-plan naturellement flou (bokeh doux), rendu "
              "photoréaliste haut de gamme. " + _FIDELITY)
    label = f"{scene.replace('sur ', '').replace('dans ', '')} · {props}"
    return prompt, label


def is_image(path: Path | str) -> bool:
    return Path(path).suffix.lower() in _IMG_EXTS


# ── appel Gemini (OAuth du compte Google, jamais de clé) ─────────────────
def _client():
    from google import genai
    return genai.Client(credentials=gemini_auth.credentials(),
                        project=gemini_auth.project_id() or None)


def _part_from(raw: Path):
    from google.genai import types
    mime = _MIME.get(raw.suffix.lower().lstrip("."), "image/jpeg")
    return types.Part.from_bytes(data=raw.read_bytes(), mime_type=mime)


def _resp_image(resp) -> bytes | None:
    """Première image (bytes) d'une réponse generate_content."""
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None) \
                or getattr(part, "inlineData", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                return (base64.b64decode(data) if isinstance(data, str)
                        else bytes(data))
    return None


def _is_unknown_model(exc) -> bool:
    s = str(exc).lower()
    return ("is not found" in s or "not found for api version" in s
            or "unsupported model" in s or "has no associated model" in s)


def _translate(exc) -> str:
    """Message français clair selon la nature du refus de Gemini."""
    s = str(exc)
    low = s.lower()
    if "limit: 0" in s or ("quota" in low and
                           ("billing" in low or "plan" in low)):
        return ("Google n'autorise pas encore les images sur ce compte : "
                "activez la facturation du projet Google (aistudio.google.com"
                " → Settings → Billing) — la connexion e-mail est bonne, "
                "seule la facturation Google manque.")
    if "429" in s or "resource_exhausted" in low or "quota" in low:
        return ("Quota Gemini temporairement dépassé — réessayez dans "
                "quelques minutes (la prochaine exécution s'en charge).")
    if ("401" in s or "403" in s or "unauthenticated" in low
            or "permission denied" in low or "forbidden" in low):
        return ("Connexion Google refusée — recliquez sur « Connecter mon "
                "compte Google » dans PostPilot.")
    return "Gemini : " + s[:170]


def _one(raw: Path, prompt: str, client=None) -> Path:
    """UNE image Gemini — lève `GeminiError` si rien n'est disponible."""
    global GEMINI_MODEL
    client = client or _client()
    last = ""
    for model in MODEL_CANDIDATES:
        try:
            resp = client.models.generate_content(
                model=model, contents=[prompt, _part_from(raw)])
        except GeminiError:
            raise
        except Exception as exc:
            if _is_unknown_model(exc):      # modèle absent du compte → suivant
                last = str(exc)
                continue
            raise GeminiError(_translate(exc)) from exc
        blob = _resp_image(resp)
        if not blob:
            last = "aucune image dans la réponse"
            continue
        config.GENERATED.mkdir(parents=True, exist_ok=True)
        out = config.GENERATED / (f"post-{time.strftime('%Y%m%d-%H%M%S')}"
                                  f"-{random.randrange(1000, 9999)}.png")
        out.write_bytes(blob)
        GEMINI_MODEL = model
        return out
    raise GeminiError("Aucun modèle image disponible sur ce compte ("
                      + (last[:90] or "inconnu") + ")")


def _prune(keep: int = 300) -> None:
    """Garde seulement les `keep` dernières images générées sur le disque."""
    try:
        files = sorted(config.GENERATED.glob("post-*"),
                       key=lambda p: p.stat().st_mtime)
        for p in files[:-keep]:
            p.unlink()
    except OSError:
        pass


def generate(raw: Path | str, count: int = 1, log: bool = True) -> list[Path]:
    """`count` photos présentables DISTINCTES — Gemini uniquement.

    Lève `GeminiError` (message clair) si le compte n'est pas connecté ou
    si Google refuse : aucun repli local, l'agent reporte la publication.
    """
    raw = Path(raw)
    if not str(raw).strip() or not raw.exists():
        raise GeminiError("Photo brute introuvable — insérez-la d'abord "
                          "dans le champ Média (bouton +).")
    if not is_image(raw):
        raise GeminiError("Ce fichier n'est pas une image (photo brute "
                          "attendue).")
    gemini_auth.credentials()          # vérifie TÔT la connexion (erreur claire)
    outs: list[Path] = []
    for _ in range(max(1, int(count))):
        prompt, label = _build_prompt()
        t0 = time.time()
        out = _one(raw, prompt)
        outs.append(out)
        if log:
            store.log(f"✨ Photo Gemini générée en {time.time() - t0:.1f} s : "
                      f"{out.name} — scène : {label}", source="photo")
    _prune()
    return outs


# ── photos validées par l'utilisateur (galerie) ──────────────────────────
def gallery_of(task: dict) -> list[str]:
    """Photos validées par l'utilisateur qui existent encore sur le disque."""
    return [n for n in (task.get("photos") or [])
            if isinstance(n, str) and n.strip()
            and (config.GENERATED / Path(n).name).exists()]


def available(task: dict | None = None) -> tuple[bool, str]:
    """(disponible, raison) — la tâche peut-elle obtenir sa photo ?"""
    if task and gallery_of(task):
        return True, ""
    if not gemini_auth.connected():
        return False, "compte Google non connecté — cliquez sur « Connecter " \
                       "mon compte Google » (section Connexion Gemini)"
    return True, ""


def take_task_photo(task: dict, media: Path | None,
                    log: bool = True) -> Path | None:
    """Photo du PROCHAIN poste : pioche dans la liste validée par
    l'utilisateur (rotation), ou en génère une nouvelle si la liste est
    épuisée.

    Retourne None quand rien n'est à préparer (aucun média image, pas de
    photo demandée). Lève `GeminiError` si Gemini doit travailler mais est
    indisponible — l'agent reporte alors la publication.
    """
    photos = gallery_of(task)
    if photos:
        cur = int(task.get("photo_cursor") or 0)
        name = Path(photos[cur % len(photos)]).name
        task["photo_cursor"] = cur + 1      # visible dès cette exécution
        if task.get("id"):
            store.update_task(task["id"], photo_cursor=cur + 1)
        return config.GENERATED / name
    if media is None or not is_image(media):
        return None
    return generate(media, count=1, log=log)[0]
