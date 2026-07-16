param(
    [switch]$AllowDifferentCwd
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $ScriptDir "..")).Path
$CurrentDir = (Resolve-Path -LiteralPath (Get-Location)).Path

function Normalize-PathText([string]$PathText) {
    return $PathText.TrimEnd("\", "/").Replace("\", "/").ToLowerInvariant()
}

$NormalizedCurrentDir = Normalize-PathText $CurrentDir
$NormalizedRepoRoot = Normalize-PathText $RepoRoot
if (-not $AllowDifferentCwd -and $NormalizedCurrentDir -ne $NormalizedRepoRoot) {
    throw "Current directory is not the active repo root. cwd='$CurrentDir' repo='$RepoRoot'"
}

$RepoItem = Get-Item -LiteralPath $RepoRoot -Force
if (($RepoItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Active repo root is a reparse point: $RepoRoot"
}

$GitTop = (& git -C $RepoRoot rev-parse --show-toplevel).Trim()
$NormalizedGitTop = Normalize-PathText $GitTop
if ($NormalizedGitTop -ne $NormalizedRepoRoot) {
    throw "Git top-level mismatch. git='$GitTop' repo='$RepoRoot'"
}

$Python = Join-Path $RepoRoot ".mamba\env\python.exe"
$SourceDir = Join-Path $RepoRoot "src"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project Python not found: $Python"
}
if (-not (Test-Path -LiteralPath $SourceDir)) {
    throw "Project src directory not found: $SourceDir"
}

$ReportedPython = (& (Join-Path $RepoRoot "scripts\run_python.ps1") -c "import sys; print(sys.executable)").Trim()
$NormalizedReportedPython = Normalize-PathText $ReportedPython
$NormalizedPython = Normalize-PathText $Python
if ($NormalizedReportedPython -ne $NormalizedPython) {
    throw "run_python.ps1 selected the wrong Python. selected='$ReportedPython' expected='$Python'"
}

Write-Host "ACTIVE_WORKSPACE_OK"
Write-Host "repo=$RepoRoot"
Write-Host "python=$ReportedPython"
