@echo off
REM 安裝 ComfyUI-Muse-NM 依賴(使用 ComfyUI portable 附帶的 python_embeded)
set PYTHON_EXE=%~dp0..\..\..\python_embeded\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 找不到 python_embeded,改用系統 python
    set PYTHON_EXE=python
)

"%PYTHON_EXE%" -m pip install -r "%~dp0requirements.txt"

echo.
echo 安裝完成!重啟 ComfyUI 後,節點在 utils/NM/Muse 分類下
pause
