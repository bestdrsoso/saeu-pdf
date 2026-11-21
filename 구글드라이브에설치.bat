@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

echo ============================================
echo   새우PDF - 구글 드라이브에 설치
echo   (여러 PC 에서 자동으로 최신 버전 쓰기)
echo ============================================
echo.

set "DRIVE=G:\내 드라이브"
if not exist "%DRIVE%" (
  echo [오류] 구글 드라이브를 찾지 못했습니다. ^(%DRIVE%^)
  echo   - 구글 드라이브 데스크톱이 켜져 있는지 확인하세요.
  echo   - 드라이브 문자가 G: 가 아니면 이 파일을 메모장으로 열어
  echo     윗부분 DRIVE 경로를 고쳐주세요.
  pause
  exit /b
)

set "DST=%DRIVE%\새우PDF"
if not exist "%DST%" mkdir "%DST%"

echo 파일을 구글 드라이브로 복사합니다...
copy /Y "%~dp0*.py"   "%DST%\" >nul
copy /Y "%~dp0*.bat"  "%DST%\" >nul
copy /Y "%~dp0*.txt"  "%DST%\" >nul
copy /Y "%~dp0*.json" "%DST%\" >nul

rem 바탕화면에 실행용 파일 만들기
set "RUN=%USERPROFILE%\Desktop\새우PDF 실행.bat"
> "%RUN%" echo @echo off
>> "%RUN%" echo cd /d "%DST%"
>> "%RUN%" echo start "" pythonw main.py

echo.
echo ============================================
echo  완료!
echo.
echo   앱 위치 : %DST%
echo   실행    : 바탕화면의 "새우PDF 실행.bat"
echo.
echo  [다른 PC 에서 쓰는 법]
echo   1. 그 PC 에도 구글 드라이브(같은 계정)를 켜 둡니다.
echo   2. 폴더가 동기화되면
echo      "%DST%" 안의 "구글드라이브에설치.bat" 을 한 번 실행하세요.
echo      (그 PC 바탕화면에도 실행 파일이 생깁니다)
echo.
echo  앞으로 제가 파일을 고치면 드라이브가 동기화해서
echo  모든 PC 가 다음 실행 때 자동으로 최신이 됩니다.
echo ============================================
pause
