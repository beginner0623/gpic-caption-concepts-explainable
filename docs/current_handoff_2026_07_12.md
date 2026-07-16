# Current Handoff 2026-07-12

## Active Repo

Use this repo as the active workspace:

`C:\Users\rlath\Documents\Codex\gpic-caption-concepts-explainable`

This repo was copied from the earlier OneDrive-backed junction workspace:

`C:\Users\rlath\Documents\Codex\gpic-explainable-link`

Do not use the old junction path for new work unless the user explicitly asks
for a comparison against the old copy.

## Why This File Exists

The current Codex conversation may still have an older default workspace. To
avoid editing or testing the wrong directory, every consequential command should
use the active repo path above as its explicit working directory.

Before long-running scripts, generated-artifact commands, benchmarks, or tests
used as decision evidence, run:

```powershell
.\scripts\assert_active_workspace.ps1
```

Expected output starts with:

```text
ACTIVE_WORKSPACE_OK
```

## Migration Status

- Full repo copy completed with `.mamba` included.
- Robocopy summary copied 3,548 dirs, 37,672 files, and 5.635 GB with failed 0.
- New local workspace reparse count was 0.
- `scripts\run_python.ps1` was fixed so it prefers the current repo root when
  `.mamba\env\python.exe` and `src` exist there.
- Copied `.mamba` smoke checks passed:
  - Python 3.11.15
  - spaCy 3.8.14
  - `en_core_web_trf` loaded
  - PyTorch CUDA available
  - CuPy CUDA runtime device count 1
  - OEWN `oewn:2025+`, OEWN Morphy, and NLTK WordNet 3.0 worked
- Narrow validation passed:
  - `test_build_gpic_observed_object_inventory.py`: 3 passed
  - `compileall scripts src`: succeeded
  - `git diff --check`: no whitespace errors, only existing CRLF/LF warnings

## Current Decision

Keep using the copied `.mamba` environment. Do not create a fresh environment
unless a reproducible environment failure appears.

## Residual Risk

One initial `check_runtime_env.py --require-spacy-gpu` run returned a transient
spaCy GPU model-load `PermissionError`, but direct GPU spaCy load and repeated
runtime check succeeded. If it reappears, investigate GPU/CuPy/spaCy load order
or Windows file access before recreating the environment.

## Next Work Context

Recent pipeline work before the migration focused on:

- tag-list processing
- object inventory prior reuse
- attribute/action inventory gates
- preposition MWE relation handling
- conjunct handling
- passive and `acl` event-role handling
- avoiding OneDrive/junction sandbox write problems

Use `AGENTS.md`, `docs\rules_v1.md`, and `docs\answer_protocol.md` before
editing code or pipeline rules.
