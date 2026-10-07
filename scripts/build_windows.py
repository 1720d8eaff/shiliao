"""Build an allowlisted Windows release without personal data."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        parser.error('This release builder requires Windows x64 Python.')
    sys.path.insert(0, str(ROOT))
    loader = importlib.machinery.SourceFileLoader('shiliao_desktop', str(ROOT / 'desktop.pyw'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    desktop = importlib.util.module_from_spec(spec)
    loader.exec_module(desktop)
    version = desktop.VERSION
    output = args.output_dir.resolve()
    package = output / 'Shiliao-Windows'
    package.mkdir(parents=True, exist_ok=True)
    build = ROOT / 'build'
    for entry, name in (('desktop.pyw', '拾聊桌面版'), ('uninstaller.pyw', '卸载拾聊')):
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                   '--onefile', '--windowed', '--noupx', '--name', name,
                   '--icon', str(ROOT / 'app.ico'), '--paths', str(ROOT),
                   '--add-data', str(ROOT / 'app.ico') + ':.',
                   '--add-data', str(ROOT / 'cleanup.ps1') + ':.',
                   '--distpath', str(package), '--workpath', str(build / name),
                   '--specpath', str(build), str(ROOT / entry)]
        subprocess.run(command, cwd=ROOT, check=True)
    for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md'):
        shutil.copy2(ROOT / name, package / name)
    (package / '使用说明.txt').write_text(
        '拾聊 ' + version + '\n双击 拾聊桌面版.exe。首次使用账号 B 时需自行登录。\n'
        '导入记录后，用复制续聊内容转到另一个账号。不会合并官方历史侧栏。\n'
        '完整说明见 README.md；许可见 LICENSE 和 third_party。\n'
        '卸载器默认保留资料库及 B 配置，请先检查清理清单。\n', encoding='utf-8-sig')
    shutil.copytree(ROOT / 'third_party', package / 'third_party', dirs_exist_ok=True)
    archive = output / ('Shiliao-v' + version + '-Windows-x64.zip')
    # Never include unknown files left in a previous output directory.
    selected = [package / name for name in ('拾聊桌面版.exe', '卸载拾聊.exe', 'README.md',
                'LICENSE', 'THIRD_PARTY_NOTICES.md', 'CHANGELOG.md', '使用说明.txt')]
    selected.extend(package / 'third_party' / name for name in
                    ('Python.txt', 'Tcl.txt', 'Tk.txt', 'OpenSSL.txt', 'PyInstaller.txt', '说明.txt'))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
        for path in selected:
            target.write(path, path.relative_to(output).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + '.sha256')
    checksum.write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print('Built ' + str(archive))
    print('SHA256 ' + digest)


if __name__ == '__main__':
    main()
