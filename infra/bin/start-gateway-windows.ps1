$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$InfraRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $InfraRoot
$bash = if (Test-Path -LiteralPath "$env:ProgramFiles\Git\bin\bash.exe") {
    "$env:ProgramFiles\Git\bin\bash.exe"
} elseif (Test-Path -LiteralPath "${env:ProgramFiles(x86)}\Git\bin\bash.exe") {
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
} else {
    throw "Git Bash est requis. Installez Git for Windows."
}

if (Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Stimma H3 Gateway est deja actif sur 127.0.0.1:8188."
    exit 0
}

$env:STIMMA_REPO_ROOT_WINDOWS = $RepoRoot
$command = @'
set -eu
cd "$(cygpath -u "$STIMMA_REPO_ROOT_WINDOWS")"
exec bash infra/bin/start-gateway.sh
'@
& $bash --login -lc $command
exit $LASTEXITCODE
