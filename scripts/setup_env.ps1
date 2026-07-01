$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".mamba\env"
$Python = Join-Path $EnvPath "python.exe"
$EnvFile = Join-Path $Root "environment.yml"
$TempEnvFile = Join-Path $env:TEMP "gpic_caption_concepts_explainable_environment.yml"

if (-not (Get-Command micromamba -ErrorAction SilentlyContinue)) {
    throw "micromamba was not found on PATH."
}

Copy-Item -Force -Path $EnvFile -Destination $TempEnvFile

if (Test-Path $Python) {
    micromamba install -y -p $EnvPath -f $TempEnvFile
} else {
    micromamba create -y -p $EnvPath -f $TempEnvFile
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $Python -B -c "import sys, spacy; print(sys.executable); print('spacy', spacy.__version__)"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
