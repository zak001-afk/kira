"""Aperçu en direct des fenêtres (images servies dans l'interface)."""
from __future__ import annotations

from postpilot import browser


class _FakePage:
    def __init__(self, data=b"\xff\xd8jpeg", url="https://www.facebook.com/groups/x",
                 fail=False):
        self._data = data
        self.url = url
        self._fail = fail

    def screenshot(self, **kwargs):
        if self._fail:
            raise RuntimeError("page en navigation")
        assert kwargs.get("type") == "jpeg"
        return self._data


def test_store_frame_then_read():
    browser.forget_frame("facebook")
    assert browser.frame("facebook") is None
    assert browser.store_frame("facebook", _FakePage()) is True
    fr = browser.frame("facebook")
    assert fr["img"] == b"\xff\xd8jpeg"
    assert fr["url"] == "https://www.facebook.com/groups/x"
    assert fr["ts"] > 0
    browser.forget_frame("facebook")
    assert browser.frame("facebook") is None


def test_capture_failure_never_breaks_anything():
    # page en navigation : la capture échoue → on renvoie False, sans effet
    assert browser.store_frame("facebook", _FakePage(fail=True)) is False
    assert browser.frame("facebook") is None

    class _BrokenUrl:
        def screenshot(self, **kwargs):
            return b"abc"

        @property
        def url(self):
            raise RuntimeError("navigation en cours")

    # URL illisible : on garde quand même l'image
    assert browser.store_frame("facebook", _BrokenUrl()) is True
    assert browser.frame("facebook")["img"] == b"abc"
    assert browser.frame("facebook")["url"] == ""
    browser.forget_frame("facebook")


def test_request_capture_without_window_is_a_noop():
    browser.forget_frame("tiktok")
    browser.request_capture("tiktok")           # aucune fenêtre ouverte
    assert browser.frame("tiktok") is None


def test_frame_is_copied_so_caller_cannot_mutate_cache():
    browser.store_frame("instagram", _FakePage(url="https://www.instagram.com/"))
    fr = browser.frame("instagram")
    fr["img"] = "modifié"
    assert browser.frame("instagram")["img"] == b"\xff\xd8jpeg"
    browser.forget_frame("instagram")
