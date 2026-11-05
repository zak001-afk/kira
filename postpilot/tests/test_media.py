"""Médias insérés depuis l'interface (bouton +) : écriture et sécurité."""
from __future__ import annotations

from postpilot import config, store


def setup_function():
    config.ensure_dirs()
    for p in config.MEDIA.glob("*"):
        if p.is_file():
            p.unlink()


def test_save_media_ok():
    name, err = store.save_media("photo de test.jpg", b"\xff\xd8fake")
    assert err is None, err
    assert name == "photo de test.jpg"
    assert (config.MEDIA / "photo de test.jpg").read_bytes() == b"\xff\xd8fake"
    assert any(m["name"] == "photo de test.jpg" for m in store.list_media())


def test_save_media_keeps_only_the_file_name():
    name, err = store.save_media(r"C:\Users\moi\Videos\clip.mp4", b"1234")
    assert err is None, err
    assert name == "clip.mp4"
    assert not (config.MEDIA / "Users").exists()      # aucun sous-dossier


def test_save_media_cannot_escape_the_media_folder():
    name, err = store.save_media("../../evil.jpg", b"1234")
    assert err is None, err
    assert name == "evil.jpg"                          # chemin neutralisé
    assert not (config.DATA.parent / "evil.jpg").exists()
    assert (config.MEDIA / "evil.jpg").exists()         # écrit uniquement ici


def test_save_media_rejects_bad_extension():
    name, err = store.save_media("programme.exe", b"1234")
    assert name is None
    assert err and "Format non pris en charge" in err
    assert not (config.MEDIA / "programme.exe").exists()


def test_save_media_rejects_empty_file_or_name():
    assert store.save_media("", b"1234")[0] is None
    assert store.save_media("   ", b"1234")[0] is None
    name, err = store.save_media("photo.jpg", b"")
    assert name is None
    assert err == "Fichier vide"


def test_list_media_ignores_unknown_files():
    (config.MEDIA / "notes.txt").write_text("x", encoding="utf-8")
    store.save_media("clip.mp4", b"vid")
    names = [m["name"] for m in store.list_media()]
    assert "clip.mp4" in names
    assert "notes.txt" not in names
