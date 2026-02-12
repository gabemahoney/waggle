"""Configuration management for Waggle.

Reads configuration from ~/.waggle/config.json with intelligent defaults.
Handles missing files, malformed JSON, and provides fallback values.
"""

import json
from pathlib import Path
from typing import Dict, Any


# Default database path for agent state storage.
# NOTE: This constant is also used in hooks/set_state.sh:15
# Both locations must be kept in sync if the path changes.
def _get_default_db_path() -> Path:
    """Get default database path. Computed lazily to support testing with mocked Path.home()."""
    return Path.home() / ".waggle" / "agent_state.db"


def get_config() -> Dict[str, Any]:
    """Read and parse ~/.waggle/config.json.
    
    Handles:
    - Missing config file (returns empty dict)
    - Malformed JSON (logs warning, returns empty dict)
    - Missing ~/.waggle directory (creates it)
    
    Returns:
        Dict containing configuration values, or empty dict if config missing/malformed
    """
    # Ensure ~/.waggle directory exists
    config_dir = Path.home() / ".waggle"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = config_dir / "config.json"
    
    # Handle missing config file
    if not config_file.exists():
        return {}
    
    # Read and parse config
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            if not isinstance(config, dict):
                return {}
            return config
    except json.JSONDecodeError:
        return {}
    except Exception:
        return {}


def get_db_path() -> str:
    """Get database path from config with fallback to default.
    
    Reads config via get_config() and returns database path.
    Falls back to ~/.waggle/agent_state.db if not specified in config.
    
    Returns:
        Absolute path to database file (tilde-expanded)
    """
    config = get_config()
    
    # Get database path from config or use default
    db_path = config.get("database_path")
    if db_path is None:
        db_path = str(_get_default_db_path())
    
    # Expand tilde and return absolute path
    return str(Path(db_path).expanduser().absolute())
