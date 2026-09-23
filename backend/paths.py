from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """설정과 로그를 두는 위치. 실행 파일 옆, 개발 중에는 저장소 루트."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """패키징된 정적 파일이 풀리는 위치."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", project_root()))
    return project_root()


def config_path() -> Path:
    override = os.environ.get("DATA_SCHEDULER_CONFIG")
    if override:
        return Path(override)
    return project_root() / "config.json"


def runtime_dir() -> Path:
    path = project_root() / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frontend_dist() -> Path:
    return bundle_root() / "frontend" / "dist"
