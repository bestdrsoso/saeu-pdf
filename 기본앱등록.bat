@echo off
setlocal
cd /d %~dp0

echo ============================================
echo   새우PDF 를 기본 PDF 프로그램으로 등록
echo ============================================
echo.

rem --- 1순위: exe 가 있으면 exe 로 등록 ---
set "TARGET="
set "ICON="
if exist "%~dp0새우PDF.exe" (
  set "TARGET=\"%~dp0새우PDF.exe\" \"%%1\""
  set "ICON=%~dp0새우PDF.exe,0"
)
if not defined TARGET if exist "%~dp0dist\새우PDF.exe" (
  set "TARGET=\"%~dp0dist\새우PDF.exe\" \"%%1\""
  set "ICON=%~dp0dist\새우PDF.exe,0"
)

rem --- exe 가 없으면 Python 으로 등록 (업데이트해도 항상 최신 코드로 열림) ---
if not defined TARGET (
  for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
  if not defined PYW (
    echo [오류] Python 도 exe 도 찾지 못했습니다.
    echo   Python 을 설치하거나 "exe만들기.bat" 을 먼저 실행하세요.
    pause
    exit /b
  )
  set "TARGET=\"!PYW!\" \"%~dp0main.py\" \"%%1\""
  set "ICON=!PYW!,0"
  echo [방식] Python 으로 등록합니다.
  echo        - 코드를 고쳐도 다시 등록할 필요가 없습니다.
  echo        - exe 를 다시 만들 필요도 없습니다.
) else (
  echo [방식] exe 로 등록합니다.
  echo        - exe 를 새로 만들 때마다 같은 자리에 덮어쓰면 재등록은 필요 없습니다.
)
echo.

setlocal enabledelayedexpansion
reg add "HKCU\Software\Classes\SaewooPDF.Document" /ve /d "새우PDF 문서" /f >nul
reg add "HKCU\Software\Classes\SaewooPDF.Document\DefaultIcon" /ve /d "!ICON!" /f >nul
reg add "HKCU\Software\Classes\SaewooPDF.Document\shell\open\command" /ve /d "!TARGET!" /f >nul
reg add "HKCU\Software\Classes\Applications\새우PDF.exe\shell\open\command" /ve /d "!TARGET!" /f >nul
reg add "HKCU\Software\Classes\Applications\새우PDF.exe" /v FriendlyAppName /t REG_SZ /d "새우PDF" /f >nul
reg add "HKCU\Software\Classes\.pdf\OpenWithProgids" /v "SaewooPDF.Document" /t REG_SZ /d "" /f >nul
endlocal

echo [완료] 연결 프로그램에 "새우PDF" 가 등록됐습니다.
echo.
echo ----------------------------------------------------------
echo  마지막 한 단계 (한 번만 하면 끝)
echo    아무 PDF 우클릭 - 연결 프로그램 - 다른 앱 선택
echo    - "새우PDF" 고르고 [항상] 체크
echo    또는  설정 - 앱 - 기본 앱 - .pdf - 새우PDF
echo ----------------------------------------------------------
echo.
echo 기본 앱 설정 화면을 열려면 아무 키나 누르세요.
pause >nul
start ms-settings:defaultapps
