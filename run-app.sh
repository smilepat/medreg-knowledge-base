#!/usr/bin/env bash
# 사내망 공유 실행 (macOS/Linux/Git Bash). Windows는 run-app.bat 더블클릭.
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
echo "같은 네트워크 동료는 아래 Network URL 로 접속 (이 창을 닫으면 종료)"
python -m streamlit run app.py --server.address 0.0.0.0
