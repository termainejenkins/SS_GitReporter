import json
import os
from typing import Dict, Any

class ConfigManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            self.create_default_config()
        
        with open(self.config_path, 'r') as f:
            return json.load(f)

    def create_default_config(self) -> None:
        default_config = {
            "project_path": "",
            "check_interval_minutes": 30,
            "max_commits_to_show": 5,
            "ignored_files": ["*.uasset", "Saved/*", "Intermediate/*"]
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=4)

    def get(self, key: str) -> Any:
        return self.config.get(key) 