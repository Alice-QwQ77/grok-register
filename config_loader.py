from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_PATH = Path(__file__).parent / "config.json"
ENV_PREFIX = "GROK_REGISTER_"


def _parse_bool(raw: str) -> bool:
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _set_nested(config: Dict[str, Any], path: str, value: Any) -> None:
    current = config
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _load_config_file() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_config() -> Dict[str, Any]:
    config = deepcopy(_load_config_file())

    env_mapping = {
        "RUN_COUNT": ("run.count", int),
        "EMAIL_PROVIDER": ("email_provider", str),
        "DUCKMAIL_API_BASE": ("duckmail_api_base", str),
        "DUCKMAIL_BEARER": ("duckmail_bearer", str),
        "TEMP_MAIL_API_BASE": ("temp_mail_api_base", str),
        "TEMP_MAIL_API_KEY": ("temp_mail_api_key", str),
        "TEMP_MAIL_PROVIDER": ("temp_mail_provider", str),
        "TEMP_MAIL_DOMAIN": ("temp_mail_domain", str),
        "TEMP_MAIL_PREFIX": ("temp_mail_prefix", str),
        "PROXY": ("proxy", str),
        "BROWSER_PROXY": ("browser_proxy", str),
        "API_ENDPOINT": ("api.endpoint", str),
        "API_TOKEN": ("api.token", str),
        "API_APPEND": ("api.append", _parse_bool),
        "WEBUI_HOST": ("webui.host", str),
        "WEBUI_PORT": ("webui.port", int),
        "WEBUI_USERNAME": ("webui.username", str),
        "WEBUI_PASSWORD": ("webui.password", str),
        "WEBUI_SECRET_KEY": ("webui.secret_key", str),
    }

    for env_key, (config_path, caster) in env_mapping.items():
        raw = os.environ.get(f"{ENV_PREFIX}{env_key}")
        if raw is None or raw == "":
            continue
        try:
            value = caster(raw)
        except Exception:
            continue
        _set_nested(config, config_path, value)

    return config


def get_config_value(config: Dict[str, Any], path: str, default: Optional[Any] = None) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current
