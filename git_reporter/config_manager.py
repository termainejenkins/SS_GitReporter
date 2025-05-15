import os
from typing import Dict, Any
from .config_utils import (
    atomic_save_json, backup_config, load_config_with_recovery, CURRENT_CONFIG_VERSION
)

DEFAULT_CONFIG = {
    "version": CURRENT_CONFIG_VERSION,
    "project_path": "",
    "check_interval_minutes": 30,
    "max_commits_to_show": 5,
    "ignored_files": ["*.uasset", "Saved/*", "Intermediate/*"],
    "auto_start_monitoring": True,
    "start_with_log_open": False
}

class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        return load_config_with_recovery(self.config_path, DEFAULT_CONFIG)

    def save_config(self) -> None:
        backup_config(self.config_path)
        atomic_save_json(self.config_path, self.config)

    def get(self, key: str) -> Any:
        return self.config.get(key) 