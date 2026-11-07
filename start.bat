@echo off
cd /d "%~dp0"
set "QAWAFEL_ENV=%~dp0..\.qawafel_runtime"
if not exist "%QAWAFEL_ENV%\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv "%QAWAFEL_ENV%"
  ) else (
    python -m venv "%QAWAFEL_ENV%"
  )
)
if not exist "%QAWAFEL_ENV%\Scripts\python.exe" (
  echo Install Python 3.11 or newer, then run this file again.
  pause
  exit /b 1
)
"%QAWAFEL_ENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
if errorlevel 1 (
  echo Dependency setup failed. See README.md for manual setup.
  pause
  exit /b 1
)
echo Open http://localhost:8501 in your browser.
"%QAWAFEL_ENV%\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
pause
