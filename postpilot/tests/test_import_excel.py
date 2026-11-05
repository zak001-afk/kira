"""Tests du filtre sans doublon et du fichier Excel de référence (lecture seule)."""
from __future__ import annotations

from pathlib import Path

from postpilot import targets, xlsx


# ── normalize_url / filter_new_links ──────────────────────────────────────
def test_normalize_url_variants():
    a = targets.normalize_url("https://www.facebook.com/groups/x/")
    b = targets.normalize_url("http://m.facebook.com/groups/x")
    c = targets.normalize_url("https://facebook.com/groups/x?fbclid=1")
    assert a == b == c == "https://facebook.com/groups/x"
    assert targets.normalize_url("") == ""
    assert targets.normalize_url("  ") == ""


def test_filter_new_links_skips_existing():
    existing = ["https://www.facebook.com/groups/a/",
                "https://facebook.com/Page1"]
    found = [
        "https://www.facebook.com/groups/a/",       # déjà présent
        "https://m.facebook.com/groups/a",          # même lien, autre écriture
        "https://www.facebook.com/groups/b/",       # nouveau
        "https://www.facebook.com/Page1/",          # déjà présent
        "https://www.facebook.com/groups/b/",       # doublon dans found
    ]
    out = targets.filter_new_links(found, existing)
    assert out == ["https://www.facebook.com/groups/b/"]


def test_filter_new_links_first_import():
    """Référence vide → tout est nouveau, sans doublon interne."""
    found = ["https://www.facebook.com/groups/1/",
             "https://www.facebook.com/groups/1/",
             "https://www.facebook.com/MaPage/"]
    assert targets.filter_new_links(found, []) == [
        "https://www.facebook.com/groups/1/",
        "https://www.facebook.com/MaPage/",
    ]


def test_filter_new_links_empty_input():
    assert targets.filter_new_links([], ["https://x"]) == []
    assert targets.filter_new_links(None, None) == []


def test_pages_system_links_never_brought_back():
    """Vus sur la liste « vos pages » : photo/, video/, stories/… ne sont
    JAMAIS des cibles de publication — même absents du fichier, on les jette."""
    hrefs = [
        "https://www.facebook.com/photo/",
        "https://www.facebook.com/photos/",
        "https://www.facebook.com/video/",
        "https://www.facebook.com/stories/",
        "https://www.facebook.com/people/",
        "https://www.facebook.com/pg/Something",
        "https://www.facebook.com/hashtag/tunisie",
        "https://www.facebook.com/MaBellePage/",     # vraie page → conservée
    ]
    assert targets.extract_fb_targets(hrefs, kind="pages") == [
        "https://www.facebook.com/MaBellePage/"]


# ── Excel : lecture seule ─────────────────────────────────────────────────
def _make_book(path: Path, links: list[str]) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Groupes de VENTE"
    ws.append(["#", "Nom", "Lien", "Zone", "Catégorie", "Visibilité",
               "Obstacle", "Remarque"])
    for i, url in enumerate(links, start=1):
        ws.append([i, f"Groupe {i}", url, "", "", "", "", ""])
    wb.save(path)


def test_read_links_from_book(tmp_path):
    p = tmp_path / "refs.xlsx"
    _make_book(p, ["https://www.facebook.com/groups/a/",
                   "https://www.facebook.com/groups/b/"])
    assert xlsx.read_links(p) == [
        "https://www.facebook.com/groups/a/",
        "https://www.facebook.com/groups/b/",
    ]


def test_read_links_missing_file(tmp_path):
    assert xlsx.read_links(tmp_path / "absent.xlsx") == []


def test_read_links_ignores_header_and_junk(tmp_path):
    p = tmp_path / "refs.xlsx"
    _make_book(p, ["https://www.facebook.com/groups/a/"])
    from openpyxl import load_workbook
    wb = load_workbook(p)
    wb.active.append([99, "vide", None, "", "", "", "", ""])   # ligne sans lien
    wb.save(p)
    assert xlsx.read_links(p) == ["https://www.facebook.com/groups/a/"]


def test_file_never_modified_by_import(tmp_path):
    """L'import est en LECTURE SEULE : le classeur reste identique octet par
    octet après une lecture (pas d'export)."""
    p = tmp_path / "refs.xlsx"
    _make_book(p, ["https://www.facebook.com/groups/a/",
                   "https://www.facebook.com/groups/b/"])
    before = p.read_bytes()
    xlsx.read_links(p)
    assert p.read_bytes() == before


def test_full_cycle_no_duplicates_against_reference():
    """Scénario complet sans écriture : 1er import ajoute les manquants à la
    liste, 2e clic → 0 nouveau (la référence est relue à chaque fois)."""
    reference = ["https://www.facebook.com/groups/a/"]
    interface: list[str] = []
    found = ["https://www.facebook.com/groups/a/",
             "https://www.facebook.com/groups/c/"]

    new = targets.filter_new_links(found, reference + interface)
    assert new == ["https://www.facebook.com/groups/c/"]
    interface += new

    # second clic : rien de nouveau, la référence n'a même pas bougé
    again = targets.filter_new_links(found, reference + interface)
    assert again == []
    assert reference == ["https://www.facebook.com/groups/a/"]
