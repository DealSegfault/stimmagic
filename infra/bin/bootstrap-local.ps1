[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "Ce bootstrap PowerShell est reserve a Windows."
}

$InfraRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RepoRoot = Split-Path -Parent $InfraRoot
$RuntimeRoot = if ($env:STIMMA_RUNTIME_DIR) { $env:STIMMA_RUNTIME_DIR } else { Join-Path $InfraRoot ".runtime" }
$ComfyRoot = Join-Path $RuntimeRoot "ComfyUI"
$PluginSource = Join-Path $RepoRoot "custom_nodes\ComfyUI-Stimma"
$PluginLink = Join-Path $ComfyRoot "custom_nodes\ComfyUI-Stimma"
$ComfyRevision = "0f1fa67ad8a68b62c65ebc97a7bf485df2459c3a"

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = @($machinePath, $userPath, $env:Path) -join ";"
$uvPackageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
if (Test-Path -LiteralPath $uvPackageRoot) {
    Get-ChildItem -LiteralPath $uvPackageRoot -Directory -Filter "astral-sh.uv_*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            if (Test-Path -LiteralPath (Join-Path $_.FullName "uv.exe")) {
                $env:Path = "$($_.FullName);$env:Path"
            }
        }
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

foreach ($commandName in @("git.exe", "uv.exe", "codex")) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        throw "$commandName est requis sur PATH. Executez d'abord infra\bin\build-windows-installer.ps1 -CheckOnly."
    }
}
if (-not (Test-Path -LiteralPath $PluginSource -PathType Container)) {
    throw "Le custom node Stimma est introuvable : $PluginSource"
}

& cmd.exe /d /c "codex login status >nul 2>&1"
if ($LASTEXITCODE -ne 0) {
    throw "Codex CLI n'est pas connecte. Lancez 'codex', choisissez 'Sign in with ChatGPT', puis relancez."
}

$VenvPython = Join-Path $ComfyRoot ".venv\Scripts\python.exe"
if ($CheckOnly) {
    if (-not (Test-Path -LiteralPath (Join-Path $ComfyRoot ".git") -PathType Container)) {
        throw "Runtime ComfyUI absent : $ComfyRoot"
    }
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Environnement Python ComfyUI absent : $VenvPython"
    }
    if (-not (Test-Path -LiteralPath $PluginLink)) {
        throw "Lien ComfyUI-Stimma absent : $PluginLink"
    }
    Write-Host "Bootstrap local Windows pret." -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $ComfyRoot ".git") -PathType Container)) {
    if (Test-Path -LiteralPath $ComfyRoot) {
        throw "$ComfyRoot existe deja mais n'est pas un checkout Git ComfyUI."
    }
    Write-Host "Clonage du runtime ComfyUI dans $ComfyRoot..."
    Invoke-Checked "git.exe" "clone" "https://github.com/Comfy-Org/ComfyUI.git" $ComfyRoot
}

Write-Host "Alignement de ComfyUI sur la revision testee..."
Invoke-Checked "git.exe" "-C" $ComfyRoot "fetch" "--quiet" "origin" $ComfyRevision
Invoke-Checked "git.exe" "-C" $ComfyRoot "checkout" "--quiet" $ComfyRevision

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Invoke-Checked "uv.exe" "venv" "--python" "3.12" (Join-Path $ComfyRoot ".venv")
}

Write-Host "Installation des dependances locales (aucun poids de modele GPU)..."
Invoke-Checked "uv.exe" "pip" "install" "--python" $VenvPython `
    "-r" (Join-Path $ComfyRoot "requirements.txt") `
    "-r" (Join-Path $PluginSource "requirements.txt") `
    "modal"

$CustomNodesDir = Split-Path -Parent $PluginLink
New-Item -ItemType Directory -Path $CustomNodesDir -Force | Out-Null
if (Test-Path -LiteralPath $PluginLink) {
    $item = Get-Item -LiteralPath $PluginLink -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "$PluginLink existe deja et n'est pas un lien ou une jonction."
    }
    $target = @($item.Target) | Select-Object -First 1
    if (-not $target -or [IO.Path]::GetFullPath($target) -ne [IO.Path]::GetFullPath($PluginSource)) {
        Remove-Item -LiteralPath $PluginLink -Force
    }
}
if (-not (Test-Path -LiteralPath $PluginLink)) {
    New-Item -ItemType Junction -Path $PluginLink -Target $PluginSource | Out-Null
}

Write-Host "`nBootstrap local termine. Aucun compte Stimma ni cle API LLM n'est requis." -ForegroundColor Green
Write-Host "Codex CLI : connecte via ChatGPT"
Write-Host "Modal reste optionnel. Pour le configurer explicitement :"
Write-Host "  & '$VenvPython' '$RepoRoot\infra\bin\setup-interactive.py'"
