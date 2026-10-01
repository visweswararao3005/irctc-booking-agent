@echo off
title IRCTC Telegram Agent - Stopper
echo Stopping IRCTC Telegram Agent...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
pause
