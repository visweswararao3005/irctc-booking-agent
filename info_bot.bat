@echo off
title IRCTC Telegram Agent - Status
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0info.ps1"
pause
