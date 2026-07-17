$ErrorActionPreference = "Stop"

$Root = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$ScratchBase = if ($env:GPIC_TEST_TEMP_ROOT) {
    $env:GPIC_TEST_TEMP_ROOT
} else {
    $CreatorTemp = "C:\Users\Public\Documents\ESTsoft\CreatorTemp"
    if (Test-Path -LiteralPath $CreatorTemp) {
        Join-Path $CreatorTemp "gpic-explainable-link-tests"
    } else {
        Join-Path (Split-Path -Parent $Root) ".gpic_tmp\gpic-explainable-link-tests"
    }
}
$TempRoot = (New-Item -ItemType Directory -Force -Path $ScratchBase).FullName

$env:TMP = $TempRoot
$env:TEMP = $TempRoot
$env:TMPDIR = $TempRoot
$env:PYTHONDONTWRITEBYTECODE = "1"

$RunPython = Join-Path $PSScriptRoot "run_python.ps1"
$UnittestTimeoutRunner = Join-Path $PSScriptRoot "run_unittest_with_timeout.py"
$PytestTimeoutRunner = Join-Path $PSScriptRoot "run_pytest_with_timeout.py"
$PytestAvailable = & $RunPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pytest') else 1)"

$HasPytest = $LASTEXITCODE -eq 0

function Invoke-UnittestWithTimeout {
    param(
        [string[]]$UnittestArgs,
        [int]$TimeoutSeconds
    )
    & $RunPython $UnittestTimeoutRunner --timeout-seconds $TimeoutSeconds -- @UnittestArgs
    exit $LASTEXITCODE
}

function Invoke-PytestWithTimeout {
    param(
        [string[]]$PytestArgs,
        [int]$TimeoutSeconds
    )
    & $RunPython $PytestTimeoutRunner --timeout-seconds $TimeoutSeconds -- @PytestArgs
    exit $LASTEXITCODE
}

function Read-TimeoutArg {
    param([string[]]$InputArgs)

    $TimeoutSeconds = 60
    $OutputArgs = New-Object System.Collections.Generic.List[string]
    for ($Index = 0; $Index -lt $InputArgs.Count; $Index++) {
        if ($InputArgs[$Index] -eq "--timeout-seconds") {
            if ($Index + 1 -ge $InputArgs.Count) {
                throw "--timeout-seconds requires a value."
            }
            $TimeoutSeconds = [int]$InputArgs[$Index + 1]
            $Index += 1
        } else {
            $OutputArgs.Add($InputArgs[$Index])
        }
    }
    return @{
        TimeoutSeconds = $TimeoutSeconds
        Args = [string[]]$OutputArgs
    }
}

if ($Args.Count -eq 0) {
    Invoke-UnittestWithTimeout -UnittestArgs @() -TimeoutSeconds 60
}

$Mode = "unittest"
$RunnerArgs = @($Args)
if ($RunnerArgs[0] -eq "--pytest") {
    $Mode = "pytest"
    if ($RunnerArgs.Count -gt 1) {
        $RunnerArgs = $RunnerArgs[1..($RunnerArgs.Count - 1)]
    } else {
        $RunnerArgs = @("--collect-only", "-q")
    }
} elseif ($RunnerArgs[0] -eq "--") {
    if ($RunnerArgs.Count -gt 1) {
        $RunnerArgs = $RunnerArgs[1..($RunnerArgs.Count - 1)]
    } else {
        $RunnerArgs = @()
    }
}

if ($Mode -eq "pytest") {
    if ($HasPytest) {
        $Parsed = Read-TimeoutArg -InputArgs $RunnerArgs
        Invoke-PytestWithTimeout -PytestArgs $Parsed.Args -TimeoutSeconds $Parsed.TimeoutSeconds
    } else {
        throw "pytest is not installed. Use default unittest mode or install pytest."
    }
} else {
    $TestsPackage = Join-Path $Root "tests\__init__.py"
    if (-not (Test-Path -LiteralPath $TestsPackage)) {
        foreach ($RunnerArg in $RunnerArgs) {
            if ($RunnerArg -match '^tests\.[A-Za-z0-9_.]+$') {
                throw "The tests directory is not a Python package, so dotted names such as '$RunnerArg' are invalid. Use --pytest with tests/test_name.py paths, or unittest discover arguments."
            }
        }
    }
    $Parsed = Read-TimeoutArg -InputArgs $RunnerArgs
    Invoke-UnittestWithTimeout -UnittestArgs $Parsed.Args -TimeoutSeconds $Parsed.TimeoutSeconds
}
