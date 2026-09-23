from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from time import perf_counter
from typing import Iterator
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from .config_store import find_source, source_label

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

SYSTEM_DATABASES = {"admin", "local", "config"}
VALUE_LIMIT = 40


class MongoServiceError(Exception):
    pass


def scrub_secrets(message: str, config: dict) -> str:
    text = message
    mail = config.get("email", {})
    secrets = []
    accounts = [config.get("mongodb") or {}, *(config.get("sources") or [])]
    for account in accounts:
        secrets.extend((account.get("password"), account.get("username")))
    secrets.append(mail.get("smtpPassword"))
    hidden = []
    for secret in secrets:
        if not secret:
            continue
        value = str(secret)
        hidden.append(value)
        encoded = quote_plus(value)
        if encoded != value:
            hidden.append(encoded)
    for secret in hidden:
        text = text.replace(secret, "******")
    return text


def normalize_host(host: str, port: int) -> tuple[str, int]:
    value = host.strip()
    if value.startswith("mongodb://") or value.startswith("mongodb+srv://"):
        return value, port
    if value.count(":") == 1:
        host_part, port_part = value.rsplit(":", 1)
        if port_part.isdigit() and host_part:
            return host_part, int(port_part)
    return value, port


def build_uri(mongo: dict) -> str:
    host, port = normalize_host(str(mongo.get("host") or ""), int(mongo.get("port") or 27017))
    if host.startswith("mongodb://") or host.startswith("mongodb+srv://"):
        return host
    username = str(mongo.get("username") or "")
    password = str(mongo.get("password") or "")
    auth_source = quote_plus(str(mongo.get("authSource") or "admin"))
    if username:
        user = quote_plus(username)
        secret = quote_plus(password)
        return f"mongodb://{user}:{secret}@{host}:{port}/?authSource={auth_source}"
    return f"mongodb://{host}:{port}/"


def validate_field_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or ".." in cleaned or cleaned.startswith(".") or cleaned.endswith("."):
        raise MongoServiceError("컬럼 이름이 올바르지 않습니다.")
    for part in cleaned.split("."):
        if not part or part.startswith("$"):
            raise MongoServiceError("컬럼 이름에 사용할 수 없는 문자가 있습니다.")
    return cleaned


def _client_options(uri: str) -> dict:
    options = {"serverSelectionTimeoutMS": 6000}
    host_part = uri.split("://", 1)[-1].split("/", 1)[0]
    if uri.startswith("mongodb+srv://") or "replicaSet=" in uri or "," in host_part:
        return options
    options["directConnection"] = True
    return options


@contextmanager
def connect(config: dict, source: dict | None = None) -> Iterator[MongoClient]:
    mongo = source or find_source(config)
    if mongo is None or not str(mongo.get("host") or "").strip():
        raise MongoServiceError("데이터베이스 주소를 입력해 주세요.")
    uri = build_uri(mongo)
    client = MongoClient(uri, **_client_options(uri))
    try:
        client.admin.command("ping")
        yield client
    except PyMongoError as exc:
        raise MongoServiceError(f"MongoDB에 연결하지 못했습니다. {scrub_secrets(str(exc), config)}") from exc
    finally:
        client.close()


def list_databases(config: dict, source: dict | None = None) -> list[str]:
    with connect(config, source) as client:
        names = client.list_database_names()
    return sorted(name for name in names if name not in SYSTEM_DATABASES)


def list_collections(config: dict, database: str, source: dict | None = None) -> list[str]:
    if not database:
        raise MongoServiceError("데이터베이스를 선택해 주세요.")
    with connect(config, source) as client:
        if database not in client.list_database_names():
            raise MongoServiceError(f"데이터베이스 '{database}'을 찾지 못했습니다.")
        names = client[database].list_collection_names()
    return sorted(names)


def _type_name(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, datetime):
        return "date"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _walk(document: dict, prefix: str, found: dict[str, dict], depth: int) -> None:
    for key, value in document.items():
        if key == "_id" and not prefix:
            continue
        if key.startswith("$"):
            continue
        name = f"{prefix}.{key}" if prefix else key
        slot = found.setdefault(name, {"types": set(), "present": 0})
        if value is not None:
            slot["present"] += 1
            slot["types"].add(_type_name(value))
        if isinstance(value, dict) and depth < 2:
            _walk(value, name, found, depth + 1)


