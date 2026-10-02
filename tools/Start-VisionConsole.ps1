$ErrorActionPreference = 'Stop'
$consoleRoot = Split-Path $PSScriptRoot -Parent
$consolePython = Join-Path (Split-Path $consoleRoot -Parent) 'commander/.venv/Scripts/python.exe'
Push-Location $consoleRoot
try {
    if (Test-Path -LiteralPath $consolePython) {
        & $consolePython (Join-Path $PSScriptRoot 'run_vision_console.py')
    } else {
        uv run commander-web
    }
} finally {
    Pop-Location
}
