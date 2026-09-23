# 현장 데이터 점검

MongoDB에 쌓이는 현장 데이터를 읽어, 전날(또는 지난 7일) 동안 고른 컬럼이 얼마나 수집됐는지 보여 주고 메일로 보냅니다. 주소를 여러 개 등록할 수 있고, 프로그램을 열면 외부 인터넷과 각 주소가 온라인인지 먼저 보여 줍니다. 내부망처럼 메일을 보낼 수 없으면 설정에서 메일 전송을 끄고 화면에서만 확인할 수 있습니다. 연결 정보, 확인 컬럼, 메일, 발송 시각은 데이터베이스가 아니라 프로그램 옆의 `config.json`에 저장됩니다.

## 개발 화면

프로젝트 폴더에서 아래를 실행하면 React와 FastAPI가 함께 켜집니다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
npm install --prefix frontend
npm start
```

브라우저에서 http://127.0.0.1:5173 을 엽니다. `frontend` 폴더에서 `npm run dev`를 실행해도 같습니다.

## 데스크톱 창

화면을 만든 뒤 pywebview 창으로 실행합니다. 창이 열리면 백엔드도 같이 켜집니다.

```bash
npm run build:ui
.venv/Scripts/python launcher.py
```

## 실행 파일

```bash
bash build.sh
```

Windows에서는 `build.bat`을 실행해도 됩니다. 결과는 `dist/DataScheduler.exe` 입니다. Windows에 WebView2가 필요합니다. Windows 10/11에는 보통 이미 설치되어 있습니다.

`config.json`과 `runtime` 폴더는 실행 파일 옆에 만들어집니다. 실행 파일만 다른 곳으로 옮기면 설정도 그 옆에 새로 생깁니다.

자동 발송은 프로그램을 켜 둔 동안에만 동작합니다. 꺼 두고 아침 8시에만 보내고 싶으면 Windows 작업 스케줄러에 아래처럼 등록합니다.

```text
DataScheduler.exe --send-now
```

이 프로그램은 MongoDB를 읽기만 합니다.
