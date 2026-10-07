import argparse
import json
from pathlib import Path
import tkinter as tk
from uninstall import open_uninstaller, scan_files

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    if args.self_test:
        root = tk.Tk()
        root.withdraw()
        window = open_uninstaller(root)
        window.withdraw()
        root.update_idletasks()
        assert (Path(__file__).parent / 'cleanup.ps1').exists()
        report = {'nativeUninstallWindow': bool(window.winfo_exists()), 'scanTargets': len(scan_files()), 'nothingDeleted': True}
        if args.data_dir:
            args.data_dir.mkdir(parents=True, exist_ok=True)
            (args.data_dir / 'uninstall-self-test.json').write_text(json.dumps(report), encoding='utf-8')
        root.destroy()
    else:
        open_uninstaller()
