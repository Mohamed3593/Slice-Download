@echo off
title yt-dlp GUI Loader
echo Starting yt-dlp GUI...
echo Please wait while the server starts...

:: Check if Node is available
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Node.js is not installed or not in PATH.
    echo Please install Node.js to use this tool.
    pause
    exit
)

:: Start the server in a new window/process
start /B node simple_gui.js

:: Wait a moment for server to spin up
timeout /t 2 /nobreak >nul

:: Open browser
echo Opening interface...
start http://localhost:3000

echo.
echo App is running! Close this window to stop the server.
pause
