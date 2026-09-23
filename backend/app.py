from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .config_store import find_source, keep_secret, load_config, public_config, save_config, sync_active_source
from .mailer import mail_enabled, normalize_recipients, send_digest, send_test, validate_delivery
from .mongo_service import (
    MongoServiceError,
    build_report,
    default_end_date,
    inspect_fields,
    list_collections,
    list_databases,
    normalize_host,
    probe_all,
    scrub_secrets,
    today_in_config,
    validate_field_name,
)
from .paths import config_path, frontend_dist
from .scheduler import (
    next_run_at,
    read_last_run,
    reschedule,
    collect_reports,
    delivery_summary,
    run_report_job,
    start_scheduler,
    stop_scheduler,
    write_last_run,
)

DEV_HINT = """
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><title>현장 데이터 점검</title></head>
<body style="font-family:Segoe UI,sans-serif;padding:40px;background:#f6f5f4">
  <h1>화면 파일이 없습니다</h1>
  <p>개발 중에는 프로젝트 폴더에서 <code>npm start</code>를 실행하세요.</p>
  <p>데스크톱 창으로 보려면 먼저 <code>npm run build:ui</code>로 화면을 만든 뒤 <code>python launcher.py</code>를 실행하세요.</p>
</body>
</html>
"""


class ConnectionIn(BaseModel):
    id: str = ""
    label: str = ""
    host: str
    port: int = 27017
    username: str = ""
    password: str = ""
    authSource: str = "admin"


class WatchIn(BaseModel):
    sourceId: str = ""
    database: str
    collection: str
    timestampField: str
    columns: list[str] = Field(default_factory=list)


class ActiveIn(BaseModel):
    id: str


class DeliveryIn(BaseModel):
    enabled: bool = True
    to: list[str] | str = ""
    smtpHost: str = ""
    smtpPort: int = 587
    smtpUser: str = ""
    smtpPassword: str = ""
    fromName: str = "DYP_Schedular"
    fromAddress: str = ""
    useTls: bool = True
    period: str = "daily"
    hour: int = 8
    minute: int = 0
    weekday: str = "mon"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="현장 데이터 점검", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _fail(exc: Exception, config: dict | None = None) -> HTTPException:
    message = str(exc)
    if config is not None:
        message = scrub_secrets(message, config)
    status = 400 if isinstance(exc, MongoServiceError) else 500
    return HTTPException(status_code=status, detail=message)


def _status_payload() -> dict:
    config = load_config()
    today = today_in_config(config)
    yesterday = default_end_date(config)
    return {
        "setupComplete": bool(config.get("setupComplete")),
        "config": public_config(config),
        "configPath": str(config_path()),
        "today": today.isoformat(),
        "yesterday": yesterday.isoformat(),
        "nextRun": next_run_at(),
        "lastRun": read_last_run(),
    }


def _blank_source() -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "label": "",
        "host": "",
        "port": 27017,
        "username": "",
        "password": "",
        "authSource": "admin",
        "database": "",
        "collection": "",
        "timestampField": "",
        "columns": [],
    }


def _apply_connection(payload: ConnectionIn) -> tuple[dict, str, list[str]]:
    config = load_config()
    if not payload.host.strip():
        raise MongoServiceError("데이터베이스 주소를 입력해 주세요.")
    if not 1 <= payload.port <= 65535:
        raise MongoServiceError("포트 번호를 확인해 주세요.")
    host, port = normalize_host(payload.host.strip(), payload.port)
    if payload.id:
        source = find_source(config, payload.id, fallback=False)
        if source is None:
            raise MongoServiceError("주소를 찾지 못했습니다.")
    else:
        source = _blank_source()
        config["sources"].append(source)
    uses_uri = host.startswith("mongodb://") or host.startswith("mongodb+srv://")
    same_account = host == source.get("host") and payload.username.strip() == (source.get("username") or "")
    password = payload.password
    if payload.username.strip() and not password and same_account:
        password = keep_secret("", source.get("password") or "")
    if payload.username.strip() and not password and not uses_uri:
        raise MongoServiceError("비밀번호를 입력해 주세요.")
    if not payload.username.strip() and not uses_uri:
        password = ""
    source.update(
        {
            "label": " ".join(payload.label.split()),
            "host": host,
            "port": port,
            "username": payload.username.strip(),
            "password": password,
            "authSource": (payload.authSource or "admin").strip() or "admin",
        }
    )
    databases = list_databases(config, source)
    config["activeSourceId"] = source["id"]
    sync_active_source(config)
    return config, source["id"], databases


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def status():
    return _status_payload()


