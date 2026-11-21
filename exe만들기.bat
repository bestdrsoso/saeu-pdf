@echo off
cd /d %~dp0
title 새우PDF exe 만들기
echo ============================================
echo   새우PDF 단독 실행파일(exe) 만들기
echo ============================================
echo 처음이면 몇 분 걸립니다. 창을 닫지 마세요.
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo [오류] Python 을 찾을 수 없습니다.
  pause
  exit /b
)

echo [1/3] 필요한 도구 확인 중...
python -m pip install -q pyinstaller pymupdf PySide6 Pillow
if errorlevel 1 (
  echo [오류] 도구 설치 실패.
  pause
  exit /b
)

rem 한글 이름/경로에서 PyInstaller 가 실패하는 일이 있어
rem 영문 이름으로, 영문 임시폴더에서 빌드한 뒤 이름만 바꾼다.
set "BUILDDIR=%TEMP%\saeupdf_build"
set "DISTDIR=%TEMP%\saeupdf_dist"
if exist "%DISTDIR%" rd /s /q "%DISTDIR%"

echo [2/3] 빌드 중... (로그: build_log.txt)
python -m PyInstaller --noconfirm --onefile --windowed --name SaeuPDF --distpath "%DISTDIR%" --workpath "%BUILDDIR%" --specpath "%TEMP%" main.py > "%~dp0build_log.txt" 2>&1

if not exist "%DISTDIR%\SaeuPDF.exe" (
  echo.
  echo [실패] exe 가 만들어지지 않았습니다.
  echo   같은 폴더의 build_log.txt 를 열어 마지막 줄을 확인하세요.
  echo   그 내용을 그대로 보내주시면 원인을 찾아드립니다.
  pause
  exit /b
)

echo [3/3] 정리 중...
if exist "%~dp0새우PDF.exe" del /q "%~dp0새우PDF.exe"
move /Y "%DISTDIR%\SaeuPDF.exe" "%~dp0새우PDF.exe" >nul
rd /s /q "%DISTDIR%" >nul 2>&1
rd /s /q "%BUILDDIR%" >nul 2>&1
del /q "%~dp0build_log.txt" >nul 2>&1

echo.
echo ============================================
echo  완료!  이 폴더에 "새우PDF.exe" 가 생겼습니다.
echo.
echo  [참고] exe 는 자동 업데이트가 안 됩니다.
echo   새 버전이 나오면 이 파일을 다시 실행해 주세요.
echo   매번 알림이 뜨는 게 싫으면 새우PDF 에서
echo   [파일] - "켤 때 자동으로 업데이트 확인" 을 꺼두세요.
echo ============================================
pause
