"""Start the installed Codex app with isolated local profiles; never copy auth data."""
import base64
import json
import os
from pathlib import Path
import subprocess

EXCLUDED_ENV = {
    'CODEX_HOME', 'CODEX_ELECTRON_USER_DATA_PATH', 'CODEX_CLI_PATH',
    'CODEX_APP_SERVER_WS_URL', 'CODEX_APP_TOOLS_PIPE_PATH', 'CODEX_ACCESS_TOKEN',
    'CODEX_API_KEY', 'OPENAI_API_KEY', 'OPENAI_IDENTITY_TOKEN_FILE',
    'OPENAI_FEDERATION_RULE_ID', 'ELECTRON_RUN_AS_NODE', 'NODE_OPTIONS',
    'CODEX_WINDOWS_REGISTERED_CORE', 'CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY',
}


def installed_executable():
    if os.name != 'nt':
        raise ValueError('双账号启动目前支持 Windows 的 Codex 桌面 App。')
    script = """$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$p = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
if ($null -eq $p) { throw 'NotInstalled' }
[xml]$m = Get-Content -LiteralPath (Join-Path $p.InstallLocation 'AppxManifest.xml')
$a = $m.Package.Applications.Application | Where-Object { $_.Id -eq 'App' } | Select-Object -First 1
if ($null -eq $a) { throw 'NoDesktopEntry' }
$exe = Join-Path $p.InstallLocation ([string]$a.Executable)
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'MissingExecutable' }
@{executable=$exe;version=[string]$p.Version} | ConvertTo-Json -Compress
"""
    command = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
                                capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise ValueError('未找到可启动的 Codex 桌面 App，请先从官方渠道安装。')
        return json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError('暂时无法检测 Codex，请确认它已安装，然后重试。') from error


def launch_profiles(profiles, dry_run=False):
    if not isinstance(profiles, list) or not profiles or any(p not in ('A', 'B') for p in profiles):
        raise ValueError('请选择账号 A、账号 B 或双开。')
    installed = installed_executable()
    executable = Path(installed['executable'])
    profile_root = Path(os.environ['LOCALAPPDATA']) / 'ChatGPT-DualAccount-Test' / 'B'
    env = {key: value for key, value in os.environ.items() if key.upper() not in EXCLUDED_ENV}
    results = []
    for profile in dict.fromkeys(profiles):
        child_env = env.copy()
        arguments = [str(executable)]
        if profile == 'B':
            user_data = profile_root / 'electron-data'
            backend = profile_root / 'codex-home'
            child_env.update(CODEX_HOME=str(backend), CODEX_ELECTRON_USER_DATA_PATH=str(user_data))
            arguments.append('--user-data-dir=' + str(user_data))
            if not dry_run:
                user_data.mkdir(parents=True, exist_ok=True)
                backend.mkdir(parents=True, exist_ok=True)
                config = backend / 'config.toml'
                try:
                    with config.open('x', encoding='utf-8') as stream:
                        stream.write('cli_auth_credentials_store = "file"\n')
                except FileExistsError:
                    pass
        result = {'profile': profile, 'version': installed['version'], 'dryRun': dry_run}
        if not dry_run:
            process = subprocess.Popen(arguments, cwd=executable.parent, env=child_env)
            result['pid'] = process.pid
        results.append(result)
    return {'launched': results}
