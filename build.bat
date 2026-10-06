@echo off
chcp 65001 >nul
setlocal

echo 正在安装/更新打包依赖...
python -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 (
    echo 依赖安装失败
    exit /b 1
)

echo.
echo 开始打包...
python -m PyInstaller --noconfirm --clean HK_capture.spec
if errorlevel 1 (
    echo 打包失败
    exit /b 1
)

echo.
echo 打包完成: dist\NVR多通道截图工具.exe
endlocal
