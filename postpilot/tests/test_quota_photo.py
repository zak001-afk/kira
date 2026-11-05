"""Tests du quota de liens par exécution (rotation) et des photos Gemini.

Le moteur est UNIQUE : Gemini, authentifié par la connexion au compte
Google (OAuth e-mail). Aucun appel réseau dans les tests (client simulé),
et surtout : si Gemini est indisponible, l'agent REPORTE la publication —
il n'invente jamais d'image locale.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from postpilot import agent, config, gemini_auth, photo, store


def setup_function():
    config.ensure_dirs()
    store.save_links([])
    store.save_tasks([])
    # run_task exige un compte enregistré pour la plateforme
    store.upsert_account("facebook", "https://www.facebook.com/me",
                         status="connected")


def teardown_function():
    store.save_links([])
    store.save_tasks([])
    store.remove_account("facebook")
    for f in config.GENERATED.glob("*"):
        f.unlink(missing_ok=True)
    for f in config.GEMINI_DIR.glob("*"):
        f.unlink(missing_ok=True)
    store.save_settings({"gemini_email": "", "gemini_project": ""})


def _mk_links(n: int) -> list[dict]:
    items = [store.add_link(f"https://www.facebook.com/groups/g{i}")[0]
             for i in range(n)]
    store.set_link_selection([i["id"] for i in items])
    return items


def _fake_platform(monkeypatch, captured: list):
    """Remplace la plateforme : publish() note les liens reçus."""
    class _Mod:
        @staticmethod
        def publish(task):
            captured.append(list(task.get("link_urls") or []))
            return {"ok": True, "message": "ok"}

    monkeypatch.setattr(agent, "platform_module", lambda p: _Mod)


def _mk_task(extra: dict) -> dict:
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur Facebook",
        {"content": "bonjour", **extra})
    assert res["ok"], res.get("message")
    return res["task"]


# ── Feature 1 : quota + rotation ──────────────────────────────────────────
def test_task_stores_quota_and_pretty():
    _mk_links(3)                              # cibles cochées → cible « links »
    t = _mk_task({"max_targets": 2, "pretty_photo": True})
    assert t["max_targets"] == 2
    assert t["pretty_photo"] is True
    assert "2 liens/exécution" in t["summary"]
    assert "photo présentable" in t["summary"]


def test_quota_rejects_invalid_values():
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur Facebook",
        {"content": "x", "max_targets": -5})
    assert res["ok"] is False and "0 (tous) à 1000" in res["message"]
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur Facebook",
        {"content": "x", "max_targets": 99999})
    assert res["ok"] is False


def test_quota_rotation_picks_next_lot(monkeypatch):
    """400-style : 7 groupes cochés, quota 3 → lots tournants sans doublon."""
    _mk_links(7)
    captured: list = []
    _fake_platform(monkeypatch, captured)

    t = _mk_task({"target": "links", "max_targets": 3})
    for _ in range(3):                       # 3 exécutions consécutives
        store.update_task(t["id"], enabled=True)
        agent.run_task(next(x for x in store.tasks() if x["id"] == t["id"]))

    assert [len(c) for c in captured] == [3, 3, 3]
    all_urls = [u for c in captured for u in c]
    # rotation continue : le 2e lot suit le 1er, le 3e enveloppe au début
    assert captured[0] == [f"https://www.facebook.com/groups/g{i}"
                           for i in (0, 1, 2)]
    assert captured[1] == [f"https://www.facebook.com/groups/g{i}"
                           for i in (3, 4, 5)]
    assert captured[2] == [f"https://www.facebook.com/groups/g{i}"
                           for i in (6, 0, 1)]
    assert len(set(all_urls)) == 7           # tous les groupes couverts


def test_quota_zero_uses_all_links(monkeypatch):
    _mk_links(4)
    captured: list = []
    _fake_platform(monkeypatch, captured)
    t = _mk_task({"target": "links", "max_targets": 0})
    agent.run_task(t)
    assert len(captured[0]) == 4             # quota 0 = tous les liens


def test_quota_larger_than_links_uses_all(monkeypatch):
    _mk_links(2)
    captured: list = []
    _fake_platform(monkeypatch, captured)
    t = _mk_task({"target": "links", "max_targets": 50})
    agent.run_task(t)
    assert len(captured[0]) == 2


def test_update_task_quota_and_pretty():
    t = _mk_task({})
    res = agent.update_task_fields(t["id"],
                                   {"max_targets": 5, "pretty_photo": True,
                                    "content": "salut"})
    assert res["ok"], res.get("message")
    cur = next(x for x in store.tasks() if x["id"] == t["id"])
    assert cur["max_targets"] == 5 and cur["pretty_photo"] is True
    bad = agent.update_task_fields(t["id"], {"max_targets": -1})
    assert bad["ok"] is False


# ── Feature 2 : photos Gemini (moteur unique, jamais de repli local) ─────
def _mk_raw(name="pot-de-miel.png") -> Path:
    p = config.MEDIA / name
    p.write_bytes(b"\x89PNG-fake")       # contenu quelconque : moteur simulé
    return p


def _fake_connected(email: str = "moi@gmail.com") -> Path:
    """Fait croire que le compte Google est déjà connecté (jeton factice)."""
    config.GEMINI_DIR.mkdir(parents=True, exist_ok=True)
    (config.GEMINI_DIR / "token.json").write_text(
        '{"token": "x", "refresh_token": "r", "client_id": "c", '
        '"client_secret": "s"}', encoding="utf-8")
    store.save_settings({"gemini_email": email})
    return config.GEMINI_DIR / "token.json"


class _FakeModels:
    """Simulateur du client Gemini : renvoie une image factice."""

    def __init__(self, fail_first_model: bool = False):
        self.calls: list[str] = []
        self.fail_first_model = fail_first_model

    def generate_content(self, model, contents):
        self.calls.append(model)
        if self.fail_first_model and len(self.calls) == 1:
            raise RuntimeError(f"models/{model} is not found "
                               f"for API version v1beta")
        blob = f"PNG-factice-{model}-{len(self.calls)}".encode()
        part = SimpleNamespace(inline_data=SimpleNamespace(data=blob))
        return SimpleNamespace(candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=[part]))])


class _FakeClient:
    def __init__(self, models):
        self.models = models


def test_generate_writes_distinct_files(monkeypatch):
    _fake_connected()
    monkeypatch.setattr(gemini_auth, "credentials", lambda: object())
    models = _FakeModels()
    monkeypatch.setattr(photo, "_client", lambda: _FakeClient(models))
    outs = photo.generate(_mk_raw(), count=2, log=False)
    assert len(outs) == 2 and outs[0] != outs[1]      # une NOUVELLE par appel
    for o in outs:
        assert o.exists() and o.parent == config.GENERATED
        assert o.read_bytes().startswith(b"PNG-factice")


def test_model_fallback_when_missing(monkeypatch):
    """Un modèle absent du compte → le suivant de la liste est essayé."""
    _fake_connected()
    monkeypatch.setattr(gemini_auth, "credentials", lambda: object())
    models = _FakeModels(fail_first_model=True)
    monkeypatch.setattr(photo, "_client", lambda: _FakeClient(models))
    outs = photo.generate(_mk_raw(name="fb.png"), log=False)
    assert len(outs) == 1
    assert models.calls[0] == photo.MODEL_CANDIDATES[0]
    assert models.calls[1] == photo.MODEL_CANDIDATES[1]


def test_generate_requires_connection():
    """Pas de compte connecté → erreur CLAIRE, jamais d'image locale."""
    with pytest.raises(photo.GeminiError) as ei:
        photo.generate(_mk_raw(name="brut.png"), log=False)
    assert "Connecter mon compte Google" in str(ei.value)


