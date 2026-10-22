@echo off
title IRCTC Telegram Agent - Launcher
echo Starting IRCTC Telegram Agent in background...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
pause