@app.post("/api/setup/connection")
def setup_connection(payload: ConnectionIn):
    config = None
    try:
        config, source_id, databases = _apply_connection(payload)
        save_config(config)
    except MongoServiceError as exc:
        raise _fail(exc, config or load_config()) from exc
    return {"ok": True, "sourceId": source_id, "databases": databases, "status": _status_payload()}


def _selected_source(config: dict, source_id: str) -> dict:
    source = find_source(config, source_id or None, fallback=not bool(source_id))
    if source is None:
        raise MongoServiceError("데이터베이스 주소를 먼저 연결해 주세요.")
    return source


@app.get("/api/connectivity")
def connectivity():
    config = load_config()
    return probe_all(config)


@app.post("/api/sources/active")
def activate_source(payload: ActiveIn):
    config = load_config()
    source = find_source(config, payload.id, fallback=False)
    if source is None:
        raise HTTPException(status_code=404, detail="주소를 찾지 못했습니다.")
    config["activeSourceId"] = source["id"]
    sync_active_source(config)
    save_config(config)
    return {"ok": True, "status": _status_payload()}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str):
    config = load_config()
    sources = list(config.get("sources") or [])
    if len(sources) <= 1:
        raise HTTPException(status_code=400, detail="주소는 하나 이상 남겨 주세요.")
    remaining = [item for item in sources if item.get("id") != source_id]
    if len(remaining) == len(sources):
        raise HTTPException(status_code=404, detail="주소를 찾지 못했습니다.")
    config["sources"] = remaining
    if config.get("activeSourceId") == source_id:
        config["activeSourceId"] = remaining[0]["id"]
    sync_active_source(config)
    save_config(config)
    return {"ok": True, "status": _status_payload()}


@app.get("/api/mongo/databases")
def mongo_databases(sourceId: str = ""):
    config = load_config()
    try:
        databases = list_databases(config, _selected_source(config, sourceId))
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    return {"databases": databases}


@app.get("/api/mongo/collections")
def mongo_collections(database: str, sourceId: str = ""):
    config = load_config()
    try:
        collections = list_collections(config, database, _selected_source(config, sourceId))
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    return {"collections": collections}


@app.get("/api/mongo/fields")
def mongo_fields(database: str, collection: str, sourceId: str = ""):
    config = load_config()
    try:
        inspected = inspect_fields(config, database, collection, source=_selected_source(config, sourceId))
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    return inspected


@app.post("/api/setup/watch")
def setup_watch(payload: WatchIn):
    config = load_config()
    try:
        source = _selected_source(config, payload.sourceId)
        database = payload.database.strip()
        collection = payload.collection.strip()
        timestamp_field = validate_field_name(payload.timestampField)
        columns = []
        for name in payload.columns:
            cleaned = validate_field_name(name)
            if cleaned != timestamp_field and cleaned not in columns:
                columns.append(cleaned)
        if not database or not collection:
            raise MongoServiceError("데이터베이스와 컬렉션을 선택해 주세요.")
        if not columns:
            raise MongoServiceError("확인할 컬럼을 하나 이상 선택해 주세요.")
        if len(columns) > 200:
            raise MongoServiceError("한 번에 확인할 수 있는 컬럼은 200개까지입니다.")
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    source["database"] = database
    source["collection"] = collection
    source["timestampField"] = timestamp_field
    source["columns"] = columns
    config["activeSourceId"] = source["id"]
    sync_active_source(config)
    save_config(config)
    return {"ok": True, "sourceId": source["id"], "status": _status_payload()}


