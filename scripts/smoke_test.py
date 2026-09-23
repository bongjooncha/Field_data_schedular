"""설정 파일 없이 API가 기동되고, 비밀번호가 응답에 섞이지 않는지 확인합니다."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEMP = Path(tempfile.mkdtemp(prefix="data-scheduler-")) / "config.json"
os.environ["DATA_SCHEDULER_CONFIG"] = str(TEMP)
TEMP.write_text(
    json.dumps(
        {
            "mongodb": {
                "host": "10.0.0.8",
                "username": "field_user",
                "password": "s3cret-value",
            },
            "email": {"smtpPassword": "mail-secret"},
        }
    ),
    encoding="utf-8",
)

from fastapi.testclient import TestClient

from backend.app import app
from backend.mongo_service import build_uri, resolve_window, scrub_secrets


def main() -> None:
    uri = build_uri(
        {
            "host": "10.0.0.5",
            "port": 27017,
            "username": "field_user",
            "password": "s3cret-value",
            "authSource": "admin",
        }
    )
    scrubbed = scrub_secrets(
        uri,
        {"mongodb": {"username": "field_user", "password": "s3cret-value"}, "email": {}},
    )
    assert "s3cret-value" not in scrubbed
    assert "field_user" not in scrubbed

    start, end, label = resolve_window(
        {"schedule": {"period": "daily", "timezone": "Asia/Seoul"}},
        date(2026, 9, 21),
        "daily",
    )
    assert start.day == 21 and end.day == 22
    assert "21" in label

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        status = client.get("/api/status")
        assert status.status_code == 200, status.text
        raw = status.text
        assert "s3cret-value" not in raw
        assert "mail-secret" not in raw
        body = status.json()
        assert body["setupComplete"] is False
        assert body["config"]["mongodb"]["password"] == ""
        assert body["config"]["mongodb"]["passwordSet"] is True
        assert body["config"]["activeSourceId"] == "primary"
        assert body["config"]["sources"][0]["host"] == "10.0.0.8"
        assert body["config"]["sources"][0]["password"] == ""
        assert body["config"]["sources"][0]["passwordSet"] is True
        removed = client.delete("/api/sources/primary")
        assert removed.status_code == 400, removed.text
        failed = client.post(
            "/api/setup/connection",
            json={"host": "", "port": 27017, "username": "", "password": ""},
        )
        assert failed.status_code == 400, failed.text
        assert "주소" in failed.json()["detail"]
        assert "s3cret-value" in TEMP.read_text(encoding="utf-8")
        skipped = client.post(
            "/api/setup/delivery",
            json={"enabled": False, "to": [], "smtpHost": "", "fromAddress": ""},
        )
        assert skipped.status_code == 200, skipped.text
        skipped_body = skipped.json()
        assert skipped_body["status"]["config"]["email"]["enabled"] is False
        assert skipped_body["status"]["setupComplete"] is True
        assert skipped_body["status"]["nextRun"] is None
        blocked = client.post("/api/report/send")
        assert blocked.status_code == 400, blocked.text
        assert "메일" in blocked.json()["detail"]
    print("smoke ok")


if __name__ == "__main__":
    main()
