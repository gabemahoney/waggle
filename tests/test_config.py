"""Tests for config module."""

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from waggle.config import get_config, get_db_path


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Create a temporary home directory for testing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Update Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def config_dir(temp_home):
    """Create ~/.waggle directory."""
    waggle_dir = temp_home / ".waggle"
    waggle_dir.mkdir(parents=True, exist_ok=True)
    return waggle_dir


@pytest.fixture
def config_file(config_dir):
    """Path to config file."""
    return config_dir / "config.json"


class TestGetConfig:
    """Tests for get_config() function."""
    
    def test_missing_config_file_returns_empty_dict(self, temp_home):
        """When config file doesn't exist, returns empty dict."""
        result = get_config()
        assert result == {}
    
    def test_missing_config_file_creates_directory(self, temp_home):
        """When config file doesn't exist, creates ~/.waggle directory."""
        waggle_dir = temp_home / ".waggle"
        assert not waggle_dir.exists()
        
        get_config()
        
        assert waggle_dir.exists()
        assert waggle_dir.is_dir()
    
    def test_valid_json_returns_parsed_config(self, config_file):
        """When config file contains valid JSON, returns parsed dict."""
        config_data = {"database_path": "/custom/path/db.sqlite"}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = get_config()
        assert result == config_data
    
    def test_malformed_json_returns_empty_dict(self, config_file):
        """When config file contains malformed JSON, returns empty dict."""
        with open(config_file, 'w') as f:
            f.write("{this is not valid json")
        
        result = get_config()
        assert result == {}
    
    def test_non_dict_json_returns_empty_dict(self, config_file):
        """When config file contains non-dict JSON, returns empty dict."""
        with open(config_file, 'w') as f:
            json.dump(["not", "a", "dict"], f)
        
        result = get_config()
        assert result == {}
    
    def test_empty_file_returns_empty_dict(self, config_file):
        """When config file is empty, returns empty dict."""
        config_file.touch()
        
        result = get_config()
        assert result == {}


class TestGetDbPath:
    """Tests for get_db_path() function."""
    
    def test_no_config_returns_default_path(self, temp_home):
        """When no config exists, returns default database path."""
        result = get_db_path()
        expected = str(temp_home / ".waggle" / "agent_state.db")
        assert result == expected
    
    def test_config_with_database_path_returns_custom_path(self, config_file):
        """When config specifies database_path, returns that path."""
        custom_path = "/custom/path/my_database.db"
        config_data = {"database_path": custom_path}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = get_db_path()
        assert result == str(Path(custom_path).absolute())
    
    def test_tilde_expansion_in_custom_path(self, config_file, temp_home):
        """When config specifies path with tilde, expands it correctly."""
        config_data = {"database_path": "~/.waggle/custom.db"}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = get_db_path()
        expected = str(temp_home / ".waggle" / "custom.db")
        assert result == expected
    
    def test_returns_absolute_path(self, config_file):
        """get_db_path() always returns absolute path."""
        config_data = {"database_path": "relative/path/db.sqlite"}
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        result = get_db_path()
        assert Path(result).is_absolute()
    
    def test_malformed_config_returns_default_path(self, config_file, temp_home):
        """When config is malformed, falls back to default path."""
        with open(config_file, 'w') as f:
            f.write("{malformed json")
        
        result = get_db_path()
        expected = str(temp_home / ".waggle" / "agent_state.db")
        assert result == expected
