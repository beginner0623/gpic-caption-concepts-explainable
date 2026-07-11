param(
    [ValidateSet("collect", "light", "stage3", "stage4-doc")]
    [string]$Group = "collect",

    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$RunPython = Join-Path $PSScriptRoot "run_python.ps1"
$Script = Join-Path $PSScriptRoot "diagnose_test_runtime.py"

& $RunPython $Script --group $Group --timeout-seconds $TimeoutSeconds
exit $LASTEXITCODE
