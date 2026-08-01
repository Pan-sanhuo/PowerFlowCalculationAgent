@echo off
chcp 65001 >nul
set "ROOT=%~dp0..\.."
powershell -ExecutionPolicy Bypass -File "%ROOT%\scripts\setup.ps1"
pause
