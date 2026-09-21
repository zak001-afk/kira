"""Tests for config loading: file missing, corrupt, wrong type, partial."""


class TestLoadConfig:
    def _load(self, backend, tmp_path, monkeypatch, content=None, name="cfg.json"):
        path = tmp_path / name
        if content is not None:
            path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(backend, "CONFIG_PATH", str(path))
        return backend.load_config()

    def test_missing_file_gives_defaults(self, backend, tmp_path, monkeypatch):
        config = self._load(backend, tmp_path, monkeypatch)
        assert config == backend.DEFAULT_CONFIG

    def test_corrupt_json_gives_defaults(self, backend, tmp_path, monkeypatch):
        config = self._load(backend, tmp_path, monkeypatch, "{not json")
        assert config == backend.DEFAULT_CONFIG

    def test_non_dict_json_gives_defaults(self, backend, tmp_path, monkeypatch):
        config = self._load(backend, tmp_path, monkeypatch, '["a", "b"]')
        assert config == backend.DEFAULT_CONFIG

    def test_partial_config_merges_over_defaults(self, backend, tmp_path, monkeypatch):
        config = self._load(
            backend,
            tmp_path,
            monkeypatch,
            '{"model": "llama3.2:1b", "chat_history_limit": 5}',
        )
        assert config["model"] == "llama3.2:1b"
        assert config["chat_history_limit"] == 5
        # keys not present in the file keep their defaults
        assert config["require_wake_word"] is False
        assert "shortcuts" in config

    def test_repo_config_is_valid(self, backend):
        # The shipped kira_config.json must always load cleanly.
        config = backend.load_config()
        assert isinstance(config["shortcuts"], dict)
        assert config["model"]
