<#
.EXAMPLE
  .\tools\Deploy-PiVision.ps1 -RestartCommander
.EXAMPLE
  .\tools\Deploy-PiVision.ps1 -PrepareOnly
#>
[CmdletBinding()]
param(
    [string]$PiHost = 'pi@bluey.local',
    [string]$RemoteRoot = '/home/pi/talos-vision-releases',
    [switch]$PrepareOnly,
    [switch]$RestartCommander
)
$ErrorActionPreference = 'Stop'
if ($PiHost -notmatch '^[A-Za-z0-9_.@-]+$') { throw 'Invalid Pi host' }
if ($RemoteRoot -notmatch '^/home/pi/[A-Za-z0-9_./-]+$' -or $RemoteRoot.Split('/') -contains '..') {
    throw 'RemoteRoot must be a directory under /home/pi with no parent traversal'
}
$consoleRoot = Split-Path $PSScriptRoot -Parent
$workspaceRoot = Split-Path $consoleRoot -Parent
$trackerRoot = Join-Path $PSScriptRoot 'pi_tracker'
$consolePython = Join-Path $workspaceRoot 'commander/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $consolePython)) { throw "Python environment missing: $consolePython" }
foreach ($program in @('tar', 'ssh', 'scp')) { $null = Get-Command $program -ErrorAction Stop }
function Invoke-Checked {
    param([string]$Program, [string[]]$CommandArguments)
    & $Program @CommandArguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with code $LASTEXITCODE" }
}
$releaseId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$bundleDirectory = Join-Path $env:TEMP "talos-pivision-$releaseId"
$sourceDirectory = Join-Path $bundleDirectory 'source'
$null = New-Item -ItemType Directory -Path $sourceDirectory -Force
$utf8 = New-Object System.Text.UTF8Encoding($false)
$files = @{}
foreach ($source in Get-ChildItem -LiteralPath $trackerRoot -Filter '*.py' -File) {
    $target = Join-Path $sourceDirectory $source.Name
    [IO.File]::WriteAllText($target, [IO.File]::ReadAllText($source.FullName).Replace("`r`n", "`n"), $utf8)
    $files[$source.Name] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
}
foreach ($required in @('main.py', 'controller.py', 'control_api.py', 'web_server.py', 'perception.py')) {
    if (-not $files.ContainsKey($required)) { throw "Tracker source missing: $required" }
}
$commanderCommit = (& git -C $consoleRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Commander revision' }
$commanderDirty = @(& git -C $consoleRoot status --porcelain).Count -gt 0
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Commander worktree status' }
$manifest = @{ schema_version = 1; release_id = $releaseId; commander_commit = $commanderCommit; commander_dirty = $commanderDirty; files = $files }
[IO.File]::WriteAllText((Join-Path $sourceDirectory 'deployment.json'), ($manifest | ConvertTo-Json -Depth 4), $utf8)
$bundle = Join-Path $bundleDirectory 'pivision.tar'
Invoke-Checked 'tar' @('-cf', $bundle, '-C', $sourceDirectory, '.')
Invoke-Checked $consolePython @((Join-Path $PSScriptRoot 'pivision_deploy.py'), '--check-bundle', $bundle)
Write-Output "Bundle: $bundle"
if ($PrepareOnly) { return }

Push-Location (Join-Path $consoleRoot 'web')
try { Invoke-Checked 'npm.cmd' @('run', 'build') } finally { Pop-Location }
$remoteUpload = $RemoteRoot.TrimEnd('/') + '/uploads/' + $releaseId
$sshOptions = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2')
Invoke-Checked 'ssh' ($sshOptions + @($PiHost, "mkdir -p '$remoteUpload'"))
Invoke-Checked 'scp' ($sshOptions + @($bundle, (Join-Path $PSScriptRoot 'pivision_deploy.py'), "${PiHost}:$remoteUpload/"))
Invoke-Checked 'ssh' ($sshOptions + @($PiHost, "sudo -n python3 '$remoteUpload/pivision_deploy.py' --apply '$remoteUpload/pivision.tar' --root '$RemoteRoot'"))
if ($RestartCommander) {
    & (Join-Path $PSScriptRoot 'Start-VisionConsole.ps1') -Restart -Background
}
