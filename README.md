# NVR 多通道截图工具

Windows 桌面工具，通过设备 HTTP 接口抓取 NVR / 录像机实时画面。支持海康威视、大华、宇视，可对单台设备按通道范围抓图，也可导入设备表批量执行。

仅用于你有权管理的设备。请妥善保管设备表中的账号密码，不要把含真实口令的 CSV 提交到公开仓库。

## 功能

| 模块 | 说明 |
|------|------|
| **单设备抓图** | 填写 IP、账号和通道范围后开始抓图；可自动识别品牌 |
| **批量设备抓图** | 导入 CSV 设备表，勾选设备后一键执行；按设备分子目录保存 |
| **品牌支持** | 海康（ISAPI）、大华（CGI）、宇视（LAPI）；也可手动指定 |
| **通道发现** | 批量模式通过接口或探测获取可用通道 |
| **重复画面跳过** | 可选跳过画面相同的通道，适合单通道设备被多次映射的情况 |
| **文件命名** | 批量模式可组合设备名、IP、通道名、通道编号、日期、时间 |

## 环境要求

- Windows 10 / 11
- Python 3.10+（建议）
- 能访问目标设备的 HTTP 端口（常见为 80）

## 安装与运行

```bash
git clone https://github.com/SeamusX9/nvr-capture.git
cd nvr-capture

pip install -r requirements.txt

python testHK7.py
```

## 使用说明

### 单设备抓图

1. 选择设备品牌，或使用「自动识别」。
2. 填写 IP、用户名、密码，以及通道起止编号。
3. 选择保存目录后点击「开始抓图」。
4. 默认文件名类似：`192.168.1.64_CH01_20261006_105500.jpg`。

### 批量设备抓图

1. 点击「下载导入模板」，按表头填写设备。
2. 「导入设备表」后勾选要执行的设备。
3. 按需勾选文件命名字段和「自动跳过重复画面」。
4. 点击「一键执行」。每台设备的图片保存在以设备名命名的子文件夹中。

CSV 表头：

```text
设备名称,IP地址,用户名,密码,设备品牌
示例海康站点,192.168.1.64,admin,12345,海康
示例大华站点,192.168.1.65,admin,12345,大华
示例宇视站点,192.168.1.66,admin,12345,宇视
```

「设备品牌」可填：`自动` / `海康` / `大华` / `宇视`（或对应英文）。留空视为自动识别。

## 打包为可执行文件

项目提供 PyInstaller 配置（`HK_capture.spec`）和脚本 `build.bat`：

```bash
build.bat
```

或手动执行：

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean HK_capture.spec
```

打包结果：`dist/NVR多通道截图工具.exe`。

打包时会尝试附带 `app.ico` 与 `nvr_app_icon.png`。缺少 PNG 图标不影响主程序运行。

## 项目结构

```
├── testHK7.py           # 程序入口与全部逻辑
├── HK_capture.spec      # PyInstaller 打包配置
├── build.bat            # Windows 一键打包
├── requirements.txt
├── app.ico              # 窗口 / 可执行文件图标
└── LICENSE
```

## 主要依赖

- [requests](https://pypi.org/project/requests/) — HTTP 请求（Digest / Basic 认证）
- [Pillow](https://pypi.org/project/Pillow/) — 图片校验与重复画面哈希
- tkinter — 界面（随 Python 安装，Windows 官方安装包通常已包含）

完整列表见 `requirements.txt`。

## 使用提示

- 设备需开启 HTTP，且账号具备抓图 / 预览权限。
- 自动识别失败时，请在界面或 CSV 中手动指定品牌。
- 连续多次探测失败会提前结束通道扫描，避免空通道长时间等待。
- 通道之间有短暂间隔，降低设备压力。
- 停止按钮会在当前通道完成后生效。

## License

MIT
