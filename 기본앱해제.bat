@echo off
echo ============================================
echo   새우PDF 기본앱 등록 해제
echo ============================================
reg delete "HKCU\Software\Classes\SaewooPDF.Document" /f >nul 2>&1
reg delete "HKCU\Software\Classes\Applications\새우PDF.exe" /f >nul 2>&1
reg delete "HKCU\Software\Classes\.pdf\OpenWithProgids" /v "SaewooPDF.Document" /f >nul 2>&1
echo [완료] 등록을 해제했습니다.
echo 기본 PDF 앱을 다른 프로그램으로 다시 지정하세요: 설정 - 앱 - 기본 앱 - .pdf
echo.
pause
