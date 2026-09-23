from __future__ import annotations

import json
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config_store import load_config
from .mailer import send_report
from .mongo_service import MongoServiceError, build_report, default_end_date, scrub_secrets
from .paths import runtime_dir

logger = logging.getLogger("data_scheduler")
_scheduler: BackgroundScheduler | None = None
WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def last_run_path():
    return runtime_dir() / "last_run.json"


def read_last_run() -> dict | None:
    path = last_run_path()
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_last_run(*, ok: bool, report: dict | None, error: str | None, manual: bool) -> None:
    payload = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": ok,
        "manual": manual,
        "error": error,
        "windowLabel": None if report is None else report["window"]["label"],
        "coveredEnd": None if report is None else report["window"].get("coveredEnd"),
        "status": None if report is None else report["status"],
        "totalDocuments": None if report is None else report["totalDocuments"],
    }
    path = last_run_path()
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def run_report_job(manual: bool = False) -> bool:
    config = load_config()
    if not config.get("setupComplete"):
        write_last_run(ok=False, report=None, error="설정이 끝나지 않았습니다.", manual=manual)
        return False
    try:
        report = build_report(config, end_date=default_end_date(config))
        send_report(config, report)
        write_last_run(ok=True, report=report, error=None, manual=manual)
        logger.info("리포트를 발송했습니다. %s", report["window"]["label"])
        return True
    except Exception as exc:
        message = scrub_secrets(str(exc), config)
        if not isinstance(exc, MongoServiceError):
            logger.exception("리포트 발송에 실패했습니다.")
        else:
            logger.error("리포트 발송에 실패했습니다. %s", message)
        write_last_run(ok=False, report=None, error=message, manual=manual)
        return False


def next_run_at() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("field-report")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()


def reschedule() -> None:
    if _scheduler is None:
        return
    existing = _scheduler.get_job("field-report")
    if existing:
        _scheduler.remove_job("field-report")
    config = load_config()
    if not config.get("setupComplete"):
        return
    schedule = config["schedule"]
    timezone_name = schedule.get("timezone") or "Asia/Seoul"
    hour = int(schedule.get("hour", 8))
    minute = int(schedule.get("minute", 0))
    trigger_kwargs = {"hour": hour, "minute": minute, "timezone": timezone_name}
    if schedule.get("period") == "weekly":
        weekday = schedule.get("weekday") or "mon"
        if weekday not in WEEKDAYS:
            weekday = "mon"
        trigger_kwargs["day_of_week"] = weekday
    _scheduler.add_job(
        run_report_job,
        CronTrigger(**trigger_kwargs),
        id="field-report",
        replace_existing=True,
        kwargs={"manual": False},
    )
    logger.info("발송 예약을 갱신했습니다. 다음 실행 %s", next_run_at())


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    reschedule()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
