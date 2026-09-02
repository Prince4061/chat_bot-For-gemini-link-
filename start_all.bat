@echo off
title AI Digital Vending Deep Agent
echo ============================================================
echo  AI Digital Vending Deep Agent
echo ============================================================
echo.

if not exist ".env" (
  echo [!] .env not found. Copying .env.example -> .env
  copy .env.example .env >nul
  echo     Edit .env and set ADMIN_API_KEY + OPENAI_API_KEY, then run again.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo [1/2] Building React frontend...
  pushd frontend
  call npm install
  call npm run build
  popd
)

echo [2/2] Starting server (APP_ENV from .env; production uses waitress)...
start "Vending Deep Agent Server" cmd /k "python app.py"
timeout /t 3 >nul
start http://127.0.0.1:5000
echo Running at http://127.0.0.1:5000
