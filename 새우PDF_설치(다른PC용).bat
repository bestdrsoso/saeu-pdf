@echo off
setlocal enabledelayedexpansion
title 새우PDF 설치

echo ============================================
echo   새우PDF 설치  (다른 PC 용)
echo ============================================
echo.
echo 인터넷에서 최신 버전을 받아 바탕화면에 설치합니다.
echo.

rem ---------- 1. Python 확인 ----------
python --version >nul 2>&1
if errorlevel 1 (
  echo [1/4] Python 이 없습니다. 자동 설치를 시도합니다...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo.
    echo [안내] 자동 설치에 실패했습니다.
    echo   python.org 에서 Python 을 설치한 뒤 이 파일을 다시 실행하세요.
    echo   설치할 때 "Add python.exe to PATH" 를 꼭 체크하세요.
    start https://www.python.org/downloads/
    pause
    exit /b
  )
  echo Python 설치 완료. 이 창을 닫고 파일을 다시 실행해 주세요.
  pause
  exit /b
)
echo [1/4] Python 확인 완료

rem ---------- 2. 최신 코드 내려받기 ----------
echo [2/4] 최신 버전 내려받는 중...
set "ZIP=%TEMP%\saeupdf.zip"
set "TMPDIR=%TEMP%\saeupdf_extract"
if exist "%TMPDIR%" rd /s /q "%TMPDIR%"
powershell -NoProfile -Command "try{Invoke-WebRequest -Uri 'https://github.com/bestdrsoso/saeu-pdf/archive/refs/heads/main.zip' -OutFile '%ZIP%' -UseBasicParsing}catch{exit 1}"
if errorlevel 1 (
  echo [오류] 내려받기에 실패했습니다. 인터넷 연결을 확인하세요.
  pause
  exit /b
)

rem ---------- 3. 바탕화면에 풀기 ----------
echo [3/4] 바탕화면에 설치하는 중...
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TMPDIR%' -Force"
set "DST=%USERPROFILE%\Desktop\새우PDF"
if not exist "%DST%" mkdir "%DST%"
xcopy "%TMPDIR%\saeu-pdf-main\*" "%DST%\" /E /Y /Q >nul
del "%ZIP%" >nul 2>&1
rd /s /q "%TMPDIR%" >nul 2>&1

rem ---------- 4. 필요한 라이브러리 ----------
echo [4/4] 필요한 라이브러리 설치 중... (처음엔 몇 분 걸립니다)
python -m pip install -q --upgrade pip >nul 2>&1
python -m pip install -q pymupdf PySide6 Pillow
if errorlevel 1 (
  echo [오류] 라이브러리 설치에 실패했습니다.
  pause
  exit /b
)

echo.
echo ============================================
echo  설치 완료!
echo.
echo   위치 : %DST%
echo   실행 : 그 폴더의 "실행하기.bat"
echo.
echo  * PDF 를 더블클릭해서 바로 열고 싶으면
echo    그 폴더의 "기본앱등록.bat" 을 한 번 실행하세요.
echo  * 앞으로 새 버전이 나오면 새우PDF 를 켤 때
echo    "업데이트가 있습니다" 창이 자동으로 뜹니다.
echo ============================================
echo.
echo 지금 새우PDF 를 실행하려면 아무 키나 누르세요.
pause >nul
start "" "%DST%\실행하기.bat"
