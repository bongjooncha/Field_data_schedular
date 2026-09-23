from __future__ import annotations

import json
from copy import deepcopy
from threading import Lock

from .paths import config_path

_lock = Lock()

DEFAULT_CONFIG: dict = {
    "mongodb": {
        "host": "",
        "port": 27017,
        "username": "",
        "password": "",
        "authSource": "admin",
        "database": "",
        "collection": "",
    },
    "timestampField": "",
    "columns": [],
    "schedule": {
        "period": "daily",
        "hour": 8,
        "minute": 0,
        "weekday": "mon",
        "timezone": "Asia/Seoul",
    },
    "email": {
        "to": [],
        "smtpHost": "",
        "smtpPort": 587,
        "smtpUser": "",
        "smtpPassword": "",
        "fromName": "DYP_Schedular",
        "fromAddress": "",
        "useTls": True,
    },
    "setupComplete": False,
}


def _merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    with path.open(encoding="utf-8") as handle:
        stored = json.load(handle)
    if not isinstance(stored, dict):
        return deepcopy(DEFAULT_CONFIG)
    return _merge(DEFAULT_CONFIG, stored)


def save_config(config: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with _lock:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)


def public_config(config: dict) -> dict:
    view = deepcopy(config)
    mongo = view["mongodb"]
    mail = view["email"]
    mongo["passwordSet"] = bool(mongo.get("password"))
    mongo["password"] = ""
    mail["smtpPasswordSet"] = bool(mail.get("smtpPassword"))
    mail["smtpPassword"] = ""
    return view


def keep_secret(incoming: str, previous: str) -> str:
    if incoming:
        return incoming
    return previous or ""
