"""Tests for the pure helpers in scripts/setup_models.py."""

import importlib.util
import json
from pathlib import Path

import pytest

_SETUP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "setup_models.py"
_spec = importlib.util.spec_from_file_location("setup_models", _SETUP_PATH)
setup_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup_models)


class TestReadConfigModels:
    def test_reads_models_from_config(self, tmp_path):
        cfg = tmp_path / "kira_config.json"
        cfg.write_text(json.dumps({"model": "a:1b", "vision_model": "b:2b"}))
        assert setup_models.read_config_models(cfg) == ("a:1b", "b:2b")

    def test_missing_file_uses_defaults(self, tmp_path):
        chat, vision = setup_models.read_config_models(tmp_path / "nope.json")
        assert chat == setup_models.DEFAULT_CHAT_MODEL
        assert vision == setup_models.DEFAULT_VISION_MODEL

    def test_corrupt_file_uses_defaults(self, tmp_path):
        cfg = tmp_path / "kira_config.json"
        cfg.write_text("{broken")
        assert setup_models.read_config_models(cfg) == (
            setup_models.DEFAULT_CHAT_MODEL,
            setup_models.DEFAULT_VISION_MODEL,
        )


class TestUpdateConfigOfflinePath:
    def test_adds_offline_path_and_preserves_keys(self, tmp_path):
        cfg = tmp_path / "kira_config.json"
        cfg.write_text(json.dumps({"model": "a:1b", "custom": 42}))
        model_dir = tmp_path / "models" / "vosk-model-small-en-us-0.15"

        data = setup_models.update_config_offline_path(cfg, model_dir)

        assert data["offline_model_path"] == str(model_dir)
        assert data["model"] == "a:1b"
        assert data["custom"] == 42
        assert json.loads(cfg.read_text())["offline_model_path"] == str(model_dir)

    def test_creates_config_when_missing(self, tmp_path):
        cfg = tmp_path / "kira_config.json"
        data = setup_models.update_config_offline_path(cfg, tmp_path / "m")
        assert "offline_model_path" in data
        assert cfg.is_file()


class TestVoskCatalog:
    @pytest.mark.parametrize("lang", ["en", "fr"])
    def test_catalog_entries_are_consistent(self, lang):
        assert lang in setup_models.VOSK_MODELS
        assert lang in setup_models.VOSK_DIR_NAMES
        assert setup_models.VOSK_MODELS[lang].endswith(
            setup_models.VOSK_DIR_NAMES[lang] + ".zip"
        )
