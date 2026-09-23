from __future__ import annotations

import json
import uuid
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
        "enabled": True,
        "to": [],
        "smtpHost": "",
        "smtpPort": 587,
        "smtpUser": "",
        "smtpPassword": "",
        "fromName": "DYP_Schedular",
        "fromAddress": "",
        "useTls": True,
    },
    "sources": [],
    "activeSourceId": "",
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
    return migrate_sources(_merge(DEFAULT_CONFIG, stored))


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
    mail = view["email"]
    for mongo in [view["mongodb"], *(view.get("sources") or [])]:
        mongo["passwordSet"] = bool(mongo.get("password"))
        mongo["password"] = ""
    mail["smtpPasswordSet"] = bool(mail.get("smtpPassword"))
    mail["smtpPassword"] = ""
    return view


def source_address(source: dict) -> str:
    host = str(source.get("host") or "")
    if host.startswith("mongodb://") or host.startswith("mongodb+srv://"):
        return host
    return f"{host}:{int(source.get('port') or 27017)}"


def source_label(source: dict) -> str:
    name = " ".join(str(source.get("label") or "").split())
    address = source_address(source)
    host = str(source.get("host") or "")
    if name and name not in {address, host}:
        return f"{name} · {address}"
    return address


def _complete_source(item: dict) -> dict:
    columns = []
    for name in item.get("columns") or []:
        text = str(name).strip()
        if text and text not in columns:
            columns.append(text)
    return {
        "id": str(item.get("id") or "") or uuid.uuid4().hex[:12],
        "label": " ".join(str(item.get("label") or "").split()),
        "host": str(item.get("host") or ""),
        "port": int(item.get("port") or 27017),
        "username": str(item.get("username") or ""),
        "password": str(item.get("password") or ""),
        "authSource": str(item.get("authSource") or "admin") or "admin",
        "database": str(item.get("database") or ""),
        "collection": str(item.get("collection") or ""),
        "timestampField": str(item.get("timestampField") or ""),
        "columns": columns,
    }


def migrate_sources(config: dict) -> dict:
    cleaned = []
    for item in config.get("sources") or []:
        if isinstance(item, dict) and str(item.get("host") or "").strip():
            cleaned.append(_complete_source(item))
    if not cleaned:
        mongo = config.get("mongodb") or {}
        if str(mongo.get("host") or "").strip():
            cleaned.append(
                _complete_source(
                    {
                        "id": "primary",
                        "label": str(mongo.get("host") or ""),
                        "host": mongo.get("host") or "",
                        "port": mongo.get("port") or 27017,
                        "username": mongo.get("username") or "",
                        "password": mongo.get("password") or "",
                        "authSource": mongo.get("authSource") or "admin",
                        "database": mongo.get("database") or "",
                        "collection": mongo.get("collection") or "",
                        "timestampField": config.get("timestampField") or "",
                        "columns": list(config.get("columns") or []),
                    }
                )
            )
    config["sources"] = cleaned
    active = str(config.get("activeSourceId") or "")
    if not any(item["id"] == active for item in cleaned):
        config["activeSourceId"] = cleaned[0]["id"] if cleaned else ""
    sync_active_source(config)
    return config


def find_source(config: dict, source_id: str | None = None, fallback: bool = True) -> dict | None:
    sources = config.get("sources") or []
    wanted = source_id if source_id else config.get("activeSourceId")
    for source in sources:
        if source.get("id") == wanted:
            return source
    if fallback and not source_id:
        return sources[0] if sources else None
    return None


def sync_active_source(config: dict) -> None:
    source = find_source(config)
    if source is None:
        return
    config["activeSourceId"] = source["id"]
    config["mongodb"] = {
        "host": source["host"],
        "port": source["port"],
        "username": source["username"],
        "password": source["password"],
        "authSource": source["authSource"],
        "database": source["database"],
        "collection": source["collection"],
    }
    config["timestampField"] = source["timestampField"]
    config["columns"] = list(source["columns"])


def keep_secret(incoming: str, previous: str) -> str:
    if incoming:
        return incoming
    return previous or ""
