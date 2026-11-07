@echo off
REM Double-click this file (Windows) to set up and start the portfolio locally.
cd /d "%~dp0"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example - open it and change ADMIN_SETUP_KEY before first use.
)
if not exist "venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv venv || (echo Python not found. Install Python from python.org and tick "Add Python to PATH". & pause & exit /b 1)
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo Install failed. & pause & exit /b 1)
echo.
echo Starting the website at http://127.0.0.1:5000  (press Ctrl+C to stop)
echo Admin panel: http://127.0.0.1:5000/admin/login
python app.py
pause