def test_billing_refusal_gives_clear_message(monkeypatch):
    """Google refuse (quota facturation) → le message parle facturation."""
    _fake_connected()

    class _Boom:
        def __init__(self):
            self.models = self           # client.models.generate_content(...)

        def generate_content(self, model, contents):
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED: Quota exceeded for metric: "
                "generate_content_free_tier_requests, limit: 0 — "
                "Please check your plan and billing")

    monkeypatch.setattr(gemini_auth, "credentials", lambda: object())
    monkeypatch.setattr(photo, "_client", lambda: _Boom())
    with pytest.raises(photo.GeminiError) as ei:
        photo.generate(_mk_raw(name="q.png"), log=False)
    assert "facturation" in str(ei.value)


def test_generate_rejects_missing_or_bad_file():
    bad = config.MEDIA / "cassé.png"
    bad.write_bytes(b"ceci n'est pas une image")
    with pytest.raises(photo.GeminiError):
        photo.generate(bad, log=False)
    with pytest.raises(photo.GeminiError):
        photo.generate(config.MEDIA / "absente.png", log=False)


def test_is_image():
    assert photo.is_image("a.jpg") and photo.is_image(Path("b.png"))
    assert not photo.is_image("c.mp4")


def test_take_task_photo_rotates_validated_list():
    """La liste validée par l'utilisateur est consommée poste par poste."""
    (config.GENERATED / "post-a.png").write_bytes(b"a")
    (config.GENERATED / "post-b.png").write_bytes(b"b")
    task = _mk_task({"photos": ["post-a.png", "post-b.png"]})
    got = [photo.take_task_photo(task, None, log=False).name
           for _ in range(3)]
    assert got == ["post-a.png", "post-b.png", "post-a.png"]
    fresh = next(x for x in store.tasks() if x["id"] == task["id"])
    assert fresh["photo_cursor"] == 3       # avance aussi sur le disque


