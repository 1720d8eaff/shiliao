﻿param([Parameter(Mandatory=$true)][string]$PlanPath, [switch]$NoDialog)
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$programDirs = @('拾聊原生桌面版','拾聊-Windows','ChatHistory-Importer','ChatGPT-DualAccount-Test','拾聊-双账号工作台-Windows','拾聊桌面版','拾聊','Shiliao-Windows')
$programFiles = @('拾聊桌面版.exe','拾聊.exe','卸载拾聊.exe','拾聊卸载工具.exe')
$packageFiles = @('拾聊-双账号工作台-Windows.zip','拾聊-源码与接口.zip','拾聊原生桌面版-Windows.zip','拾聊原生桌面版-源码.zip','ChatGPT-DualAccount-Test.zip','拾聊导出预览.jpg','拾聊界面预览.jpg','拾聊原生桌面版-验证说明.md')
$cacheDirs = @('app-review','history-build','history-build-v011','history-build-v012','history-import-tests','native-build','native-frozen-self-test','native-self-test','native-uninstall-test')
$cacheFiles = @('native-live-pid.txt','package_native.py','previous-desktop-shiliao.exe')
$stateFiles = @('instance.lock','server-info.json','last-instance-probe.json','last-start-error.json','last-native-error.txt','native-self-test.json')
$shortcuts = @('拾聊.lnk','拾聊桌面版.lnk','拾聊双账号工作台.lnk','拾聊 - 快捷方式.lnk','拾聊桌面版 - 快捷方式.lnk','卸载拾聊.lnk')
$productNames = @('拾聊','拾聊桌面版','拾聊双账号工作台','拾聊 · 双账号工作台','ChatHistoryImporter')
$desktop = [IO.Path]::GetFullPath((Join-Path $env:USERPROFILE 'Desktop'))
$localData = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'ChatHistoryImporter'))
$profileData = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'ChatGPT-DualAccount-Test'))
$programs = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))
$roots = @($plan.packageRoots | ForEach-Object {[IO.Path]::GetFullPath($_).TrimEnd('\')})
$lines = New-Object 'System.Collections.Generic.List[string]'
$failures = New-Object 'System.Collections.Generic.List[string]'

function Test-AllowedPath([string]$PathValue) {
    $full = [IO.Path]::GetFullPath($PathValue).TrimEnd('\')
    $leaf = [IO.Path]::GetFileName($full)
    $parent = [IO.Path]::GetDirectoryName($full)
    if ($parent -ieq [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') -and $leaf -match '^_MEI[a-zA-Z0-9]+$') {
        $icon = Join-Path $full 'app.ico'
        return ((Test-Path -LiteralPath $icon -PathType Leaf) -and (Get-FileHash -LiteralPath $icon -Algorithm SHA256).Hash -ieq '868ced1b0570f491ddfbcf956df5a0ea70d4db9378920eb2f054faf0556d2bc8')
    }
    if ($full -ieq $localData) { return -not [bool]$plan.preserveData }
    if ($full -ieq $profileData) { return -not [bool]$plan.preserveProfile }
    if ($parent -ieq $localData) { return $leaf -in $stateFiles }
    if ($leaf -in $shortcuts -and $parent -in @($desktop,$programs,(Join-Path $programs 'Startup'))) { return $true }
    if ($leaf -eq '拾聊' -and $parent -in @($programs,(Join-Path $programs 'Startup'))) { return $true }
    if ($parent -in $roots) {
        if ([IO.Path]::GetFileName($parent) -eq 'work') { return ($leaf -in $cacheDirs -or $leaf -in $cacheFiles) }
        return ($leaf -in $programDirs -or $leaf -in $programFiles -or $leaf -in $packageFiles)
    }
    return $false
}

function Test-NoLinks([string]$PathValue) {
    $item = Get-Item -LiteralPath $PathValue -Force
    $ancestor = $item
    while ($null -ne $ancestor) {
        if (($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
        if ($ancestor -is [IO.DirectoryInfo]) { $ancestor = $ancestor.Parent }
        else { $ancestor = $ancestor.Directory }
    }
    if ($item.PSIsContainer) {
        $links = @(Get-ChildItem -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop | Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
        if ($links.Count -gt 0) { return $false }
    }
    return $true
}

try {
    # Validate every target before stopping any process or deleting any item.
    $targets = @()
    foreach ($entry in $plan.files) {
        $full = [IO.Path]::GetFullPath([string]$entry.path).TrimEnd('\')
        if (-not (Test-AllowedPath $full)) { throw "拒绝不在拾聊清理范围内的路径：$full" }
        if (Test-Path -LiteralPath $full) {
            if (-not (Test-NoLinks $full)) { throw "清理目标含链接或目录联接，请手工检查：$full" }
            $targets += $full
        }
    }
    if (-not $plan.preserveProfile) {
        $bPath = Join-Path $profileData 'B'
        $inUse = @(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -and $_.CommandLine.IndexOf($bPath,[StringComparison]::OrdinalIgnoreCase) -ge 0})
        if ($inUse.Count -gt 0) { throw '账号 B 的官方 App 仍在使用独立配置，请关闭 B 窗口后重试。' }
    }
    Start-Sleep -Seconds 2
    # Only stop this product's executable or exact source entry points in selected folders.
    foreach ($process in Get-CimInstance Win32_Process) {
        $owned = $false
        foreach ($target in $targets) {
            if ($process.ExecutablePath -and ($process.ExecutablePath -ieq $target -or $process.ExecutablePath.StartsWith($target + '\',[StringComparison]::OrdinalIgnoreCase))) {
                $owned = $true
            }
            if ($process.Name -in @('python.exe','pythonw.exe') -and $process.CommandLine) {
                foreach ($source in @('拾聊.pyw','desktop.pyw','uninstaller.pyw','server.py')) {
                    $sourcePath = Join-Path $target $source
                    $nestedSource = Join-Path (Join-Path $target '源码') $source
                    if ($process.CommandLine.IndexOf($sourcePath,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or $process.CommandLine.IndexOf($nestedSource,[StringComparison]::OrdinalIgnoreCase) -ge 0) { $owned = $true }
                }
            }
        }
        if ($owned -and $process.ProcessId -ne $PID) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($target in $targets) {
        $deleted = $false
        for ($attempt = 0; $attempt -lt 12; $attempt++) {
            try {
                if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop }
                $deleted = -not (Test-Path -LiteralPath $target)
                if ($deleted) { break }
            } catch {
                if ($attempt -eq 11) { $failures.Add($target + '：' + $_.Exception.Message) }
            }
            Start-Sleep -Milliseconds 500
        }
        if ($deleted) { $lines.Add('已删除：' + $target) }
    }
    foreach ($entry in $plan.registry) {
        try {
            $key = [string]$entry.key
            if ($key -ieq 'Software\Microsoft\Windows\CurrentVersion\Run') {
                if ($entry.name -notin $productNames) { throw '启动项名称与拾聊不匹配。' }
                $run = 'HKCU:\' + $key
                $current = (Get-ItemProperty -LiteralPath $run -Name $entry.name -ErrorAction SilentlyContinue).($entry.name)
                if ($current) {
                    if ($current -ne $entry.value) { throw '启动项已改变，请重新扫描。' }
                    Remove-ItemProperty -LiteralPath $run -Name $entry.name -Force
                    $lines.Add('已删除启动项：' + $entry.name)
                }
                continue
            }
            if (-not $key.StartsWith('Software\Microsoft\Windows\CurrentVersion\Uninstall\',[StringComparison]::OrdinalIgnoreCase)) { throw '注册表目标不在允许范围。' }
            $path = 'HKCU:\' + $key
            if (Test-Path -LiteralPath $path) {
                $display = (Get-ItemProperty -LiteralPath $path).DisplayName
                if ($display -notin $productNames) { throw '卸载登记名称与拾聊不匹配。' }
                Remove-Item -LiteralPath $path -Recurse -Force
                $lines.Add('已删除登记：' + $path)
            }
        } catch { $failures.Add('注册表：' + $_.Exception.Message) }
    }
} catch { $failures.Add($_.Exception.Message) }

$kept = ''
if ($plan.preserveData) { $kept += '聊天资料已保留。' }
if ($plan.preserveProfile) { $kept += '账号 B 登录与会话已保留。' }
$lines.Add($kept)
$lines.Add('官方 Codex / ChatGPT App 未卸载。')
foreach ($failure in $failures) { $lines.Add('未完成：' + $failure) }
$report = [IO.Path]::GetFullPath([string]$plan.report)
if ([IO.Path]::GetDirectoryName($report) -ieq [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') -and [IO.Path]::GetFileName($report) -match '^Shiliao-uninstall-[a-f0-9]+-report\.txt$') {
    $lines | Set-Content -LiteralPath $report -Encoding UTF8
}
if ($failures.Count -eq 0) { $message = '拾聊新旧版本清理完成。' + "`n`n" + $kept }
else { $message = '有 ' + $failures.Count + ' 项未清理完成。请查看报告。' + "`n`n" + ($failures -join "`n") }
$message += "`n`n清理报告：" + $report
if (-not $NoDialog) {
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class ShiliaoCleanupDialog { [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int MessageBox(IntPtr hWnd, string text, string caption, uint type); }'
    [void][ShiliaoCleanupDialog]::MessageBox([IntPtr]::Zero,$message,'拾聊 · 卸载结果',0x40)
}
Remove-Item -LiteralPath $PlanPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
