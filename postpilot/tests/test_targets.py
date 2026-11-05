"""Tests de l'extraction des cibles Facebook (groupes & pages)."""
from __future__ import annotations

from postpilot.targets import extract_fb_targets


def test_groups_normalized_and_deduped():
    hrefs = [
        "https://www.facebook.com/groups/123456789/",
        "https://www.facebook.com/groups/123456789/?ref=share",   # doublon
        "https://m.facebook.com/groups/mon-groupe/",
        "https://www.facebook.com/groups/x/posts/99/",            # → le groupe
    ]
    out = extract_fb_targets(hrefs, kind="groups")
    assert out == [
        "https://www.facebook.com/groups/123456789/",
        "https://www.facebook.com/groups/mon-groupe/",
        "https://www.facebook.com/groups/x/",
    ]


def test_groups_system_links_rejected():
    hrefs = [
        "https://www.facebook.com/groups/discover",
        "https://www.facebook.com/groups/",
        "https://www.facebook.com/groups/your_posts",
        "https://example.com/groups/y",
        "www.facebook.com/groups/ok",
    ]
    out = extract_fb_targets(hrefs, kind="groups")
    assert out == ["https://www.facebook.com/groups/ok/"]


def test_pages_from_category_and_bare_slug():
    hrefs = [
        "https://www.facebook.com/pages/Commerce/MielDeSfax",
        "https://www.facebook.com/MonPage/",
        "https://www.facebook.com/MonPage/photos",   # sous-page → ignorée
        "https://www.facebook.com/watch",
        "https://www.facebook.com/settings",
        "https://www.facebook.com/profile.php?id=123",
        "https://www.instagram.com/autre",
    ]
    out = extract_fb_targets(hrefs, kind="pages")
    assert out == [
        "https://www.facebook.com/pages/Commerce/MielDeSfax/",
        "https://www.facebook.com/MonPage/",
    ]


def test_kind_filter_separates_groups_and_pages():
    hrefs = [
        "https://www.facebook.com/groups/a/",
        "https://www.facebook.com/MaPage/",
    ]
    assert extract_fb_targets(hrefs, kind="groups") == [
        "https://www.facebook.com/groups/a/"]
    assert extract_fb_targets(hrefs, kind="pages") == [
        "https://www.facebook.com/MaPage/"]


def test_all_is_union_in_order():
    hrefs = [
        "https://www.facebook.com/groups/a/",
        "https://www.facebook.com/MaPage/",
        "https://www.facebook.com/groups/b/",
    ]
    assert extract_fb_targets(hrefs) == [
        "https://www.facebook.com/groups/a/",
        "https://www.facebook.com/MaPage/",
        "https://www.facebook.com/groups/b/",
    ]


def test_empty_and_junk_input():
    assert extract_fb_targets([]) == []
    assert extract_fb_targets(None) == []
    assert extract_fb_targets(["", "  ", "javascript:void(0)", None]) == []
