#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  python -m venv .venv
fi

if [[ -x .venv/Scripts/python.exe ]]; then
  PY=".venv/Scripts/python.exe"
elif [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

"$PY" -m pip install -r requirements.txt
npm install --prefix frontend
npm run build --prefix frontend
"$PY" -m PyInstaller --noconfirm DataScheduler.spec
echo "실행 파일: dist/DataScheduler.exe"