def inspect_fields(
    config: dict,
    database: str,
    collection: str,
    sample_size: int = 80,
    source: dict | None = None,
) -> dict:
    if not database or not collection:
        raise MongoServiceError("데이터베이스와 컬렉션을 선택해 주세요.")
    with connect(config, source) as client:
        coll = client[database][collection]
        documents = list(coll.find().sort("_id", -1).limit(sample_size))
    found: dict[str, dict] = {}
    for document in documents:
        _walk(document, "", found, 0)
    fields = [
        {
            "name": name,
            "types": sorted(info["types"]),
            "present": info["present"],
        }
        for name, info in found.items()
    ]
    fields.sort(key=lambda item: item["name"])
    candidates = [
        item["name"]
        for item in fields
        if "date" in item["types"]
        or any(token in item["name"].lower() for token in ("time", "date", "created", "timestamp", "ts"))
    ]
    return {"fields": fields, "timestampCandidates": candidates, "sampled": len(documents)}


def _timezone(config: dict) -> ZoneInfo:
    name = config.get("schedule", {}).get("timezone") or "Asia/Seoul"
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise MongoServiceError("시간대를 읽지 못했습니다.") from exc


def resolve_window(config: dict, end_date: date, span: str | None) -> tuple[datetime, datetime, str]:
    period = span or config.get("schedule", {}).get("period") or "daily"
    if period not in {"daily", "weekly"}:
        raise MongoServiceError("지원하지 않는 집계 주기입니다.")
    tz = _timezone(config)
    end = datetime(end_date.year, end_date.month, end_date.day, tzinfo=tz) + timedelta(days=1)
    days = 7 if period == "weekly" else 1
    start = end - timedelta(days=days)
    label = _window_label(start, end)
    return start, end, label


def _window_label(start: datetime, end: datetime) -> str:
    last = end - timedelta(days=1)
    if start.date() == last.date():
        return f"{start.year}년 {start.month}월 {start.day}일"
    return (
        f"{start.year}년 {start.month}월 {start.day}일"
        f" – {last.year}년 {last.month}월 {last.day}일"
    )


def default_end_date(config: dict) -> date:
    tz = _timezone(config)
    return (datetime.now(tz) - timedelta(days=1)).date()


def today_in_config(config: dict) -> date:
    return datetime.now(_timezone(config)).date()


def _get_path(document: dict, field: str):
    current = document
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def detect_timestamp_mode(coll: Collection, field: str) -> str:
    document = coll.find_one({field: {"$exists": True, "$ne": None}}, projection={field: 1})
    if not document:
        return "datetime"
    value = _get_path(document, field)
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, bool):
        return "datetime"
    if isinstance(value, (int, float)):
        return "epoch_ms" if abs(value) > 10_000_000_000 else "epoch_s"
    if isinstance(value, str):
        return "string"
    return "datetime"


def _match_and_date_expr(field: str, mode: str, start: datetime, end: datetime):
    if mode == "epoch_ms":
        match = {field: {"$gte": int(start.timestamp() * 1000), "$lt": int(end.timestamp() * 1000)}}
        expr = {"$toDate": f"${field}"}
        return match, expr
    if mode == "epoch_s":
        match = {field: {"$gte": int(start.timestamp()), "$lt": int(end.timestamp())}}
        expr = {"$toDate": {"$multiply": [f"${field}", 1000]}}
        return match, expr
    if mode == "string":
        match = {
            field: {
                "$gte": start.strftime("%Y-%m-%d"),
                "$lt": end.strftime("%Y-%m-%d"),
            }
        }
        expr = {
            "$dateFromString": {
                "dateString": f"${field}",
                "onError": None,
                "onNull": None,
            }
        }
        return match, expr
    # 시간대 없이 저장된 시각은 적힌 날짜 그대로 자른다.
    # 서울 시각으로 바꾸면 하루가 9시간 밀려 고른 날짜와 어긋난다.
    return {field: {"$gte": start.replace(tzinfo=None), "$lt": end.replace(tzinfo=None)}}, f"${field}"


def format_stored_value(value) -> str:
    if value is None:
        return "빈 값"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text if len(text) <= 80 else f"{text[:77]}..."
    return str(value)


def _present_expr(field: str) -> dict:
    path = f"${field}"
    return {
        "$and": [
            {"$ne": [{"$type": path}, "missing"]},
            {"$ne": [path, None]},
            {"$not": [{"$in": [path, ["", []]]}]},
        ]
    }


