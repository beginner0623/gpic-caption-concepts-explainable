$ErrorActionPreference = "Stop"

$ActualRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$Root = $ActualRoot

if ($env:GPIC_RUNTIME_ROOT) {
    $Root = (Resolve-Path -LiteralPath $env:GPIC_RUNTIME_ROOT).Path
} else {
    $AsciiRootCandidates = @(
        (Join-Path $env:USERPROFILE "Documents\Codex\gpic-explainable-link"),
        (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Codex\gpic-explainable-link")
    )
    foreach ($AsciiRoot in $AsciiRootCandidates) {
        $AsciiPython = Join-Path $AsciiRoot ".mamba\env\python.exe"
        $AsciiSrc = Join-Path $AsciiRoot "src"
        if ((Test-Path -LiteralPath $AsciiPython) -and (Test-Path -LiteralPath $AsciiSrc)) {
            $Root = (Resolve-Path -LiteralPath $AsciiRoot).Path
            break
        }
    }
}

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
