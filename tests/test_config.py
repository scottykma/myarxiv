import json
import os
from unittest.mock import mock_open, patch

import pytest
import yaml

import src.config
from src.config import backup_path, config_path, get, get_env, load_config, reload, replace, save, set, undo


@pytest.mark.unit
class TestConfigLoad:
    def test_load_config_returns_dict(self, temp_config_dir):
        config = load_config()
        assert isinstance(config, dict)
        assert config["user"]["name"] == "Test User"

    def test_load_config_cache(self, temp_config_dir):
        config1 = load_config()
        config2 = load_config()
        assert config1 is config2

    def test_load_config_missing_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(src.config, "_CONFIG_PATH", tmp_path / "nonexistent.yaml")
        monkeypatch.setattr(src.config, "_CONFIG", None)
        with pytest.raises(FileNotFoundError) as excinfo:
            load_config()
        assert "Copy config.example.yaml to config.yaml first" in str(excinfo.value)

    def test_reload_bypass_cache(self, temp_config_dir):
        config1 = reload()
        config2 = reload()
        assert config1 is not config2
        assert config1 == config2


@pytest.mark.unit
class TestConfigGet:
    def test_get_top_level(self, temp_config_dir):
        assert get("user.name") == "Test User"

    def test_get_nested(self, temp_config_dir):
        assert get("daily.max_papers") == 20

    def test_get_list(self, temp_config_dir):
        keywords = get("interests.keywords_include")
        assert isinstance(keywords, list)
        assert "agent" in keywords

    def test_get_default(self, temp_config_dir):
        assert get("nonexistent.key", "default_value") == "default_value"

    def test_get_partial_path_default(self, temp_config_dir):
        src.config._CONFIG = None
        config = load_config()
        assert get("user.name.extra", "fallback") == "fallback"


@pytest.mark.unit
class TestConfigSet:
    def test_set_existing(self, temp_config_dir):
        set("daily.max_papers", 20)
        assert get("daily.max_papers") == 20

    def test_set_new_key(self, temp_config_dir):
        set("daily.new_option", "test_value")
        assert get("daily.new_option") == "test_value"

    def test_set_creates_nested(self, temp_config_dir):
        set("notification.wechat.new_field", 123)
        assert get("notification.wechat.new_field") == 123


@pytest.mark.unit
class TestConfigSave:
    def test_save_persists_changes(self, temp_config_dir):
        set("daily.max_papers", 15)
        save()
        reload()
        assert get("daily.max_papers") == 15

    def test_save_noop_when_no_config(self, monkeypatch):
        monkeypatch.setattr(src.config, "_CONFIG", None)
        save()

    def test_save_creates_previous_version(self, temp_config_dir):
        set("daily.max_papers", 15)
        save()
        assert backup_path().exists()
        previous = yaml.safe_load(backup_path().read_text())
        assert previous["daily"]["max_papers"] == 20

    def test_save_leaves_no_temp_file(self, temp_config_dir):
        set("daily.max_papers", 15)
        save()
        assert not config_path().with_name(config_path().name + ".tmp").exists()

    def test_undo_restores_previous_version(self, temp_config_dir):
        set("daily.max_papers", 15)
        save()
        set("daily.max_papers", 10)
        save()
        assert undo() is True
        assert get("daily.max_papers") == 15
        assert not backup_path().exists()

    def test_undo_without_backup(self, temp_config_dir):
        assert undo() is False

    def test_backup_path(self, temp_config_dir):
        assert backup_path().name == "config.yaml.bak"

    def test_replace(self, temp_config_dir):
        replace({"user": {"name": "New"}})
        assert get("user.name") == "New"
        with pytest.raises(ValueError, match="mapping"):
            replace([])

    def test_save_cleans_temp_when_replace_fails(self, temp_config_dir, monkeypatch):
        set("daily.max_papers", 15)
        def _fail_replace(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(src.config.os, "replace", _fail_replace)
        with pytest.raises(OSError):
            save()
        assert not config_path().with_name(config_path().name + ".tmp").exists()

    def test_undo_invalid_backup(self, temp_config_dir):
        backup_path().write_text("not: [valid")
        assert undo() is False

    def test_undo_non_mapping_backup(self, temp_config_dir):
        backup_path().write_text("- one\n- two\n")
        assert undo() is False

    def test_undo_survives_unlink_error(self, temp_config_dir, monkeypatch):
        set("daily.max_papers", 15)
        save()
        def _fail_unlink(*args, **kwargs):
            raise OSError("locked")

        monkeypatch.setattr(src.config.Path, "unlink", _fail_unlink)
        assert undo() is True


@pytest.mark.unit
class TestConfigLoadErrors:
    def test_empty_config_becomes_mapping(self, temp_config_dir):
        config_path().write_text("")
        src.config._CONFIG = None
        assert load_config() == {}

    def test_non_mapping_config(self, temp_config_dir):
        config_path().write_text("- one\n- two\n")
        src.config._CONFIG = None
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config()


@pytest.mark.unit
class TestGetEnv:
    def test_get_env_existing(self, mock_env, monkeypatch):
        assert get_env("OPENAI_API_KEY") == "sk-test-key"

    def test_get_env_default(self, monkeypatch):
        assert get_env("NONEXISTENT_KEY", "default") == "default"

    def test_get_env_empty_string(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert get_env("OPENAI_API_KEY") == ""

    def test_get_env_base_url_default(self, monkeypatch):
        assert get_env("NONEXISTENT_URL", "https://default.url") == "https://default.url"
