$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".mamba\env"
$Python = Join-Path $EnvPath "python.exe"
$Src = Join-Path $Root "src"

if (-not (Test-Path $Python)) {
    throw "Project Python environment was not found. Run scripts\setup_env.ps1 first."
}

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$Src;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $Src
}

& $Python -B @Args
exit $LASTEXITCODE
