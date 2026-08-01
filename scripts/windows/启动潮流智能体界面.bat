@echo off
chcp 65001 >nul
set "ROOT=%~dp0..\.."
cd /d "%ROOT%"
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 尚未创建 .venv，请先运行“一键安装环境.bat”。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run apps\streamlit\web_ui.py
pause
