@echo off
chcp 65001 >nul
set "ROOT=%~dp0..\.."
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo 请先运行“一键安装环境.bat”
  pause
  exit /b 1
)
set PYTHONUTF8=1
"%ROOT%\.venv\Scripts\python.exe" "%ROOT%\examples\demo_vscode.py"
pause
