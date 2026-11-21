@echo off
cd /d %~dp0
echo ============================================
echo   새우PDF 실행
echo ============================================
echo 필요한 라이브러리를 확인합니다 (처음 한 번만 오래 걸립니다)...
python -m pip install -q pymupdf PySide6 Pillow
if errorlevel 1 (
  echo.
  echo [오류] python 이 설치돼 있지 않거나 PATH 에 없습니다.
  echo python.org 에서 Python 을 설치한 뒤 다시 실행하세요.
  pause
  exit /b
)
python main.py
