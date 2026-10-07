# 第三方许可说明

拾聊自有源码及图标采用仓库根目录的 MIT License。运行源码仅依赖 Python 标准库和 Tcl/Tk；Windows 发行包额外包含运行时和 PyInstaller 启动器。

| 组件 | 许可 / 说明 | 原文 |
| --- | --- | --- |
| Python 3.12 | PSF License 及其组件许可 | [Python.txt](third_party/Python.txt) |
| Tcl | Tcl/Tk 许可 | [Tcl.txt](third_party/Tcl.txt) |
| Tk | Tcl/Tk 许可 | [Tk.txt](third_party/Tk.txt) |
| OpenSSL 3.x | Apache License 2.0 | [OpenSSL.txt](third_party/OpenSSL.txt) |
| SQLite | 公有领域 | [官方声明](https://www.sqlite.org/copyright.html) |
| PyInstaller | GPL 2.0 及生成程序分发例外 | [PyInstaller.txt](third_party/PyInstaller.txt) |

许可原文随发行包保留。打包所用 Python 的补丁版本和组件版本取决于构建环境；发布时应在干净环境中检查依赖和许可是否一致。源码许可不改变任何第三方组件的许可。

参考：[PyInstaller 许可例外](https://pyinstaller.org/en/stable/license.html)、[Python 许可](https://docs.python.org/3/license.html)。
