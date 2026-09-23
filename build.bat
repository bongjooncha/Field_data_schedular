@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  python -m venv .venv
)

set PY=.venv\Scripts\python.exe
"%PY%" -m pip install -r requirements.txt
call npm install --prefix frontend
call npm run build --prefix frontend
"%PY%" -m PyInstaller --noconfirm DataScheduler.spec
echo 실행 파일: dist\DataScheduler.exe
