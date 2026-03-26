from pathlib import Path
import toml

CONFIG_DIR = Path.home() / ".config" / "pomocli"
CONFIG_PATH = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = {
    "session_duration": 25,
    "break_duration": 5,
    "idle_timeout": 300,
    "sound_enabled": True,
    "history_retention_days": 30,
    "hotkey_distraction": "cmd+shift+d",
    "distraction_extend_minutes": 2,
    "timezone": "auto",
}


def load_config() -> dict:
    """Read TOML config and merge with defaults for any missing keys."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        user_config = toml.load(CONFIG_PATH)
        config.update(user_config)
    return config


def save_config(config: dict) -> None:
    """Write config dict to TOML file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        toml.dump(config, f)
