@echo off
chcp 65001 >nul
set "ROOT=%~dp0..\.."
cd /d "%ROOT%"
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 尚未创建 .venv，请先运行“一键安装环境.bat”。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-ui.txt
echo.
echo 图形界面依赖安装完成。
pause
