import os
import json
import tempfile
import shutil
import threading

CURRENT_CONFIG_VERSION = 1

# Threading lock for config operations (desktop app can use this)
config_lock = threading.Lock()

def atomic_save_json(path, data):
    """Atomically save JSON data to a file."""
    dir_name = os.path.dirname(path)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=2)
        tempname = tf.name
    os.replace(tempname, path)

def backup_config(path):
    """Backup the config file to path.bak if it exists."""
    if os.path.exists(path):
        shutil.copy2(path, path + '.bak')

def validate_config(data, default):
    """Validate config dict, fill in missing fields from default."""
    if not isinstance(data, dict):
        return dict(default)
    out = dict(default)
    out.update({k: v for k, v in data.items() if k in default})
    # Recursively validate nested dicts/lists if needed
    for k, v in default.items():
        if isinstance(v, dict):
            out[k] = validate_config(data.get(k, {}), v)
        elif isinstance(v, list) and isinstance(data.get(k), list):
            out[k] = data[k]
    return out

def migrate_config(data, current_version=CURRENT_CONFIG_VERSION):
    """Migrate config to the current version if needed. Extend as versions change."""
    version = data.get('version', 1)
    # Example: if version < 2: ...
    # For now, just set version
    data['version'] = current_version
    return data

def load_config_with_recovery(path, default):
    """Load config, validate, migrate, and recover from backup if needed."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data = migrate_config(data)
        data = validate_config(data, default)
        return data
    except Exception:
        # Try backup
        bak_path = path + '.bak'
        if os.path.exists(bak_path):
            try:
                with open(bak_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data = migrate_config(data)
                data = validate_config(data, default)
                return data
            except Exception:
                pass
        # Fallback to default
        return dict(default) 