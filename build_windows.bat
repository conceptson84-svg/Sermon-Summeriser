@echo off
REM Build the Windows app. Run this ON A WINDOWS machine.
REM Output: dist\SermonSummarizer\SermonSummarizer.exe
cd /d "%~dp0"

echo ==^> Setting up build environment
py -3 -m venv .venv-build
call .venv-build\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

echo ==^> Generating app icon (if assets\icon.png exists)
python make_icon.py

echo ==^> Building with PyInstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller sermon-summarizer.spec

echo.
echo ==^> Done. App folder:
echo     dist\SermonSummarizer\
echo.
echo To distribute: zip the dist\SermonSummarizer folder and share it.
echo Users unzip and run SermonSummarizer.exe (SmartScreen: More info -^> Run anyway).
pause
