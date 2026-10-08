param([switch]$Restart, [switch]$Background)
$ErrorActionPreference = 'Stop'
$consoleRoot = Split-Path $PSScriptRoot -Parent
$consolePython = Join-Path (Split-Path $consoleRoot -Parent) 'commander/.venv/Scripts/python.exe'
$runner = Join-Path $PSScriptRoot 'run_vision_console.py'
if ($Restart) {
    $listeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if ($process.CommandLine -notlike "*$runner*") {
            throw "Port 8000 belongs to a different application (PID $($process.ProcessId))"
        }
        Stop-Process -Id $process.ProcessId
    }
}
if ($Background) {
    if (-not (Test-Path -LiteralPath $consolePython)) { throw 'Commander Python environment is missing' }
    $logPrefix = Join-Path $env:TEMP ('talos-vision-console-' + [guid]::NewGuid().ToString('N'))
    Start-Process -FilePath $consolePython -ArgumentList ('"' + $runner + '"') -WorkingDirectory $consoleRoot -WindowStyle Hidden -RedirectStandardOutput "$logPrefix.out" -RedirectStandardError "$logPrefix.err" | Out-Null
    $started = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $health = Invoke-RestMethod -TimeoutSec 1 http://127.0.0.1:8000/api/health
            if ($health.status -eq 'ok') { $started = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
    if (-not $started) { throw "Commander did not start. See $logPrefix.err" }
    Write-Output 'Commander: http://127.0.0.1:8000'
    return
}
Push-Location $consoleRoot
try {
    if (Test-Path -LiteralPath $consolePython) {
        & $consolePython $runner
    } else {
        uv run commander-web
    }
} finally {
    Pop-Location
}
