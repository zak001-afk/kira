"""Tests des 3 demandes : champ « Exprimez-vous… », publication résiliente
(lien suivant en cas d'erreur, jamais de blocage), liste des liens en
difficulté, fenêtres en arrière-plan.

Aucun test ne touche à un vrai groupe : tout est simulé.
"""
from __future__ import annotations

import re

from postpilot import config, store
from postpilot.platforms import facebook as fb


def setup_function():
    config.ensure_dirs()
    store.save_links([])
    store.clear_link_errors()


def teardown_function():
    store.save_links([])
    store.clear_link_errors()


# ── 1. déclencheur « Exprimez-vous… » ─────────────────────────────────────
def test_trigger_matches_exprimez_vous():
    """Le déclencheur reconnaît « Exprimez-vous… » (groupe, page, profil)."""
    assert any(rx.search("Exprimez-vous…")
               for rx in fb._TRIGGER_RES)
    assert any(rx.search("Que voulez-vous dire ?")
               for rx in fb._TRIGGER_RES)


def test_trigger_never_matches_comments():
    """Surtout JAMAIS les commentaires : « Exprimez-vous dans les
    commentaires » ne doit pas correspondre au déclencheur."""
    for rx in fb._TRIGGER_RES:
        assert not rx.search("Exprimez-vous dans les commentaires"), \
            "le déclencheur ne doit jamais viser un commentaire"
        assert not rx.search("Exprimez-vous dans les commentaires…")
        assert not rx.search("Écrivez un commentaire")


def test_inline_box_filter_excludes_comments():
    """Le filtre JS du champ en ligne écarte commentaires et réponses."""
    # le code JS doit contenir les mots interdits + le test d'aria-label
    assert "commentaire" in fb._JS_NOT_COMMENT
    assert "closest('[aria-label]')" in fb._JS_NOT_COMMENT


# ── 2a. liste des liens en difficulté (persistance) ───────────────────────
def test_link_error_recorded_and_forgotten():
    store.add_link_error("https://www.facebook.com/groups/a",
                         "Champ de partage introuvable")
    errs = store.link_errors()
    assert len(errs) == 1
    assert errs[0]["url"] == "https://www.facebook.com/groups/a"
    assert "introuvable" in errs[0]["message"]
    assert errs[0]["ts"]

    # un lien qui réussit ensuite disparaît de la liste
    assert store.forget_link_error("https://www.facebook.com/groups/a") is True
    assert store.link_errors() == []
    assert store.forget_link_error("https://www.facebook.com/groups/a") is False


def test_link_error_upsert_by_url():
    store.add_link_error("https://www.facebook.com/groups/x", "erreur 1")
    store.add_link_error("https://www.facebook.com/groups/x", "erreur 2")
    errs = store.link_errors()
    assert len(errs) == 1                     # pas de doublon : upsert
    assert errs[0]["message"] == "erreur 2"


def test_link_errors_persist_across_restarts():
    store.add_link_error("https://www.facebook.com/groups/p", "page introuvable")
    # store.links()/link_errors() relisent le disque à chaque appel
    assert store.link_errors()[0]["url"] == "https://www.facebook.com/groups/p"


def test_clear_link_errors():
    store.add_link_error("https://www.facebook.com/groups/y", "e")
    assert store.clear_link_errors() is True
    assert store.link_errors() == []
    assert store.clear_link_errors() is False


# ── 2b. agrégation : jamais de blocage, on continue ──────────────────────
def test_aggregate_reports_partial_and_points_to_list():
    """1 échec sur 3 → le message indique la continuation + la liste."""
    results = [
        ("https://www.facebook.com/groups/1", {"ok": True}),
        ("https://www.facebook.com/groups/2", {"ok": False,
                                               "message": "partage interdit"}),
        ("https://www.facebook.com/groups/3", {"ok": True}),
    ]
    res = fb._aggregate(results, 3)
    assert res["ok"] is False
    assert "2/3" in res["message"]
    assert "continué" in res["message"]
    assert "Liens en difficulté" in res["message"]


def test_aggregate_all_ok():
    results = [(f"https://www.facebook.com/groups/{i}", {"ok": True})
               for i in range(4)]
    res = fb._aggregate(results, 4)
    assert res["ok"] is True
    assert "4 liens" in res["message"]


def test_aggregate_single_link_unchanged():
    """Un seul lien → résultat brut (comportement inchangé)."""
    res = fb._aggregate([("https://x", {"ok": False, "message": "boom"})], 1)
    assert res == {"ok": False, "message": "boom"}


# ── 3. fenêtres en arrière-plan ───────────────────────────────────────────
def test_windows_open_in_background_by_default():
    """Le mode par défaut est headless (aucun pop-up) ; visible sur demande."""
    import inspect
    from postpilot import browser
    sig = inspect.signature(browser._open_window_locked)
    assert sig.parameters["visible"].default is False
    sig2 = inspect.signature(browser.open_window_now)
    assert sig2.parameters["visible"].default is False


def test_register_account_has_visible_flag():
    import inspect
    from postpilot import agent
    sig = inspect.signature(agent.register_account)
    assert "visible" in sig.parameters
    assert sig.parameters["visible"].default is False
