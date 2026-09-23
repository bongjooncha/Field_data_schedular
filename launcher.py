"""데스크톱 창을 열고, 같은 프로세스에서 FastAPI를 띄웁니다."""

from __future__ import annotations

import multiprocessing
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(ROOT))


def _prepare_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def _configure_logging() -> None:
    import logging

    from backend.paths import runtime_dir

    logging.basicConfig(
        filename=runtime_dir() / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def _message_box(message: str) -> None:
    if sys.platform != "win32":
        if sys.stderr:
            print(message, file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "현장 데이터 점검", 0x10)
    except Exception:
        if sys.stderr:
            print(message, file=sys.stderr)


def _pick_port(start: int = 8765) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("사용할 수 있는 포트를 찾지 못했습니다.")


def _wait_until_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("서버를 시작하지 못했습니다. runtime/app.log 를 확인해 주세요.")


def _send_now() -> int:
    _configure_logging()
    from backend.scheduler import run_report_job

    return 0 if run_report_job(manual=False) else 1


def _open_window() -> None:
    import uvicorn
    import webview

    from backend.app import app as fastapi_app

    _configure_logging()
    port = _pick_port()
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="api", daemon=True)
    thread.start()
    _wait_until_ready(port)
    webview.create_window(
        "현장 데이터 점검",
        f"http://127.0.0.1:{port}",
        width=1180,
        height=820,
        min_size=(980, 680),
        background_color="#f6f5f4",
        text_select=True,
    )
    webview.start()
    server.should_exit = True


def main() -> int:
    _prepare_stdio()
    try:
        if "--send-now" in sys.argv:
            return _send_now()
        _open_window()
        return 0
    except Exception as exc:
        detail = "".join(traceback.format_exception(exc))
        try:
            from backend.paths import runtime_dir

            (runtime_dir() / "error.log").write_text(detail, encoding="utf-8")
        except Exception:
            pass
        _message_box(f"{exc}\n\n자세한 내용은 runtime/error.log 에 있습니다.")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
