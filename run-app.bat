@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo ============================================================
echo   의료기기 규정 비서 - 사내망 공유 실행
echo ------------------------------------------------------------
echo   - 잠시 후 브라우저가 열립니다.
echo   - 같은 네트워크(사무실)의 동료는 아래 "Network URL" 로 접속.
echo   - 방화벽 허용 창이 뜨면 [액세스 허용] 을 누르세요(개인 네트워크).
echo   - 이 검은 창을 닫으면 종료됩니다.
echo ============================================================
echo.

python -m streamlit run app.py --server.address 0.0.0.0

echo.
echo (종료됨) 오류가 있으면 위 메시지를 확인하거나 setup_check 를 실행하세요:
echo     python scripts\setup_check.py
pause
