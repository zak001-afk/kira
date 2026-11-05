"""Tests du gestionnaire de liens : base, sélection, cibles de publication."""
from __future__ import annotations

from postpilot import agent, config, store
from postpilot.platforms import facebook as fb


def setup_function():
    config.ensure_dirs()
    store.save_links([])


def teardown_function():
    store.save_links([])


def test_add_link_ok_and_dedupe():
    res = agent.add_link("https://www.facebook.com/groups/miel")
    assert res["ok"] is True, res.get("message")
    assert res["created"] is True
    assert res["link"]["url"] == "https://www.facebook.com/groups/miel"
    assert res["link"]["selected"] is False      # l'utilisateur coche lui-même
    assert len(store.links()) == 1

    # même lien avec « / » final, query et fragment → PAS de doublon
    res2 = agent.add_link("https://WWW.facebook.com/groups/miel/?fbclid=abc#top")
    assert res2["ok"] is True
    assert res2["created"] is False
    assert len(store.links()) == 1


def test_add_link_adds_https_and_normalizes():
    res = agent.add_link("www.facebook.com/groups/123/")
    assert res["ok"] is True, res.get("message")
    assert res["link"]["url"] == "https://www.facebook.com/groups/123"


def test_add_link_rejects_non_facebook():
    res = agent.add_link("https://example.com/page")
    assert res["ok"] is False
    assert "pas un lien Facebook" in res["message"]
    assert store.links() == []


def test_add_link_rejects_empty():
    assert agent.add_link("   ")["ok"] is False
    assert agent.add_link("")["ok"] is False
    assert store.links() == []


def test_remove_link_x():
    item, _ = store.add_link("https://www.facebook.com/page-a")
    assert store.remove_link(item["id"]) is True
    assert store.remove_link(item["id"]) is False    # déjà retiré
    assert store.links() == []


def test_selection_of_targets():
    a, _ = store.add_link("https://www.facebook.com/a")
    b, _ = store.add_link("https://www.facebook.com/b")
    assert agent.selected_link_urls() == []          # rien de coché au départ

    store.set_link_selection([a["id"], b["id"]])
    assert agent.selected_link_urls() == ["https://www.facebook.com/a",
                                          "https://www.facebook.com/b"]

    store.set_link_selection([b["id"]])              # décoche a
    assert agent.selected_link_urls() == ["https://www.facebook.com/b"]
    assert store.links()[0]["selected"] is False


def test_summary_counts_checked_links():
    item, _ = store.add_link("https://www.facebook.com/groups/x")
    store.set_link_selection([item["id"]])
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur Facebook",
        {"content": "Bonjour", "target": "links"})
    assert res["ok"] is True, res.get("message")
    assert "1 lien(s) coché(s)" in res["task"]["summary"]
    store.remove_task(res["task"]["id"])


def test_task_target_prefers_checked_links():
    """Liens cochés → la tâche vise ces liens (pas de champ Destination)."""
    item, _ = store.add_link("https://www.facebook.com/groups/x")
    store.set_link_selection([item["id"]])
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur mon compte Facebook",
        {"content": "salut"})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["target"] == "links"
    assert "1 lien(s) coché(s)" in res["task"]["summary"]
    store.remove_task(res["task"]["id"])


def test_task_target_groups_text_uses_checked_links():
    item, _ = store.add_link("https://www.facebook.com/groups/y")
    store.set_link_selection([item["id"]])
    res = agent.create_task_from_command(
        "partage dans mes groupes facebook toutes les 2 heures",
        {"content": "salut"})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["target"] == "links"
    store.remove_task(res["task"]["id"])


def test_task_target_falls_back_to_profile():
    """Aucun lien coché → la tâche publie sur le profil (comme avant)."""
    store.save_links([])
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur mon compte Facebook",
        {"content": "salut"})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["target"] == "profile"
    store.remove_task(res["task"]["id"])


def test_task_target_groups_without_any_link_falls_back_to_profile():
    """Le champ « URL d'un groupe » n'existe plus : pas de lien → profil."""
    store.save_links([])
    res = agent.create_task_from_command(
        "partage dans mes groupes facebook toutes les 2 heures",
        {"content": "salut"})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["target"] == "profile"
    store.remove_task(res["task"]["id"])


def test_run_task_links_without_checked_target():
    store.upsert_account("facebook", "https://www.facebook.com/Mhirsimiel/",
                         status="connected")
    store.save_links([])
    res = agent.run_task({"platform": "facebook", "target": "links",
                          "content": "test"})
    assert res["ok"] is False
    assert "cible cochée" in res["message"]
    store.remove_account("facebook")


