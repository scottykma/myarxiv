import os
import shutil
from pathlib import Path
from typing import Any

import yaml

_CONFIG: dict[str, Any] | None = None
_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found at {_CONFIG_PATH}. Copy config.example.yaml to config.yaml first."
        )

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file at {_CONFIG_PATH} must contain a YAML mapping")

    _CONFIG = data
    return _CONFIG


def config_path() -> Path:
    return _CONFIG_PATH


def backup_path() -> Path:
    return _CONFIG_PATH.with_name(_CONFIG_PATH.name + ".bak")


def get(key: str, default: Any = None) -> Any:
    config = load_config()
    keys = key.split(".")
    val = config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
        if val is None:
            return default
    return val


def set(key: str, value: Any) -> None:
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value


def replace(data: dict[str, Any]) -> None:
    global _CONFIG
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping")
    _CONFIG = data


def _dump() -> str:
    return yaml.dump(_CONFIG, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _write_atomic(text: str) -> None:
    temp = _CONFIG_PATH.with_name(_CONFIG_PATH.name + ".tmp")
    try:
        with open(temp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp, _CONFIG_PATH)
    finally:
        if temp.exists():
            temp.unlink()


def save() -> None:
    if _CONFIG is None:
        return
    text = _dump()
    if _CONFIG_PATH.exists():
        shutil.copy2(_CONFIG_PATH, backup_path())
    _write_atomic(text)


def undo() -> bool:
    global _CONFIG
    backup = backup_path()
    if not backup.exists():
        return False
    try:
        with open(backup, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    _CONFIG = data
    _write_atomic(_dump())
    try:
        backup.unlink()
    except OSError:
        pass
    return True


def reload() -> dict[str, Any]:
    global _CONFIG
    _CONFIG = None
    return load_config()


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)
