@echo off
cd /d %~dp0
echo ============================================
echo   새우PDF 단독 실행파일(exe) 만들기
echo ============================================
echo 처음이면 시간이 꽤 걸립니다. 기다려 주세요...
echo.

python -m pip install -q pyinstaller pymupdf PySide6 Pillow
if errorlevel 1 (
  echo [오류] Python 이 설치돼 있지 않거나 PATH 에 없습니다.
  pause
  exit /b
)

rem pyinstaller 명령이 PATH 에 없어도 되도록 python -m 으로 실행
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name 새우PDF ^
  --distpath "%~dp0." ^
  --workpath "%TEMP%\saeupdf_build" ^
  --specpath "%TEMP%" ^
  main.py

if errorlevel 1 (
  echo.
  echo [실패] exe 만들기에 실패했습니다. 위 메시지를 확인하세요.
  pause
  exit /b
)

echo.
echo ============================================
echo  완료!  이 폴더에 "새우PDF.exe" 가 생겼습니다.
echo  (dist 폴더 안이 아니라 바로 여기입니다)
echo.
echo  이제 "기본앱등록.bat" 을 실행하면
echo  PDF 를 더블클릭했을 때 새우PDF 로 열립니다.
echo ============================================
pause