def test_targets_resolution():
    acc = {"profile_url": "https://www.facebook.com/moi"}
    # liens cochés → autant d'URLs
    urls = fb._targets({"target": "links",
                        "link_urls": ["https://www.facebook.com/a",
                                      "https://www.facebook.com/b"]}, acc)
    assert urls == ["https://www.facebook.com/a", "https://www.facebook.com/b"]
    # aucun lien → message d'aide (str)
    msg = fb._targets({"target": "links"}, acc)
    assert isinstance(msg, str) and "cible cochée" in msg
    # profil / groupe unique : inchangé
    assert fb._targets({"target": "profile"}, acc) == ["https://www.facebook.com/moi"]
    assert fb._targets({"target": "groups",
                        "group_url": "https://www.facebook.com/groups/x"},
                       acc) == ["https://www.facebook.com/groups/x"]
    assert isinstance(fb._targets({"target": "groups"}, acc), str)


def test_aggregate_single_target_unchanged():
    res = {"ok": True, "message": "Publication envoyée sur Facebook"}
    assert fb._aggregate([("https://www.facebook.com/a", res)], 1) is res


def test_aggregate_all_targets_ok():
    out = fb._aggregate([("https://www.facebook.com/a", {"ok": True}),
                         ("https://www.facebook.com/b", {"ok": True})], 2)
    assert out["ok"] is True
    assert "2 liens" in out["message"]


def test_aggregate_partial_failure():
    out = fb._aggregate([("https://www.facebook.com/a", {"ok": True}),
                         ("https://www.facebook.com/b",
                          {"ok": False, "message": "popup"})], 2)
    assert out["ok"] is False
    assert "1/2" in out["message"]
    assert "popup" in out["message"]


# ── Boucle de publication (page factice : AUCUN clic Facebook) ────────────
class _FakePage:
    def __init__(self):
        self.urls: list[str] = []

    def goto(self, url, wait_until=None):
        self.urls.append(url)


def _stub_browser(monkeypatch, page, logged_out=False, flow=None):
    """Remplace le navigateur par une page factice + flux simulé."""
    monkeypatch.setattr(fb.browser, "with_page",
                        lambda plat, fn, visible=False, timeout=90.0: fn(page))
    monkeypatch.setattr(fb.browser, "screenshot", lambda *a, **k: None)
    monkeypatch.setattr(fb.base, "wait_stable", lambda *a, **k: None)
    monkeypatch.setattr(fb.base, "looks_logged_out", lambda p: logged_out)
    monkeypatch.setattr(fb, "_publish_flow",
                        flow or (lambda page, content, media:
                                 {"ok": True, "message": "Publication envoyée"}))


def test_publish_visits_every_checked_link(monkeypatch):
    page = _FakePage()
    _stub_browser(monkeypatch, page)
    out = fb.publish({"target": "links",
                      "link_urls": ["https://www.facebook.com/a",
                                    "https://www.facebook.com/b"],
                      "content": "bonjour"})
    assert page.urls == ["https://www.facebook.com/a",
                         "https://www.facebook.com/b"]
    assert out["ok"] is True
    assert "2 liens" in out["message"]


def test_publish_single_checked_link_keeps_old_message(monkeypatch):
    page = _FakePage()
    _stub_browser(monkeypatch, page)
    out = fb.publish({"target": "links",
                      "link_urls": ["https://www.facebook.com/a"],
                      "content": "bonjour"})
    assert page.urls == ["https://www.facebook.com/a"]
    assert out == {"ok": True, "message": "Publication envoyée"}


def test_publish_stops_when_logged_out(monkeypatch):
    page = _FakePage()
    _stub_browser(monkeypatch, page, logged_out=True)
    out = fb.publish({"target": "links",
                      "link_urls": ["https://www.facebook.com/a",
                                    "https://www.facebook.com/b"],
                      "content": "bonjour"})
    assert page.urls == ["https://www.facebook.com/a"]   # 2e cible non tentée
    assert out["ok"] is False
    assert "non connecté" in out["message"]


def test_publish_continues_after_one_target_fails(monkeypatch):
    page = _FakePage()

    def flow(page, content, media):
        if page.urls[-1].endswith("/b"):
            return {"ok": False, "message": "popup"}
        return {"ok": True, "message": "Publication envoyée"}

    _stub_browser(monkeypatch, page, flow=flow)
    out = fb.publish({"target": "links",
                      "link_urls": ["https://www.facebook.com/a",
                                    "https://www.facebook.com/b",
                                    "https://www.facebook.com/c"],
                      "content": "bonjour"})
    assert page.urls == ["https://www.facebook.com/a",
                         "https://www.facebook.com/b",
                         "https://www.facebook.com/c"]    # on ne s'arrête pas
    assert out["ok"] is False
    assert "2/3" in out["message"]


def test_publish_without_any_checked_link():
    out = fb.publish({"target": "links", "content": "bonjour"})
    assert out["ok"] is False
    assert "cible cochée" in out["message"]              # aucun navigateur lancé