def _timestamp_indexed(coll: Collection, field: str) -> bool:
    try:
        indexes = coll.index_information()
    except PyMongoError:
        return False
    for index in indexes.values():
        keys = index.get("key") or []
        if keys and keys[0][0] == field:
            return True
    return False


def _bucket_pipeline(date_expr, timezone_name: str, daily: bool) -> list[dict]:
    if daily:
        group_id = {"$hour": {"date": date_expr, "timezone": timezone_name}}
    else:
        group_id = {
            "$dateToString": {
                "format": "%Y-%m-%d",
                "date": date_expr,
                "timezone": timezone_name,
            }
        }
    return [
        {"$group": {"_id": group_id, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]


def internet_reachable(config: dict | None = None) -> bool:
    targets = [("1.1.1.1", 443), ("8.8.8.8", 53)]
    email = (config or {}).get("email") or {}
    smtp_host = str(email.get("smtpHost") or "").strip()
    if email.get("enabled", True) and smtp_host:
        targets.append((smtp_host, int(email.get("smtpPort") or 587)))
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            continue
    return False


def probe_source(config: dict, source: dict) -> dict:
    started = perf_counter()
    error = None
    online = False
    try:
        with connect(config, source):
            online = True
    except MongoServiceError as exc:
        error = str(exc)
    return {
        "id": source.get("id"),
        "label": source_label(source),
        "host": source.get("host") or "",
        "port": int(source.get("port") or 27017),
        "database": source.get("database") or "",
        "collection": source.get("collection") or "",
        "online": online,
        "error": error,
        "latencyMs": int((perf_counter() - started) * 1000),
    }


def probe_all(config: dict) -> dict:
    sources = list(config.get("sources") or [])
    workers = max(len(sources) + 1, 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        internet_future = pool.submit(internet_reachable, config)
        probed = list(pool.map(lambda source: probe_source(config, source), sources))
        internet = internet_future.result()
    return {"internet": internet, "sources": probed}


def build_report(
    config: dict,
    end_date: date | None = None,
    span: str | None = None,
    source_id: str | None = None,
) -> dict:
    source = find_source(config, source_id, fallback=not bool(source_id))
    if source is None:
        raise MongoServiceError("데이터베이스 주소를 선택해 주세요.")
    database = source.get("database") or ""
    collection_name = source.get("collection") or ""
    if not str(source.get("timestampField") or "").strip():
        raise MongoServiceError("시간 기준 컬럼을 선택해 주세요.")
    timestamp_field = validate_field_name(source["timestampField"])
    columns = [validate_field_name(name) for name in source.get("columns") or []]
    if not columns:
        raise MongoServiceError("확인할 컬럼을 하나 이상 선택해 주세요.")
    if timestamp_field in columns:
        columns = [name for name in columns if name != timestamp_field]
        if not columns:
            raise MongoServiceError("시간 컬럼 외에 확인할 컬럼을 선택해 주세요.")

    period = span or config.get("schedule", {}).get("period") or "daily"
    selected = end_date or default_end_date(config)
    start, end, label = resolve_window(config, selected, period)
    timezone_name = config.get("schedule", {}).get("timezone") or "Asia/Seoul"
    daily = (end - start) <= timedelta(days=1)

    with connect(config, source) as client:
        database_handle = client[database]
        if collection_name not in database_handle.list_collection_names():
            raise MongoServiceError(f"컬렉션 '{collection_name}'을 찾지 못했습니다.")
        coll = database_handle[collection_name]
        mode = detect_timestamp_mode(coll, timestamp_field)
        match, date_expr = _match_and_date_expr(timestamp_field, mode, start, end)
        bucket_timezone = "UTC" if mode == "datetime" else timezone_name
        indexed = _timestamp_indexed(coll, timestamp_field)

        summary_group: dict = {"_id": None}
        for index, name in enumerate(columns):
            summary_group[f"c{index}"] = {"$sum": {"$cond": [_present_expr(name), 1, 0]}}

        facet: dict = {
            "summary": [{"$group": {**summary_group, "total": {"$sum": 1}}}],
            "buckets": _bucket_pipeline(date_expr, bucket_timezone, daily),
            "bounds": [
                {
                    "$group": {
                        "_id": None,
                        "first": {"$min": date_expr},
                        "last": {"$max": date_expr},
                    }
                }
            ],
        }
        for index, name in enumerate(columns):
            facet[f"v{index}"] = [
                {"$group": {"_id": {"$ifNull": [f"${name}", None]}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
                {"$limit": VALUE_LIMIT + 1},
            ]
        pipeline = [{"$match": match}, {"$facet": facet}]
        try:
            aggregated = list(coll.aggregate(pipeline, maxTimeMS=60_000))
        except PyMongoError as exc:
            raise MongoServiceError(
                f"수집량을 계산하지 못했습니다. {scrub_secrets(str(exc), config)}"
            ) from exc

        facet = aggregated[0] if aggregated else {}
        summary_preview = (facet.get("summary") or [{}])[0]
        active_dates: list[dict] = []
        if not int(summary_preview.get("total") or 0):
            try:
                date_rows = list(
                    coll.aggregate(
                        [
                            {
                                "$group": {
                                    "_id": {
                                        "$dateToString": {
                                            "format": "%Y-%m-%d",
                                            "date": f"${timestamp_field}",
                                            "timezone": "UTC",
                                        }
                                    },
                                    "count": {"$sum": 1},
                                }
                            },
                            {"$sort": {"_id": 1}},
                        ],
                        maxTimeMS=120_000,
                    )
                )
            except PyMongoError as exc:
                raise MongoServiceError(
                    f"데이터가 있는 날짜를 찾지 못했습니다. {scrub_secrets(str(exc), config)}"
                ) from exc
            active_dates = [
                {"date": row.get("_id"), "count": int(row.get("count") or 0)}
                for row in date_rows
                if row.get("_id")
            ]

    facet = aggregated[0] if aggregated else {}
    summary_rows = facet.get("summary") or []
    summary = summary_rows[0] if summary_rows else {}
    total = int(summary.get("total") or 0)
    column_rows = []
    for index, name in enumerate(columns):
        present = int(summary.get(f"c{index}") or 0)
        missing = max(total - present, 0)
        fill_rate = (present / total) if total else 0
        raw_values = facet.get(f"v{index}") or []
        truncated = len(raw_values) > VALUE_LIMIT
        values = []
        for item in raw_values[:VALUE_LIMIT]:
            count = int(item.get("count") or 0)
            values.append(
                {
                    "value": format_stored_value(item.get("_id")),
                    "count": count,
                    "rate": round((count / total), 4) if total else 0,
                }
            )
        column_rows.append(
            {
                "name": name,
                "present": present,
                "missing": missing,
                "fillRate": round(fill_rate, 4),
                "status": _column_status(total, fill_rate),
                "values": values,
                "valuesTruncated": truncated,
            }
        )

    raw_buckets = {item.get("_id"): int(item.get("count") or 0) for item in facet.get("buckets") or []}
    if daily:
        buckets = [{"label": f"{hour:02d}", "count": raw_buckets.get(hour, 0)} for hour in range(24)]
        bucket_kind = "hour"
    else:
        buckets = []
        cursor = start
        while cursor < end:
            key = cursor.strftime("%Y-%m-%d")
            buckets.append({"label": key, "count": raw_buckets.get(key, 0)})
            cursor += timedelta(days=1)
        bucket_kind = "day"

    bounds = (facet.get("bounds") or [{}])[0]
    average = round(sum(row["fillRate"] for row in column_rows) / len(column_rows), 4) if column_rows else 0
    return {
        "sourceId": source.get("id"),
        "sourceLabel": source_label(source),
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": label,
            "period": "weekly" if not daily else "daily",
            "coveredEnd": (end - timedelta(days=1)).date().isoformat(),
        },
        "database": database,
        "collection": collection_name,
        "timestampField": timestamp_field,
        "timestampMode": mode,
        "timestampIndexed": indexed,
        "totalDocuments": total,
        "averageFillRate": average,
        "status": _report_status(total, column_rows),
        "columns": column_rows,
        "bucketKind": bucket_kind,
        "buckets": buckets,
        "firstAt": _iso(bounds.get("first")),
        "lastAt": _iso(bounds.get("last")),
        "activeDates": active_dates,
    }


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _column_status(total: int, fill_rate: float) -> str:
    if total == 0 or fill_rate == 0:
        return "empty"
    if fill_rate >= 0.999:
        return "ok"
    return "partial"


def _report_status(total: int, columns: list[dict]) -> str:
    if total == 0:
        return "empty"
    if any(row["status"] != "ok" for row in columns):
        return "partial"
    return "ok"
