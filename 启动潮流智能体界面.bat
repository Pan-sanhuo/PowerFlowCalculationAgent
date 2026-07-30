@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 尚未创建 .venv，请先运行“一键安装环境.bat”。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m streamlit run web_ui.py
pause
