# 拾聊 Shiliao

[![Windows checks](https://github.com/1720d8eaff/shiliao/actions/workflows/windows.yml/badge.svg)](https://github.com/1720d8eaff/shiliao/actions/workflows/windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

**两个 Codex 账号，一起用。** 拾聊是一款 Windows 原生桌面工具，用于启动两个独立登录的 Codex 窗口，并在本机整理、查找和转用两个账号的聊天记录。

它适合同时使用两个 Codex 账号、希望切换账号时继续参考旧对话的人。界面使用 Python / Tkinter，聊天资料存入本机 SQLite；日常使用无需浏览器，也不需要额外的 API Key。

> 「记录互通」通过导入、导出和复制对话背景实现。拾聊不会把记录写入 Codex 或 ChatGPT 官方历史侧栏，不会自动同步两个账号，也不会复制账号 A 的登录凭据到账号 B。双开使用本机独立配置，属于实验功能，可能随 Codex 更新而失效。

## 功能

| 功能 | 使用方式 |
| --- | --- |
| 一键双开 | A 沿用本机默认登录；B 使用独立配置，首次自行登录第二个账号 |
| 导入本机记录 | 扫描 A / B 的 Codex 会话文件，也可自行选择其他 Codex 记录目录 |
| 导入导出文件 | 支持 ChatGPT 的 ZIP / conversations JSON、Codex JSONL，以及拾聊 JSON 备份 |
| 去重与更新 | 相同来源、账号标签和会话 ID 下，重复导入去重，有变化则更新 |
| 查找对话 | 按账号标签、来源或文字搜索；支持查看 ChatGPT 回答分支 |
| 跨账号续聊 | 复制所选对话作为背景，粘贴到另一个账号的新聊天 |
| 导出和备份 | 全部、筛选结果或单段对话可导出为 JSON / Markdown / TXT；JSON 可重新导入 |

当前版本整理用户和助手的可见文字，不导入图片、音频或附件本体，也不保留完整的工具调用执行环境。导出的 Markdown / TXT 用于阅读；需要保留回答分支和再次导入时，请使用 JSON。

## 下载使用

1. 在 [Releases](https://github.com/1720d8eaff/shiliao/releases/latest) 下载 `Shiliao-v1.2.0-Windows-x64.zip`。
2. 解压后打开 `Shiliao-Windows`，双击 `拾聊桌面版.exe`。打包版无需安装 Python。
3. 双开前，先安装并登录官方 Codex Windows 桌面 App。本版通过 Windows 的 `OpenAI.Codex` 应用包查找程序。
4. 点击「一键双开」。账号 A 使用默认配置；在账号 B 窗口自行完成第二个账号的登录。
5. 在拾聊点击「＋ 导入记录」，导入本机 Codex 记录或选择 ZIP / JSON / JSONL 文件，随后搜索、查看或导出。

拾聊是社区工具，与 OpenAI 无隶属关系。两个账号的登录和服务访问仍由官方 App 处理。当前发行包为 Windows x64；未签名，发布页面提供 SHA-256 校验文件。

## 如何让另一个账号接着聊

例如，账号 A 已经讨论过一个项目，接下来准备使用账号 B：

1. 在拾聊导入账号 A 的记录，打开对应对话。
2. 点击「复制续聊内容」。复制内容会说明这些文字是历史背景，等待下一条具体要求。
3. 切换到账号 B，在新聊天中粘贴。
4. 再发送本次要做的具体要求；如涉及代码或文件，让 B 同时访问对应项目文件。

粘贴文字背景不会恢复原聊天的附件、工具状态或工作区权限。很长的对话建议先导出并选择必要片段；续聊质量还受目标模型的上下文长度影响。

## 数据和隐私

拾聊本身不发送网络请求，不把聊天上传到服务器，也不收集遥测。启动的官方 Codex App 会按自身行为连接其服务；把历史内容粘贴到目标账号后，该内容会随你的消息发送。

| 内容 | 默认位置 |
| --- | --- |
| 拾聊资料库 | `%LOCALAPPDATA%\ChatHistoryImporter\history.sqlite` |
| 账号 A 会话 | `%USERPROFILE%\.codex\sessions`、`archived_sessions`、`history.jsonl` |
| 账号 B 独立配置 | `%LOCALAPPDATA%\ChatGPT-DualAccount-Test\B` |
| 账号 B 会话 | 上述目录中的 `codex-home` |
| 导出和备份 | 保存对话框选择的位置；部分内部导出会暂存于资料库旁的 `exports` |

账号 B 的目录名保留旧版命名，便于已有用户继续使用。拾聊不读取或复制 `auth.json`；批量选择记录文件时会跳过该文件及 `server-info.json`。账号 B 的独立目录可能包含官方 App 保存的登录凭据，请勿公开。

资料库和导出记录是本机明文文件。使用系统账号权限保护它们。提交 Issue、截图或示例前，请删除聊天内容、个人路径和登录信息；本仓库仅包含程序源码、文档和许可说明。

## 从源码运行

支持 Windows，推荐使用官方 Python 3.12，并确保安装了 Tcl/Tk。运行时仅使用 Python 标准库。

```powershell
git clone https://github.com/1720d8eaff/shiliao.git
cd shiliao
python desktop.pyw
```

使用单独的资料目录：

```powershell
python desktop.pyw --data-dir .\work\demo-data
```

`--data-dir` 仅改变拾聊资料库位置，不改变 A / B 的 Codex 配置位置。从源码运行时「卸载拾聊」按钮禁用；删除源码目录即可移除源码，资料库需另外处理。

## 测试与打包

```powershell
python -m unittest discover -s tests -v
python desktop.pyw --self-test --data-dir .\work\self-test
```

测试使用合成聊天数据、临时资料库和模拟启动器，不会登录、启动或修改你的 Codex 账号。GUI 自检创建控件后退出。GitHub Actions 在 Windows 上执行这些检查并构建发行包。

建议在干净的 Python 虚拟环境中打包：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts\build_windows.py
```

打包使用 [PyInstaller 的 onefile / windowed 模式](https://www.pyinstaller.org/en/stable/usage.html)。输出为 `dist\Shiliao-v1.2.0-Windows-x64.zip` 及对应 `.sha256` 校验文件，包含主程序、独立卸载器、使用说明和许可证。生成目录和个人数据由 `.gitignore` 排除。

卸载器会先展示清单，再在确认后清理识别到的拾聊程序及残留；默认保留聊天资料和账号 B 配置。它不卸载官方 Codex / ChatGPT App。需要删除 B 配置时，请先关闭 B 窗口；删除聊天资料前请自行备份。

## 项目结构

```text
desktop.pyw              原生界面与导入、导出操作
server.py                记录解析、SQLite 存储、搜索与导出（沿用旧模块名）
app_launcher.py          Windows Codex 检测与独立配置启动
uninstall.py             卸载清单与确认界面
cleanup.ps1              再次验证路径后执行清理
uninstaller.pyw          独立卸载器入口
scripts/build_windows.py Windows 打包脚本
tests/                   合成记录与启动隔离测试
third_party/             运行时与打包组件许可
```

旧版遗留的 HTTP 服务入口和开发者本机路径元数据已从开源版移除。

## 常见问题

**找不到 Codex App？** 本版查找 Windows 中的 `OpenAI.Codex` 应用包。请检查官方桌面 App 是否安装；CLI、macOS / Linux 或其他分发方式不在本版双开支持范围内。

**导入后为什么官方侧栏没出现记录？** 记录存在拾聊的本机资料库中。用「复制续聊内容」转到目标账号，或导出后自行使用。

**重复导入还是出现两份？** 去重依据包含账号标签。对同一批记录使用不同标签，会作为不同来源保存；重复导入时保持标签一致。

**有些内容没导进来？** 当前只整理可见文字。JSON 单文件上限 128 MB、JSONL 单行上限 32 MB，上传文件及 ZIP 内选中记录总量上限 512 MB。无效 JSONL 行会跳过并显示提示，损坏 JSON 会报错。

**Codex 更新后 B 无法独立启动？** 双开依赖官方 App 的本地配置行为。请提交脱敏后的系统版本、Codex 版本和现象，等待兼容性修复。首次登录两个账号及真实续聊需要由用户完成，自动化检查只覆盖启动参数和配置隔离。

## 贡献与许可证

欢迎提交 [Issue](https://github.com/1720d8eaff/shiliao/issues) 或 Pull Request。开发说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，隐私问题报告方式见 [SECURITY.md](SECURITY.md)。请用合成数据复现问题。

拾聊源码及本项目图标采用 [MIT License](LICENSE)。发行包中的 Python、Tcl/Tk、OpenSSL、SQLite 和 PyInstaller 遵循各自许可，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；OpenAI / Codex 名称及商标归其各自权利人所有。
