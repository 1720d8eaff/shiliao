# 参与开发

在 Windows 上使用 Python 3.12 和 Tcl/Tk。运行时不需要第三方 Python 依赖；打包依赖在 `requirements-build.txt` 中。

1. Fork 并创建分支，描述要解决的问题。
2. 用合成记录复现，不提交真实聊天、数据库、账号配置、Token 或本机路径。
3. 修改后运行 `python -m unittest discover -s tests -v`。
4. 涉及界面时运行 `python desktop.pyw --self-test --data-dir .\work\self-test`，并实际检查受影响操作。
5. 涉及打包时运行 `python scripts\build_windows.py`，验证新程序使用临时资料目录可以启动。

记录解析应保留可见文字与回答分支，并继续跳过隐藏消息、分析通道和工具调用。导入失败时不得破坏已有资料。双开改动不得复制登录凭据，测试应模拟启动而非操作真实账号。

报告兼容性问题时提供 Windows / Python / Codex 版本、复现步骤和脱敏错误；不要贴 `auth.json`、SQLite 文件或整个 Codex 数据目录。