def test_take_task_photo_generates_when_list_empty(monkeypatch):
    raw = _mk_raw(name="seul.png")
    out = config.GENERATED / "post-new.png"
    out.write_bytes(b"n")
    monkeypatch.setattr(photo, "generate", lambda *a, **k: [out])
    got = photo.take_task_photo({"id": "t1", "photos": []}, raw, log=False)
    assert got == out


def test_available_explains_when_not_connected():
    ok, why = photo.available({"photos": []})
    assert ok is False and "Connecter" in why
    (config.GENERATED / "post-v.png").write_bytes(b"v")
    ok, _why = photo.available({"photos": ["post-v.png"]})
    assert ok is True                       # liste validée suffit


def test_run_task_reports_when_gemini_unavailable():
    """VRAI module facebook : le contrôle part AVANT le moindre navigateur,
    et la publication est reportée — aucun lien n'est touché."""
    raw = _mk_raw(name="attente.png")
    t = _mk_task({"pretty_photo": True, "media": raw.name, "photos": []})
    res = agent.run_task(t)
    assert res["ok"] is False
    assert "reportée" in res["message"]


def test_task_stores_validated_photos_and_summary():
    t = _mk_task({"photos": ["post-1.png", "../evil.png", 42]})
    assert t["photos"] == ["post-1.png", "evil.png"]   # nom de fichier seul
    assert "2 photo(s) Gemini" in t["summary"]


def test_update_media_resets_photos():
    (config.GENERATED / "post-r.png").write_bytes(b"r")
    t = _mk_task({"media": "a.png", "photos": ["post-r.png"]})
    res = agent.update_task_fields(t["id"], {"media": "b.png"})
    assert res["ok"], res.get("message")
    cur = next(x for x in store.tasks() if x["id"] == t["id"])
    assert cur["photos"] == [] and cur["photo_cursor"] == 0


# ── Feature 3 : connexion au compte Google (OAuth, sans clé) ─────────────
def test_connect_start_needs_client_file():
    st = gemini_auth.connect_start()
    assert st["ok"] is False and "client_secret" in st["message"]


def test_client_secret_validation_and_status():
    ok, msg = gemini_auth.save_client_secret(b"pas du json")
    assert ok is False and "illisible" in msg
    ok, _msg = gemini_auth.save_client_secret(b'{"foo": 1}')
    assert ok is False
    good = (b'{"installed": {"client_id": "cid.apps.googleusercontent.com",'
            b' "project_id": "mon-projet-123", "client_secret": "s"}}')
    ok, msg = gemini_auth.save_client_secret(good)
    assert ok is True and "mon-projet-123" in msg
    st = gemini_auth.status()
    assert st["configured"] is True and st["project"] == "mon-projet-123"
    assert st["connected"] is False
    assert gemini_auth.project_id() == "mon-projet-123"


def test_status_and_disconnect_reset():
    _fake_connected("moi@test.com")
    st = gemini_auth.status()
    assert st["connected"] is True and st["email"] == "moi@test.com"
    res = gemini_auth.disconnect()
    assert res["ok"] is True
    assert gemini_auth.status()["connected"] is False


# ── Feature 4 : le prompt reste fidèle au produit, varié à chaque appel ──
def test_prompt_varies_but_never_touches_product():
    """Chaque post = une scène différente, ET la consigne de fidélité
    au produit (étiquette/couleurs/forme intouchées) est toujours là."""
    prompts = [photo._build_prompt()[0] for _ in range(40)]
    assert len(set(prompts)) >= 35
    for p in prompts:
        assert "STRICTE FIDÉLITÉ" in p          # produit intact
        assert "EXACTEMENT identiques" in p
        assert "carré" in p                     # format post


def test_prompt_scene_label_for_journal():
    prompt, label = photo._build_prompt()
    assert label and "·" in label               # étiquette lisible au journal
    assert len(prompt) > 200
