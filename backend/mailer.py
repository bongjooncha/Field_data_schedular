from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from .mongo_service import MongoServiceError, scrub_secrets

STATUS_LABEL = {
    "ok": "정상",
    "partial": "확인 필요",
    "empty": "미수집",
}


def normalize_recipients(value) -> list[str]:
    if isinstance(value, str):
        raw = value.replace(";", ",").replace("\n", ",")
        parts = [item.strip() for item in raw.split(",")]
    elif isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(normalize_recipients(str(item)))
    else:
        parts = []
    unique: list[str] = []
    for item in parts:
        if item and item not in unique:
            unique.append(item)
    return unique


def _valid_email(value: str) -> bool:
    if value.count("@") != 1:
        return False
    local, domain = value.split("@")
    return bool(local and domain and "." in domain and " " not in value)


def validate_delivery(email: dict) -> list[str]:
    recipients = normalize_recipients(email.get("to") or [])
    invalid = [item for item in recipients if not _valid_email(item)]
    if not recipients:
        raise MongoServiceError("받을 메일 주소를 입력해 주세요.")
    if invalid:
        raise MongoServiceError("메일 주소 형식을 확인해 주세요.")
    if not str(email.get("smtpHost") or "").strip():
        raise MongoServiceError("SMTP 서버 주소를 입력해 주세요.")
    if not str(email.get("fromAddress") or "").strip():
        raise MongoServiceError("보내는 메일 주소를 입력해 주세요.")
    if not _valid_email(str(email.get("fromAddress"))):
        raise MongoServiceError("보내는 메일 주소 형식을 확인해 주세요.")
    return recipients


def _column_lines(report: dict) -> list[str]:
    lines = []
    for row in report["columns"]:
        rate = f"{row['fillRate'] * 100:.1f}%"
        lines.append(
            f"- {row['name']}: {row['present']:,}건 수집 / {row['missing']:,}건 누락 ({rate}, {STATUS_LABEL[row['status']]})"
        )
    return lines


def render_text(report: dict) -> str:
    lines = [
        f"현장 데이터 점검 결과 ({STATUS_LABEL[report['status']]})",
        f"기간: {report['window']['label']}",
        f"대상: {report['database']}.{report['collection']}",
        f"시간 컬럼: {report['timestampField']}",
        f"수집 문서: {report['totalDocuments']:,}건",
        "",
        "컬럼별 수집",
        *_column_lines(report),
    ]
    if not report.get("timestampIndexed"):
        lines.extend(["", "시간 컬럼에 인덱스가 없어 조회가 느릴 수 있습니다."])
    return "\n".join(lines)


def render_html(report: dict) -> str:
    rows = []
    for row in report["columns"]:
        rate = f"{row['fillRate'] * 100:.1f}%"
        rows.append(
            "<tr>"
            f"<td>{escape(row['name'])}</td>"
            f"<td style='text-align:right'>{row['present']:,}</td>"
            f"<td style='text-align:right'>{row['missing']:,}</td>"
            f"<td style='text-align:right'>{rate}</td>"
            f"<td>{STATUS_LABEL[row['status']]}</td>"
            "</tr>"
        )
    index_note = ""
    if not report.get("timestampIndexed"):
        index_note = "<p>시간 컬럼에 인덱스가 없어 조회가 느릴 수 있습니다.</p>"
    return f"""
    <div style="font-family:Segoe UI,sans-serif;color:#191918">
      <p style="margin:0 0 8px;font-size:18px;font-weight:700">현장 데이터 점검</p>
      <p style="margin:0 0 16px">기간 {escape(report['window']['label'])} · {STATUS_LABEL[report['status']]}</p>
      <p style="margin:0 0 16px">
        {escape(report['database'])}.{escape(report['collection'])}<br>
        시간 컬럼 {escape(report['timestampField'])}<br>
        수집 문서 {report['totalDocuments']:,}건
      </p>
      <table cellpadding="8" cellspacing="0" style="border-collapse:collapse;min-width:420px">
        <thead>
          <tr style="background:#f6f5f4;text-align:left">
            <th>컬럼</th><th>수집</th><th>누락</th><th>채움률</th><th>상태</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      {index_note}
    </div>
    """


def _smtp_client(email: dict):
    host = str(email.get("smtpHost") or "").strip()
    port = int(email.get("smtpPort") or 587)
    if port == 465:
        client = smtplib.SMTP_SSL(host, port, timeout=20)
    else:
        client = smtplib.SMTP(host, port, timeout=20)
        if email.get("useTls", True):
            client.starttls()
    username = str(email.get("smtpUser") or "")
    password = str(email.get("smtpPassword") or "")
    if username:
        client.login(username, password)
    return client


def format_sender(email: dict) -> str:
    address = str(email.get("fromAddress") or "").strip()
    name = " ".join(str(email.get("fromName") or "").split()) or "DYP_Schedular"
    return formataddr((name, address))


def send_message(config: dict, subject: str, text: str, html: str | None = None) -> None:
    email = config["email"]
    recipients = validate_delivery(email)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = format_sender(email)
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    try:
        with _smtp_client(email) as client:
            client.send_message(message)
    except Exception as exc:
        raise MongoServiceError(f"메일을 보내지 못했습니다. {scrub_secrets(str(exc), config)}") from exc


def send_report(config: dict, report: dict) -> None:
    status = STATUS_LABEL[report["status"]]
    subject = f"[현장 데이터 점검] {report['window']['label']} — {status}"
    send_message(config, subject, render_text(report), render_html(report))


def send_test(config: dict) -> None:
    send_message(
        config,
        "[현장 데이터 점검] 메일 설정 확인",
        "현장 데이터 점검 프로그램의 메일 설정이 연결되어 있습니다.\n이 메일이 보이면 발송 설정이 올바릅니다.",
    )
