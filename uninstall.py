"""Reviewable cleanup of this product only. Never remove the official app."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import re
import tkinter as tk
from tkinter import ttk, messagebox
import uuid
import winreg

PROGRAM_DIRS = ('拾聊原生桌面版', '拾聊-Windows', 'ChatHistory-Importer',
                'ChatGPT-DualAccount-Test', '拾聊-双账号工作台-Windows', '拾聊桌面版', 'Shiliao-Windows')
PROGRAM_FILES = ('拾聊桌面版.exe', '拾聊.exe', '卸载拾聊.exe', '拾聊卸载工具.exe')
PACKAGE_FILES = ('拾聊-双账号工作台-Windows.zip', '拾聊-源码与接口.zip',
                 '拾聊原生桌面版-Windows.zip', '拾聊原生桌面版-源码.zip',
                 'ChatGPT-DualAccount-Test.zip', '拾聊导出预览.jpg', '拾聊界面预览.jpg',
                 '拾聊原生桌面版-验证说明.md')
CACHE_DIRS = ('app-review', 'history-build', 'history-build-v011', 'history-build-v012',
              'history-import-tests', 'native-build', 'native-frozen-self-test',
              'native-self-test', 'native-uninstall-test')
CACHE_FILES = ('native-live-pid.txt', 'package_native.py', 'previous-desktop-shiliao.exe')
STATE_FILES = ('instance.lock', 'server-info.json', 'last-instance-probe.json',
               'last-start-error.json', 'last-native-error.txt', 'native-self-test.json')
SHORTCUTS = ('拾聊.lnk', '拾聊桌面版.lnk', '拾聊双账号工作台.lnk',
             '拾聊 - 快捷方式.lnk', '拾聊桌面版 - 快捷方式.lnk', '卸载拾聊.lnk')
PRODUCT_NAMES = ('拾聊', '拾聊桌面版', '拾聊双账号工作台', '拾聊 · 双账号工作台', 'ChatHistoryImporter')
ICON_HASH = '868ced1b0570f491ddfbcf956df5a0ea70d4db9378920eb2f054faf0556d2bc8'


def known_roots():
    desktop = Path(os.environ['USERPROFILE']) / 'Desktop'
    roots = [desktop]
    # A consumer may extract to another location; only clean this explicitly known package.
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    if exe_dir.name in PROGRAM_DIRS and exe_dir.parent not in roots:
        roots.append(exe_dir.parent)
    return list(dict.fromkeys(roots))


def without_links(path):
    for item in [path, *path.parents]:
        if item.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(item)):
            return False
    return True


def scan_files(packages=True, caches=True, data=False, profile=False):
    found = []
    def add(path, kind):
        path = Path(path).absolute()
        if path.exists() and without_links(path):
            found.append({'path': str(path), 'kind': kind})
    for root in known_roots():
        if root.name == 'work':
            if caches:
                for name in CACHE_DIRS + CACHE_FILES:
                    add(root / name, '开发缓存')
            continue
        for name in PROGRAM_FILES:
            add(root / name, '程序')
        for name in PROGRAM_DIRS:
            folder = root / name
            # Match the product files as well as the name before removing a directory.
            if folder.is_dir() and any((folder / marker).exists() for marker in
                    (*PROGRAM_FILES, 'server.py', 'Open-Both.cmd', '源码/desktop.pyw', '拾聊-Windows/拾聊.exe')):
                add(folder, '程序目录')
        if packages:
            for name in PACKAGE_FILES:
                add(root / name, '旧版安装包及项目附件')
    local = Path(os.environ['LOCALAPPDATA'])
    if data:
        add(local / 'ChatHistoryImporter', '聊天资料（含备份与导出）')
    else:
        for name in STATE_FILES:
            add(local / 'ChatHistoryImporter' / name, '旧版启动残留')
    if profile:
        add(local / 'ChatGPT-DualAccount-Test', '账号 B 独立登录与本地会话')
    if caches:
        for folder in Path(tempfile.gettempdir()).glob('_MEI*'):
            if not re.fullmatch(r'_MEI[a-zA-Z0-9]+', folder.name) or not without_links(folder):
                continue
            try:
                if hashlib.sha256((folder / 'app.ico').read_bytes()).hexdigest() == ICON_HASH:
                    add(folder, '拾聊运行时临时文件')
            except OSError:
                pass
    programs = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs'
    for root in [Path(os.environ['USERPROFILE']) / 'Desktop', programs, programs / 'Startup']:
        for name in SHORTCUTS:
            add(root / name, '快捷方式或启动项')
        folder = root / '拾聊'
        if folder.is_dir() and any((folder / name).exists() for name in SHORTCUTS):
            add(folder, '开始菜单快捷方式')
    # Avoid duplicate deletion of paths inside an already selected directory.
    unique = []
    for entry in sorted(found, key=lambda item: len(Path(item['path']).parts)):
        path = Path(entry['path'])
        if not any(path == Path(existing['path']) or Path(existing['path']) in path.parents for existing in unique):
            unique.append(entry)
    return unique


def scan_registry():
    found = []
    parent = r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, parent) as key:
            for index in range(winreg.QueryInfoKey(key)[0]):
                name = winreg.EnumKey(key, index)
                with winreg.OpenKey(key, name) as entry:
                    try:
                        display = winreg.QueryValueEx(entry, 'DisplayName')[0]
                    except OSError:
                        continue
                    if display in PRODUCT_NAMES:
                        found.append({'key': parent + '\\' + name, 'display': display})
    except OSError:
        pass
    run_key = r'Software\Microsoft\Windows\CurrentVersion\Run'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, value, _ = winreg.EnumValue(key, index)
                if name in PRODUCT_NAMES and isinstance(value, str) and any(filename in value for filename in PROGRAM_FILES):
                    found.append({'key': run_key, 'name': name, 'value': value, 'display': name})
    except OSError:
        pass
    return found


def profile_in_use():
    script = "$p=Join-Path $env:LOCALAPPDATA 'ChatGPT-DualAccount-Test\\B'; @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($p,[StringComparison]::OrdinalIgnoreCase) -ge 0 }).Count"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], capture_output=True,
                            timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    # If process detection fails, do not delete a possibly active profile.
    return result.returncode != 0 or result.stdout.strip() != b'0'


def launch_cleanup(entries, registry, preserve_data, preserve_profile):
    identifier = uuid.uuid4().hex
    temp = Path(tempfile.gettempdir())
    plan_path = temp / ('Shiliao-uninstall-' + identifier + '.json')
    helper_path = temp / ('Shiliao-uninstall-' + identifier + '.ps1')
    report_path = temp / ('Shiliao-uninstall-' + identifier + '-report.txt')
    plan = {'files': entries, 'registry': registry, 'parentPid': os.getpid(),
            'preserveData': preserve_data, 'preserveProfile': preserve_profile,
            'report': str(report_path), 'packageRoots': [str(root) for root in known_roots()]}
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    helper_path.write_bytes((Path(__file__).parent / 'cleanup.ps1').read_bytes())
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                          '-File', str(helper_path), '-PlanPath', str(plan_path)],
                         creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    except OSError:
        plan_path.unlink(missing_ok=True)
        helper_path.unlink(missing_ok=True)
        raise


def open_uninstaller(owner=None):
    window = tk.Toplevel(owner) if owner else tk.Tk()
    window.title('卸载拾聊 · 清理新旧版本')
    window.geometry('760x630')
    window.minsize(650, 560)
    if owner:
        window.transient(owner)
        window.grab_set()
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='卸载拾聊及以前版本', font=('Microsoft YaHei UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='先查看清理清单。继续后将关闭拾聊，删除选定文件。', wraplength=690).pack(anchor='w', pady=(8, 14))
    clear_data = tk.BooleanVar(value=False)
    clear_profile = tk.BooleanVar(value=False)
    clear_packages = tk.BooleanVar(value=True)
    clear_caches = tk.BooleanVar(value=True)
    selected, registry = [], []
    choices = [
        ('清理已知的拾聊旧版安装包与附件', clear_packages),
        ('清理拾聊运行时临时文件', clear_caches),
        ('同时删除聊天资料、备份和导出文件（不可恢复）', clear_data),
        ('同时删除账号 B 登录和本地会话（需先关闭 B 窗口）', clear_profile),
    ]
    for text, variable in choices:
        ttk.Checkbutton(frame, text=text, variable=variable).pack(anchor='w', pady=4)
    ttk.Label(frame, text='清理清单', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(12, 5))
    area = ttk.Frame(frame)
    area.pack(fill='both', expand=True)
    listing = tk.Text(area, wrap='word', height=12, font=('Microsoft YaHei UI', 9))
    scroll = ttk.Scrollbar(area, orient='vertical', command=listing.yview)
    listing.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    listing.pack(fill='both', expand=True)
    summary = tk.StringVar()
    ttk.Label(frame, textvariable=summary, wraplength=690).pack(anchor='w', pady=12)
    def refresh(*args):
        nonlocal selected, registry
        selected = scan_files(clear_packages.get(), clear_caches.get(), clear_data.get(), clear_profile.get())
        registry = scan_registry()
        listing.configure(state='normal')
        listing.delete('1.0', 'end')
        for entry in selected:
            listing.insert('end', entry['kind'] + '\n' + entry['path'] + '\n\n')
        for entry in registry:
            listing.insert('end', '卸载登记：' + entry['display'] + '\nHKCU\\' + entry['key'] + '\n\n')
        listing.configure(state='disabled')
        kept = []
        if not clear_data.get():
            kept.append('聊天资料')
        if not clear_profile.get():
            kept.append('B 登录与会话')
        summary.set(f'找到 {len(selected)} 个文件/目录、{len(registry)} 项卸载登记。' + ('保留：' + '、'.join(kept) + '。' if kept else '聊天资料与 B 配置也将删除。') + ' 官方 App 保留。')
    for _, variable in choices:
        variable.trace_add('write', refresh)
    refresh()
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x')
    ttk.Button(buttons, text='取消', command=window.destroy).pack(side='right')
    def begin():
        if owner and getattr(owner, '_shiliao_busy', lambda: False)():
            messagebox.showinfo('卸载拾聊', '请等导入、导出或启动操作完成后再卸载。', parent=window)
            return
        if clear_profile.get():
            try:
                active = profile_in_use()
            except (OSError, subprocess.TimeoutExpired):
                active = True
            if active:
                messagebox.showinfo('卸载拾聊', '请先关闭账号 B 的官方 App 窗口，再选择删除其配置。也可以取消勾选并保留配置。', parent=window)
                return
        refresh()
        warning = '确认关闭拾聊，并删除清单中的新旧版程序及所选残留？\n\n'
        warning += '聊天资料将永久删除。\n' if clear_data.get() else '聊天资料会保留。\n'
        warning += '账号 B 登录与本地会话将删除。' if clear_profile.get() else '账号 B 登录与本地会话会保留。'
        if not messagebox.askyesno('确认卸载', warning, parent=window, default='no'):
            return
        try:
            launch_cleanup(selected, registry, not clear_data.get(), not clear_profile.get())
        except OSError as error:
            messagebox.showerror('卸载未开始', str(error), parent=window)
            return
        if owner:
            owner.destroy()
        else:
            window.destroy()
    ttk.Button(buttons, text='卸载并清理', command=begin).pack(side='right', padx=8)
    ttk.Button(buttons, text='重新扫描', command=refresh).pack(side='left')
    if not owner:
        window.mainloop()
    return window

