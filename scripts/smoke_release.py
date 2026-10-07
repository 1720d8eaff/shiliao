"""Exercise both frozen GUI entrypoints without launching or deleting accounts."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'dist/Shiliao-Windows')
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    for executable, report in (('拾聊桌面版.exe', 'native-self-test.json'), ('卸载拾聊.exe', 'uninstall-self-test.json')):
        result = subprocess.run([str((args.package_dir / executable).resolve()), '--self-test', '--data-dir', str(data)], timeout=60)
        if result.returncode:
            raise RuntimeError(executable + ' failed with exit code ' + str(result.returncode))
        parsed = json.loads((data / report).read_text(encoding='utf-8'))
        if report.startswith('native'):
            assert parsed['nativeWidgetsCreated'] and not parsed['httpServiceStarted']
        else:
            assert parsed['nativeUninstallWindow'] and parsed['nothingDeleted']
        print(executable + ': GUI self-test passed')


if __name__ == '__main__':
    main()
