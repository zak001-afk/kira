"""Tests du parseur de commandes françaises."""
from postpilot import commands as c


def test_platform_detection():
    assert c.detect_platform("Publie sur Facebook") == "facebook"
    assert c.detect_platform("mets ça sur insta") == "instagram"
    assert c.detect_platform("video tiktok") == "tiktok"
    assert c.detect_platform("salut") is None


def test_interval_every_hour():
    assert c.detect_interval("Publie ce post toutes les 1 heure") == 3600
    assert c.detect_interval("chaque 2h") == 7200
    assert c.detect_interval("toutes les 30 minutes") == 1800
    assert c.detect_interval("toutes les heures") == 3600
    assert c.detect_interval("1 post chaque jour") == 86400


def test_interval_none():
    assert c.detect_interval("publie vite") is None


def test_kind():
    assert c.detect_kind("publie une story") == "story"
    assert c.detect_kind("publie cette vidéo") == "video"
    assert c.detect_kind("publie ce post") == "post"


def test_target():
    assert c.detect_target("dans mes groupes facebook") == "groups"
    assert c.detect_target("sur mon compte facebook") == "profile"
    assert c.detect_target("") == "profile"


def test_parse_command_full():
    p = c.parse_command(
        "Publie ce post toutes les 1 heure sur mon compte Facebook")
    assert p["platform"] == "facebook"
    assert p["interval_seconds"] == 3600
    assert p["target"] == "profile"
    assert p["valid"] is True


def test_parse_command_missing_platform():
    p = c.parse_command("publie toutes les 1 heure")
    assert p["platform"] is None
    assert p["valid"] is False


def test_quoted_content():
    p = c.parse_command('publie "bonjour à tous" toutes les 2h sur insta')
    assert p["content"] == "bonjour à tous"
    assert p["platform"] == "instagram"
    assert p["interval_seconds"] == 7200


def test_human_interval():
    assert c.human_interval(3600) == "toutes les 1 heure"
    assert c.human_interval(1800) == "toutes les 30 minutes"
    assert c.human_interval(10800) == "toutes les 3 heures"
    assert c.human_interval(43200) == "toutes les 12 heures"
    # 24 h se dit « 24 heures » (et non « 1 jour »)
    assert c.human_interval(86400) == "toutes les 24 heures"
    assert c.human_interval(172800) == "toutes les 2 jours"


def test_media_absolute_path():
    assert c.detect_media(
        "publie E:\\photos\\miel.jpg toutes les 1 heure sur facebook"
    ) == "E:\\photos\\miel.jpg"
    assert c.detect_media("publie C:/media/clip.mp4 chaque 2h sur insta") == \
        "C:/media/clip.mp4"


def test_media_relative_path():
    assert c.detect_media("publie ce post avec photo.png toutes les 1h") == "photo.png"
    assert c.detect_media("poste img.jpg dans mes groupes facebook toutes les 2h") == \
        "img.jpg"


def test_media_none():
    assert c.detect_media("publie ce post toutes les 1 heure sur facebook") == ""
    assert c.detect_media("") == ""


def test_parse_command_keeps_media():
    p = c.parse_command(
        "publie E:\\photos\\miel.jpg toutes les 1 heure sur mon compte Facebook")
    assert p["media"] == "E:\\photos\\miel.jpg"
    assert p["platform"] == "facebook"
    assert p["interval_seconds"] == 3600
