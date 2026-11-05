"""Tests de l'import d'un fichier Excel choisi par l'utilisateur (bouton +).

Vérifie : extraction SANS limite de nombre, lecture seule du classeur,
dédoublonnage contre la liste existante, persistance définitive.
"""
from __future__ import annotations

import io

from postpilot import agent, config, store, xlsx


def setup_function():
    config.ensure_dirs()
    store.save_links([])


def teardown_function():
    store.save_links([])


def _book_bytes(links: list[str], title: str = "Liens") -> bytes:
    """Classeur en mémoire : liens dans plusieurs feuilles / colonnes."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(["#", "Nom", "Lien"])
    for i, url in enumerate(links, start=1):
        ws.append([i, f"Groupe {i}", url])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── xlsx.extract_links_from_bytes ─────────────────────────────────────────
def test_extract_reads_everything_no_limit():
    """Aucun plafond : 500 liens dans le fichier → 500 liens extraits."""
    urls = [f"https://www.facebook.com/groups/g{i}/" for i in range(500)]
    out = xlsx.extract_links_from_bytes(_book_bytes(urls), "liens.xlsx")
    assert len(out) == 500
    assert out[0] == "https://www.facebook.com/groups/g0/"
    assert out[-1] == "https://www.facebook.com/groups/g499/"


def test_extract_reads_all_sheets_and_text_cells():
    from openpyxl import Workbook
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "A"
    ws1.append(["https://www.facebook.com/page-a"])
    ws2 = wb.create_sheet("B")
    ws2.append([None, "voir https://www.facebook.com/groups/zzz/ ici"])
    buf = io.BytesIO()
    wb.save(buf)
    out = xlsx.extract_links_from_bytes(buf.getvalue(), "mix.xlsx")
    assert "https://www.facebook.com/page-a" in out
    assert "https://www.facebook.com/groups/zzz/" in out


def test_extract_reads_hyperlink_targets():
    """Cellule dont l'affichage n'est pas l'URL : l'hyperlien est lu."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    c = ws.cell(row=1, column=1, value="Cliquez ici")
    c.hyperlink = "https://www.facebook.com/groups/cachet/"
    buf = io.BytesIO()
    wb.save(buf)
    out = xlsx.extract_links_from_bytes(buf.getvalue(), "h.xlsx")
    assert out == ["https://www.facebook.com/groups/cachet/"]


def test_extract_does_not_modify_file():
    """Lecture seule : le classeur envoyé reste identique octet par octet."""
    data = _book_bytes(["https://www.facebook.com/groups/a/"])
    xlsx.extract_links_from_bytes(data, "refs.xlsx")
    # le binaire d'entrée n'a pas été altéré (immuté en mémoire)
    assert xlsx.extract_links_from_bytes(data, "refs.xlsx") == \
        ["https://www.facebook.com/groups/a/"]


def test_extract_rejects_empty_and_bad_format():
    try:
        xlsx.extract_links_from_bytes(b"", "x.xlsx")
        assert False, "doit lever ValueError"
    except ValueError as e:
        assert "vide" in str(e)
    try:
        xlsx.extract_links_from_bytes(b"PK...", "ancien.xls")
        assert False, "doit lever ValueError"
    except ValueError as e:
        assert ".xls" in str(e)
    try:
        xlsx.extract_links_from_bytes(b"zzz", "doc.pdf")
        assert False, "doit lever ValueError"
    except ValueError as e:
        assert ".pdf" in str(e)


# ── store.add_links_bulk ──────────────────────────────────────────────────
def test_add_links_bulk_unlimited_and_dedupes():
    urls = [f"https://www.facebook.com/bulk{i}/" for i in range(300)]
    added, dupes = store.add_links_bulk(urls)
    assert len(added) == 300 and dupes == 0
    assert len(store.links()) == 300

    # re-import du même fichier → tout est doublon, rien n'est écrit deux fois
    added2, dupes2 = store.add_links_bulk(urls)
    assert added2 == [] and dupes2 == 300
    assert len(store.links()) == 300


# ── agent.import_links_file ───────────────────────────────────────────────
def test_import_adds_only_missing_links():
    """Dédoublonnage contre la liste : seuls les liens manquants sont copiés."""
    store.add_link("https://www.facebook.com/groups/deja-là/")
    data = _book_bytes([
        "https://www.facebook.com/groups/deja-là/",     # déjà en liste
        "https://m.facebook.com/groups/deja-là/",       # même lien, autre écriture
        "https://www.facebook.com/groups/neuf/",
        "https://facebook.com/PasLaEncore",
    ])
    res = agent.import_links_file("mes liens.xlsx", data)
    assert res["ok"] is True, res.get("message")
    assert res["added"] == 2
    assert res["duplicates"] == 2
    urls = [i["url"] for i in store.links()]
    assert len(urls) == 3
    # _normalize_link retire la barre finale (convention du projet)
    assert "https://www.facebook.com/groups/neuf" in urls
    assert "https://facebook.com/PasLaEncore" in urls


def test_import_is_permanent():
    """La liste est enregistrée sur le disque : relue → identique."""
    data = _book_bytes([f"https://www.facebook.com/groups/p{i}/"
                        for i in range(120)])
    res = agent.import_links_file("p.xlsx", data)
    assert res["ok"] is True and res["added"] == 120
    # relecture depuis le fichier (store.links() lit le disque à chaque fois)
    assert len(store.links()) == 120


def test_import_twice_adds_nothing():
    data = _book_bytes(["https://www.facebook.com/groups/a/",
                        "https://www.facebook.com/groups/b/"])
    first = agent.import_links_file("f.xlsx", data)
    assert first["added"] == 2
    second = agent.import_links_file("f.xlsx", data)
    assert second["ok"] is True
    assert second["added"] == 0
    assert second["duplicates"] == 2
    assert len(store.links()) == 2


def test_import_no_limit_with_many_links():
    """Le nombre de liens est illimité : 1000 liens importés d'un coup."""
    urls = [f"https://www.facebook.com/groupe-{i}/" for i in range(1000)]
    res = agent.import_links_file("gros.xlsx", _book_bytes(urls))
    assert res["ok"] is True
    assert res["added"] == 1000
    assert len(store.links()) == 1000


def test_import_ignores_unknown_hosts():
    data = _book_bytes(["https://example.com/page",
                        "https://www.facebook.com/ok/"])
    res = agent.import_links_file("mix.xlsx", data)
    assert res["ok"] is True
    assert res["added"] == 1
    assert [i["url"] for i in store.links()] == ["https://www.facebook.com/ok"]


def test_import_rejects_unreadable_file():
    res = agent.import_links_file("vide.xlsx", b"")
    assert res["ok"] is False
    assert res["message"]
    assert store.links() == []
