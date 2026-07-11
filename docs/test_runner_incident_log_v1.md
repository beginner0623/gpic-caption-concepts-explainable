# Test Runner Incident Log V1

This file records test-runner failures that affected future workflow decisions.
It is not a list of ordinary failing unit tests.

## 2026-07-08: Direct `run_python.ps1 -m unittest` Repeated A Temp/Timeout Failure

### What Happened

During the attribute inventory status cleanup, a narrow unit test was launched
with:

```powershell
.\scripts\run_python.ps1 -m unittest tests.test_export_attribute_stage5_lexicons
```

The command was still visible in the UI after many minutes and was interrupted
by the user. Before that, related runs had produced repeated
`PermissionError` failures under:

```text
C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_export_attribute_stage5_lexicons\...
```

A stale project Python process was also observed and stopped:

```text
python.exe
Path: C:\Users\rlath\Documents\Codex\gpic-explainable-link\.mamba\env\python.exe
StartTime: 2026-07-08 13:26 KST
High accumulated CPU time
```

### Verified Evidence

- `AGENTS.md` already required bounded test wrappers:
  `scripts\run_tests.ps1`, `scripts\run_unittest_with_timeout.py`, and
  `scripts\run_pytest_with_timeout.py`.
- `scripts\run_python.ps1` only resolves the project root, sets
  `PYTHONPATH`, then executes:

```powershell
& $Python -B @Args
exit $LASTEXITCODE
```

  It is not a test runner and has no repository-level hard timeout or stale
  process cleanup policy.
- `scripts\run_python.ps1` uses `Resolve-Path` for the project root. In this
  repository layout, path resolution can cross from the logical Codex path to
  the OneDrive target path.
- A previous probe in this incident showed that deriving a temp path from
  `Path(__file__).resolve()` could point at the OneDrive target, while a
  non-resolving logical path could point at
  `C:\Users\rlath\Documents\Codex\gpic-explainable-link`.
- The affected test helper had fallback behavior that allowed a repo-local temp
  problem to fall through to the shared Public temp path.

### Root Cause

Primary root cause:

- The validation command used the wrong runner. It directly invoked unittest
  through `scripts\run_python.ps1` instead of the repository's bounded test
  wrappers, despite `AGENTS.md` already requiring bounded wrappers.

Contributing causes:

- The temp helper was allowed to fall back to a shared Public temp path, where
  write and cleanup permissions had already proven unstable in this thread.
- Path derivation used resolving behavior in a repo that can be reached through
  a junction/link, which made logical-path and real-path reasoning diverge.
- After the first failure, the response drifted into repeated test debugging
  instead of stopping, recording the runner problem, and returning to the user's
  requested artifact generation.

### Prevention

- Do not run `scripts\run_python.ps1 -m unittest` or
  `scripts\run_python.ps1 -m pytest` for validation.
- Use `scripts\run_tests.ps1` or the bounded Python wrappers for test
  validation.
- After a hung or interrupted test, inspect and clean stale project processes
  before any rerun.
- When a temp path failure appears, inspect the temp-path decision logic before
  rerunning the test.
- Avoid `Path.resolve()` for repo-local temp paths in this linked repository.

### Current Status

- The long-running project `python.exe` process observed during the incident
  was stopped.
- The interrupted test result must not be used as validation evidence.
- Further work should resume by finishing the `decision_status` cleanup and
  regenerating the 100-caption attribute inventory, not by continuing broad test
  debugging.