def _apply_delivery(config: dict, payload: DeliveryIn) -> dict:
    if payload.period not in {"daily", "weekly"}:
        raise MongoServiceError("주기는 매일 또는 매주로 선택해 주세요.")
    if not 0 <= payload.hour <= 23 or not 0 <= payload.minute <= 59:
        raise MongoServiceError("발송 시각을 확인해 주세요.")
    if payload.weekday not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
        raise MongoServiceError("발송 요일을 확인해 주세요.")
    email = config["email"]
    email["enabled"] = payload.enabled
    if payload.enabled:
        if not 1 <= payload.smtpPort <= 65535:
            raise MongoServiceError("SMTP 포트를 확인해 주세요.")
        email.update(
            {
                "to": normalize_recipients(payload.to),
                "smtpHost": payload.smtpHost.strip(),
                "smtpPort": payload.smtpPort,
                "smtpUser": payload.smtpUser.strip(),
                "smtpPassword": keep_secret(payload.smtpPassword, email.get("smtpPassword") or ""),
                "fromName": " ".join(payload.fromName.split()) or "DYP_Schedular",
                "fromAddress": payload.fromAddress.strip(),
                "useTls": payload.useTls,
            }
        )
        validate_delivery(email)
    config["schedule"].update(
        {
            "period": payload.period,
            "hour": payload.hour,
            "minute": payload.minute,
            "weekday": payload.weekday,
            "timezone": "Asia/Seoul",
        }
    )
    return config


@app.post("/api/setup/delivery")
def setup_delivery(payload: DeliveryIn):
    config = load_config()
    try:
        _apply_delivery(config, payload)
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    config["setupComplete"] = True
    save_config(config)
    reschedule()
    return {"ok": True, "status": _status_payload()}


@app.post("/api/mail/test")
def mail_test(payload: DeliveryIn):
    if not payload.enabled:
        raise HTTPException(status_code=400, detail="메일 전송을 사용하지 않는 설정입니다.")
    config = load_config()
    try:
        _apply_delivery(config, payload)
        send_test(config)
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    return {"ok": True}


@app.get("/api/report")
def report(
    date_value: str | None = Query(default=None, alias="date"),
    span: str | None = None,
    source_id: str | None = Query(default=None, alias="source"),
):
    config = load_config()
    if not config.get("setupComplete"):
        raise HTTPException(status_code=400, detail="설정을 먼저 마무리해 주세요.")
    end_date = _parse_date(date_value) if date_value else default_end_date(config)
    try:
        return build_report(config, end_date=end_date, span=span, source_id=source_id)
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc


@app.post("/api/report/send")
def report_send(
    date_value: str | None = Query(default=None, alias="date"),
    span: str | None = None,
    source_id: str | None = Query(default=None, alias="source"),
):
    config = load_config()
    if not config.get("setupComplete"):
        raise HTTPException(status_code=400, detail="설정을 먼저 마무리해 주세요.")
    if not mail_enabled(config):
        raise HTTPException(status_code=400, detail="메일 전송을 사용하지 않는 설정입니다.")
    end_date = _parse_date(date_value) if date_value else default_end_date(config)
    try:
        reports, skipped, label = collect_reports(config, end_date, span)
        send_digest(config, reports, skipped, label)
    except MongoServiceError as exc:
        raise _fail(exc, config) from exc
    built = next((item for item in reports if item.get("sourceId") == source_id), reports[0] if reports else None)
    write_last_run(ok=True, report=delivery_summary(reports, skipped, label, end_date.isoformat()), error=None, manual=True)
    return {"ok": True, "report": built, "status": _status_payload()}


@app.post("/api/report/run")
def report_run():
    ok = run_report_job(manual=True)
    payload = _status_payload()
    if not ok:
        detail = (payload.get("lastRun") or {}).get("error") or "메일을 보내지 못했습니다."
        raise HTTPException(status_code=400, detail=detail)
    return {"ok": True, "status": payload}


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="날짜 형식을 확인해 주세요.") from exc


@app.get("/")
def index():
    index_file = frontend_dist() / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return HTMLResponse(DEV_HINT)


@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith("api"):
        return JSONResponse(status_code=404, content={"detail": "요청한 기능을 찾지 못했습니다."})
    dist = frontend_dist()
    candidate = dist / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index_file = dist / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return HTMLResponse(DEV_HINT, status_code=404)
