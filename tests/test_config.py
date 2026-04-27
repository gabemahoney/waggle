"""Tests for config module (v2)."""

import json
from pathlib import Path

import pytest

from waggle.config import (
    get_config,
    get_db_path,
    get_http_port,
    get_max_workers,
    get_mcp_worker_port,
    get_queue_path,
    get_repos_path,
)


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Redirect HOME and Path.home() to tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def config_dir(temp_home):
    waggle_dir = temp_home / ".waggle"
    waggle_dir.mkdir(parents=True, exist_ok=True)
    return waggle_dir


@pytest.fixture
def config_file(config_dir):
    return config_dir / "config.json"


class TestAllDefaults:
    def test_all_default_keys_present(self, temp_home):
        config = get_config()
        expected_keys = {
            "database_path", "queue_path", "max_workers", "state_poll_interval_seconds",
            "output_capture_lines", "http_port", "mcp_worker_port", "relay_timeout_seconds",
            "authorized_keys_path", "repos_path", "admin_email", "admin_notify_after_retries",
            "max_retry_hours", "tls_cert_path", "tls_key_path",
        }
        assert set(config.keys()) == expected_keys

    def test_database_path_default(self, temp_home):
        assert get_config()["database_path"] == "~/.waggle/state.db"

    def test_queue_path_default(self, temp_home):
        assert get_config()["queue_path"] == "~/.waggle/queue.db"

    def test_max_workers_default(self, temp_home):
        assert get_config()["max_workers"] == 8

    def test_state_poll_interval_default(self, temp_home):
        assert get_config()["state_poll_interval_seconds"] == 2

    def test_output_capture_lines_default(self, temp_home):
        assert get_config()["output_capture_lines"] == 50

    def test_http_port_default(self, temp_home):
        assert get_config()["http_port"] == 8422

    def test_mcp_worker_port_default(self, temp_home):
        assert get_config()["mcp_worker_port"] == 8423

    def test_relay_timeout_default(self, temp_home):
        assert get_config()["relay_timeout_seconds"] == 3600

    def test_authorized_keys_path_default(self, temp_home):
        assert get_config()["authorized_keys_path"] == "~/.waggle/authorized_keys.json"

    def test_repos_path_default(self, temp_home):
        assert get_config()["repos_path"] == "~/.waggle/repos"

    def test_admin_email_default(self, temp_home):
        assert get_config()["admin_email"] == ""

    def test_admin_notify_after_retries_default(self, temp_home):
        assert get_config()["admin_notify_after_retries"] == 5

    def test_max_retry_hours_default(self, temp_home):
        assert get_config()["max_retry_hours"] == 72

    def test_tls_cert_path_default(self, temp_home):
        assert get_config()["tls_cert_path"] == ""

    def test_tls_key_path_default(self, temp_home):
        assert get_config()["tls_key_path"] == ""


class TestFileOverrides:
    def test_file_overrides_database_path(self, config_file):
        config_file.write_text(json.dumps({"database_path": "/custom/db.sqlite"}))
        assert get_config()["database_path"] == "/custom/db.sqlite"

    def test_file_overrides_http_port(self, config_file):
        config_file.write_text(json.dumps({"http_port": 9000}))
        assert get_config()["http_port"] == 9000

    def test_file_overrides_max_workers(self, config_file):
        config_file.write_text(json.dumps({"max_workers": 16}))
        assert get_config()["max_workers"] == 16

    def test_non_overridden_keys_keep_defaults(self, config_file):
        config_file.write_text(json.dumps({"http_port": 9000}))
        config = get_config()
        assert config["max_workers"] == 8
        assert config["database_path"] == "~/.waggle/state.db"

    def test_multiple_overrides(self, config_file):
        overrides = {"http_port": 9001, "max_workers": 4, "admin_email": "ops@example.com"}
        config_file.write_text(json.dumps(overrides))
        config = get_config()
        assert config["http_port"] == 9001
        assert config["max_workers"] == 4
        assert config["admin_email"] == "ops@example.com"


