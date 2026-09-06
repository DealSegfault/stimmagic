[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoInstall,
    [switch]$SkipDependencySync
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Ce script doit etre execute sur Windows."
}

$InfraRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $InfraRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $knownPaths = @(
        (Join-Path $env:USERPROFILE ".cargo\bin"),
        (Join-Path $env:USERPROFILE ".deno\bin"),
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links")
    )
    $env:Path = (@($machinePath, $userPath, $env:Path) + $knownPaths | Where-Object { $_ }) -join ";"
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments | Out-Host
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "La commande '$FilePath' a echoue avec le code $exitCode."
    }
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [string]$Override = ""
    )
    if ($NoInstall) {
        throw "Prerequis manquant ($Id). Relancez sans -NoInstall pour l'installer automatiquement."
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget est requis pour installer automatiquement $Id. Installez App Installer depuis Microsoft Store, puis relancez."
    }

    $arguments = @(
        "install", "--id", $Id, "--exact", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--silent"
    )
    if ($Override) {
        $arguments += @("--override", $Override)
    }
    Invoke-Checked $winget.Source @arguments
    Refresh-ProcessPath
}

function Ensure-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$PackageId
    )
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Write-Step "Installation de $Command"
        Install-WingetPackage $PackageId
    }
    $resolved = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $resolved) {
        throw "$Command reste introuvable apres l'installation. Ouvrez un nouveau terminal et relancez ce script."
    }
    return $resolved.Source
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

    $candidates = @(
        "$env:ProgramFiles\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
        "C:\BuildTools\Common7\Tools\VsDevCmd.bat"
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Import-MsvcEnvironment([string]$VsDevCmd) {
    $environment = & cmd.exe /s /c "`"$VsDevCmd`" -arch=x64 -host_arch=x64 >nul && set"
    if ($LASTEXITCODE -ne 0) {
        throw "Impossible d'initialiser l'environnement MSVC avec $VsDevCmd."
    }
    foreach ($line in $environment) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-Item -Path ("Env:{0}" -f $Matches[1]) -Value $Matches[2]
        }
    }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
        throw "Le compilateur C++ MSVC n'est pas disponible apres initialisation."
    }
}

Refresh-ProcessPath

Write-Step "Verification des prerequis Windows"
$git = Ensure-Command "git.exe" "Git.Git"
$node = Ensure-Command "node.exe" "OpenJS.NodeJS.LTS"
$npm = Ensure-Command "npm.cmd" "OpenJS.NodeJS.LTS"
$uv = Ensure-Command "uv.exe" "astral-sh.uv"
$rustc = Ensure-Command "rustc.exe" "Rustlang.Rustup"
$cargo = Ensure-Command "cargo.exe" "Rustlang.Rustup"
$deno = Ensure-Command "deno.exe" "DenoLand.Deno"
$ffmpeg = Ensure-Command "ffmpeg.exe" "Gyan.FFmpeg.Shared"

$nodeMajor = [int]((& $node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) {
    throw "Node.js 20+ est requis ; version detectee : $(& $node --version)."
}

$vsDevCmd = Find-VsDevCmd
if (-not $vsDevCmd) {
    Write-Step "Installation de Visual Studio Build Tools (C++)"
    Install-WingetPackage "Microsoft.VisualStudio.2022.BuildTools" "--wait --passive --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    $vsDevCmd = Find-VsDevCmd
}
if (-not $vsDevCmd) {
    throw "Visual Studio Build Tools avec le workload C++ est introuvable."
}
Import-MsvcEnvironment $vsDevCmd

Write-Host "Git      : $(& $git --version)"
Write-Host "Node     : $(& $node --version)"
Write-Host "uv       : $(& $uv --version)"
Write-Host "Rust     : $(& $rustc --version)"
Write-Host "Deno     : $(& $deno --version | Select-Object -First 1)"
Write-Host "FFmpeg   : $(& $ffmpeg -version | Select-Object -First 1)"
Write-Host "MSVC     : $vsDevCmd"

if ($CheckOnly) {
    Write-Host "`nEnvironnement Windows pret." -ForegroundColor Green
    exit 0
}

if (-not $SkipDependencySync) {
    Write-Step "Installation reproductible des dependances"
    Invoke-Checked $npm "ci" "--prefix" (Join-Path $RepoRoot "frontend")
    Push-Location (Join-Path $RepoRoot "backend")
    try {
        Invoke-Checked $uv "sync" "--all-extras" "--locked"
    }
    finally {
        Pop-Location
    }
}

Write-Step "Construction de l'installateur Windows autonome"
$stimmaCli = Join-Path $RepoRoot "tools\stimma.ps1"
Invoke-Checked "powershell.exe" "-NoProfile" "-ExecutionPolicy" "Bypass" "-File" $stimmaCli "app" "build"

$bundleRoot = Join-Path $RepoRoot "src-tauri\target\release\bundle\nsis"
$installer = Get-ChildItem -LiteralPath $bundleRoot -Filter "*.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $installer) {
    throw "Le build a termine sans produire d'installateur NSIS dans $bundleRoot."
}

$hash = Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256
Write-Host "`nInstallateur pret : $($installer.FullName)" -ForegroundColor Green
Write-Host "SHA-256           : $($hash.Hash.ToLowerInvariant())"
Write-Host "Le poste cible n'a besoin ni de Python, ni de Node.js, ni de Rust."
