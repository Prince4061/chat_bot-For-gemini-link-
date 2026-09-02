@echo off
title AI Digital Vending Deep Agent
echo ============================================================
echo  Starting AI Digital Vending Deep Agent & React Frontend...
echo ============================================================
echo.
echo 1. Starting Flask Server on port 5000...
start cmd /k "python app.py"

echo 2. Opening React Application in Browser...
timeout /t 2 >nul
start http://127.0.0.1:5000

echo Application is running at http://127.0.0.1:5000
