[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$InfraRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $InfraRoot

function Add-PathEntry([string]$Path) {
    if ($Path -and (Test-Path -LiteralPath $Path) -and (($env:Path -split ";") -notcontains $Path)) {
        $env:Path = "$Path;$env:Path"
    }
}

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = @($machinePath, $userPath, $env:Path) -join ";"
Add-PathEntry (Join-Path $env:USERPROFILE ".cargo\bin")
Add-PathEntry (Join-Path $env:USERPROFILE ".deno\bin")
Add-PathEntry (Join-Path $env:USERPROFILE ".local\bin")
Add-PathEntry (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links")

$packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
if (Test-Path -LiteralPath $packageRoot) {
    Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "DenoLand.Deno_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Add-PathEntry $_.FullName }
    Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "astral-sh.uv_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Add-PathEntry $_.FullName }
    Get-ChildItem -LiteralPath $packageRoot -Directory -Filter "Gyan.FFmpeg.*_*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Directory -Filter "ffmpeg-*" -ErrorAction SilentlyContinue |
                ForEach-Object { Add-PathEntry (Join-Path $_.FullName "bin") }
        }
}

function Require-Command([string]$Name, [string]$Hint) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Name est introuvable. $Hint"
    }
    return $command.Source
}

function Find-VsDevCmd {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -eq 0 -and $installPath) {
            $candidate = Join-Path ($installPath | Select-Object -First 1) "Common7\Tools\VsDevCmd.bat"
            if (Test-Path -LiteralPath $candidate) {
                return $candidate
            }
        }
    }
    return @(
        "$env:ProgramFiles\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "C:\BuildTools\Common7\Tools\VsDevCmd.bat"
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

$bash = if (Test-Path -LiteralPath "$env:ProgramFiles\Git\bin\bash.exe") {
    "$env:ProgramFiles\Git\bin\bash.exe"
} elseif (Test-Path -LiteralPath "${env:ProgramFiles(x86)}\Git\bin\bash.exe") {
    "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
} else {
    Require-Command "bash.exe" "Installez Git for Windows."
}

$vsDevCmd = Find-VsDevCmd
if (-not $vsDevCmd) {
    throw "Visual Studio Build Tools avec le workload C++ est requis."
}
$environment = & cmd.exe /s /c "`"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && set"
if ($LASTEXITCODE -ne 0) {
    throw "Impossible d'initialiser Visual Studio Build Tools."
}
foreach ($line in $environment) {
    if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        Set-Item -Path ("Env:{0}" -f $Matches[1]) -Value $Matches[2]
    }
}

foreach ($requirement in @(
    @("node.exe", "Installez Node.js 20+."),
    @("uv.exe", "Lancez build-windows-installer.ps1 -CheckOnly."),
    @("deno.exe", "Installez Deno."),
    @("rustc.exe", "Installez Rustup."),
    @("ffmpeg.exe", "Installez FFmpeg."),
    @("codex", "Installez Codex CLI.")
)) {
    Require-Command $requirement[0] $requirement[1] | Out-Null
}

& codex login status | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Codex CLI n'est pas connecte. Lancez codex et choisissez Sign in with ChatGPT."
}

$runtimePython = Join-Path $InfraRoot ".runtime\ComfyUI\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    throw "Runtime ComfyUI absent. Lancez infra\bin\bootstrap-local.ps1."
}

if ($Check) {
    Write-Host "Launcher Stimma Windows pret." -ForegroundColor Green
    exit 0
}

$cargoTarget = if (Test-Path -LiteralPath "D:\stimmagic-cargo-target") {
    "D:\stimmagic-cargo-target"
} else {
    Join-Path $env:LOCALAPPDATA "Stimma\cargo-target"
}
$launchLogs = Join-Path $env:LOCALAPPDATA "Stimma\Logs"
New-Item -ItemType Directory -Path $cargoTarget -Force | Out-Null
New-Item -ItemType Directory -Path $launchLogs -Force | Out-Null

$env:STIMMA_REPO_ROOT_WINDOWS = $RepoRoot
$env:STIMMA_CARGO_TARGET_DIR_WINDOWS = $cargoTarget
$env:STIMMA_LAUNCH_LOG_DIR_WINDOWS = $launchLogs

$launchCommand = @'
set -eu
export CARGO_TARGET_DIR="$(cygpath -u "$STIMMA_CARGO_TARGET_DIR_WINDOWS")"
export STIMMA_LAUNCH_LOG_DIR="$(cygpath -u "$STIMMA_LAUNCH_LOG_DIR_WINDOWS")"
cd "$(cygpath -u "$STIMMA_REPO_ROOT_WINDOWS")"
exec bash infra/bin/launch-stimma.sh
'@

Write-Host "Lancement de Stimma : passerelle, backend, frontend et application..."
$launchCommand | & $bash --login -s --
exit $LASTEXITCODE