class TestUnknownKeysIgnored:
    def test_unknown_key_not_in_result(self, config_file):
        config_file.write_text(json.dumps({"unknown_key": "value", "http_port": 9001}))
        config = get_config()
        assert "unknown_key" not in config
        assert config["http_port"] == 9001

    def test_all_unknown_keys_ignored(self, config_file):
        config_file.write_text(json.dumps({"foo": 1, "bar": 2, "baz": 3}))
        config = get_config()
        assert "foo" not in config
        assert "bar" not in config
        assert "baz" not in config
        # All defaults still present
        assert config["http_port"] == 8422


class TestTildeExpansion:
    def test_get_db_path_expands_tilde(self, temp_home):
        result = get_db_path()
        assert "~" not in result
        assert str(temp_home) in result

    def test_get_queue_path_expands_tilde(self, temp_home):
        result = get_queue_path()
        assert "~" not in result
        assert str(temp_home) in result

    def test_get_repos_path_expands_tilde(self, temp_home):
        result = get_repos_path()
        assert "~" not in result
        assert str(temp_home) in result

    def test_custom_tilde_path_in_database_path(self, config_file, temp_home):
        config_file.write_text(json.dumps({"database_path": "~/.waggle/custom.db"}))
        result = get_db_path()
        assert "~" not in result
        assert str(temp_home / ".waggle" / "custom.db") == result

    def test_authorized_keys_path_tilde_expansion(self, config_file, temp_home):
        config_file.write_text(
            json.dumps({"authorized_keys_path": "~/.waggle/custom_keys.json"})
        )
        raw = get_config()["authorized_keys_path"]
        expanded = str(Path(raw).expanduser())
        assert "~" not in expanded
        assert str(temp_home) in expanded


class TestMalformedJSON:
    def test_malformed_json_returns_defaults(self, config_file):
        config_file.write_text("{this is not valid json")
        config = get_config()
        assert config["database_path"] == "~/.waggle/state.db"
        assert config["http_port"] == 8422

    def test_malformed_json_has_all_keys(self, config_file):
        config_file.write_text("{not json at all!")
        config = get_config()
        expected_keys = {
            "database_path", "queue_path", "max_workers", "state_poll_interval_seconds",
            "output_capture_lines", "http_port", "mcp_worker_port", "relay_timeout_seconds",
            "authorized_keys_path", "repos_path", "admin_email", "admin_notify_after_retries",
            "max_retry_hours", "tls_cert_path", "tls_key_path",
        }
        assert set(config.keys()) == expected_keys


class TestNonDictJSON:
    def test_array_json_returns_defaults(self, config_file):
        config_file.write_text(json.dumps(["not", "a", "dict"]))
        config = get_config()
        assert config["http_port"] == 8422
        assert config["database_path"] == "~/.waggle/state.db"

    def test_string_json_returns_defaults(self, config_file):
        config_file.write_text(json.dumps("just a string"))
        config = get_config()
        assert config["database_path"] == "~/.waggle/state.db"

    def test_null_json_returns_defaults(self, config_file):
        config_file.write_text("null")
        config = get_config()
        assert config["max_workers"] == 8


class TestPathAccessors:
    def test_get_db_path_returns_absolute(self, temp_home):
        assert Path(get_db_path()).is_absolute()

    def test_get_queue_path_returns_absolute(self, temp_home):
        assert Path(get_queue_path()).is_absolute()

    def test_get_repos_path_returns_absolute(self, temp_home):
        assert Path(get_repos_path()).is_absolute()

    def test_get_db_path_default_is_state_db(self, temp_home):
        result = get_db_path()
        expected = str(temp_home / ".waggle" / "state.db")
        assert result == expected


class TestPortAndIntAccessors:
    def test_get_http_port_returns_int(self, temp_home):
        result = get_http_port()
        assert isinstance(result, int)
        assert result == 8422

    def test_get_mcp_worker_port_returns_int(self, temp_home):
        result = get_mcp_worker_port()
        assert isinstance(result, int)
        assert result == 8423

    def test_get_max_workers_returns_int(self, temp_home):
        result = get_max_workers()
        assert isinstance(result, int)
        assert result == 8

    def test_get_http_port_with_string_config_value(self, config_file, temp_home):
        config_file.write_text(json.dumps({"http_port": "9000"}))
        result = get_http_port()
        assert isinstance(result, int)
        assert result == 9000
