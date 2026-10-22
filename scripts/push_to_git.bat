@echo off
title IRCTC Telegram Agent - Git Push
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push.ps1"
pause
