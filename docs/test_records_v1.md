# V1 Test Records

This file records tests that affect future implementation decisions.

## 2026-07-08: Attribute Type Deferral And Object Core-Span Consumption

Change:

- Active Stage 5/6/report no longer exports `attribute_type`.
- Stage 4 and the attribute inventory builder consume selected object core
  suffix tokens, not necessarily the full lookup span.

Commands:

```powershell
.\scripts\run_python.ps1 -c "... ast.parse(...) ..."
.\scripts\run_tests.ps1 --timeout-seconds 45 discover -s tests -p test_build_gpic_observed_attribute_inventory.py
.\scripts\run_tests.ps1 --timeout-seconds 45 discover -s tests -p test_export_attribute_stage5_lexicons.py
```

Result:

- AST parse check passed for the edited Python files.
- `test_build_gpic_observed_attribute_inventory.py`: 5 tests passed.
- `test_export_attribute_stage5_lexicons.py`: hard-timeout after 45 seconds.
  No `python.exe` process remained afterward. Cause not established from this
  run; do not report that export behavior is runtime-verified from this test.

Interpretation:

- The object core-span rule is covered by the attribute inventory test file.
- Attribute type export behavior is statically updated but the export unittest
  file was not successfully completed in this run.

## 2026-07-03: Action Parent Renamed To Action Type

Change:

- Kept object parent concepts as `parent_concepts`.
- Replaced action parent lookup with `action_type` lookup.
- Replaced `resources/lexicons/action_parents.tsv` with `resources/lexicons/action_types.tsv`.

Commands:

```powershell
.\scripts\run_python.ps1 -m unittest tests.test_stage5_canonicalize tests.test_stage6_export_counts tests.test_schema
.\scripts\run_python.ps1 -m unittest discover tests
```

Result:

- Targeted tests: 11 passed.
- Full unit test suite: 45 passed.

Interpretation:

- Stage 5 now stores action type in `canonical_detail.action_type`.
- Stage 6 `action_event` facts export `action_type`.
- Action mentions no longer receive `parent_concepts` from Stage 5.
- Object parent behavior remains unchanged.

## 2026-07-03: Prevent Accidental Full Test Runs

Problem:

- Running `.\scripts\run_tests.ps1` executed the full pytest suite by default.
- The run was interrupted after a long wall time.
- Collection also loaded the transformer model because two `skipUnless`
  decorators called `spacy.load()` at import/collection time.

Changes:

- `scripts/run_tests.ps1` now defaults to `pytest --collect-only -q`.
- Full pytest execution now requires `.\scripts\run_tests.ps1 --full`.
- Other pytest execution args are rejected unless `--collect-only` is present.
- `tests/test_stage3_annotate.py` and `tests/test_stage4_extract_raw.py` now
  check for the transformer model package with `importlib.util.find_spec()`
  during collection instead of calling `spacy.load()`.

Commands:

```powershell
.\scripts\run_tests.ps1
.\scripts\run_tests.ps1 -q
```

Result:

- Default test command collected 45 tests in 4.39 seconds.
- Accidental execution command `.\scripts\run_tests.ps1 -q` was rejected before
  pytest execution.

Interpretation:

- The default test command no longer starts the full suite.
- Transformer model loading no longer happens during pytest collection.

## 2026-07-03: Add Hard Pytest Subprocess Timeout

Problem:

- Shell-level command timeouts can stop the outer PowerShell process while
  leaving the inner `python.exe -m pytest` process alive.
- `--maxfail=1` is not a timeout and does not protect against hangs.

Change:

- Added `scripts/run_pytest_with_timeout.py`.
- `scripts/run_tests.ps1` now runs pytest through this Python wrapper.
- The wrapper executes `python -m pytest ...` with
  `subprocess.run(..., timeout=...)`.
- Default timeout is 60 seconds.
- A custom timeout can be passed with `--timeout-seconds N`.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/run_pytest_with_timeout.py').read_text(encoding='utf-8')); print('syntax ok')"
.\scripts\run_tests.ps1 --collect-only -q --timeout-seconds 20
.\scripts\run_tests.ps1 --full --timeout-seconds 1 -q tests/test_stage3_annotate.py::Stage3AnnotateTest
Get-Process | Where-Object { $_.ProcessName -match 'python|pytest' } | Select-Object Id,ProcessName,CPU,StartTime,Path
```

Result:

- Syntax check passed.
- Collection completed: 45 tests collected in 4.53 seconds.
- The 1-second transformer test probe returned
  `PYTEST_TIMEOUT: killed pytest after 1.001s limit=1s`.
- No `python` or `pytest` process remained after the timeout probe.

Interpretation:

- `run_tests.ps1` now has a child-process-level pytest timeout.
- This does not identify the original 50-minute root cause by itself.
- It prevents the same class of lingering pytest process while that cause is
  investigated in smaller timed probes.

## 2026-07-03: Pytest Cache And Sandbox Temp Write Diagnosis

Problem:

- A pytest run could print passing tests and then fail to terminate.
- A later bounded `light` probe failed quickly with `PermissionError` while
  writing files under a Python `TemporaryDirectory`.

Verified observations:

- `tests/test_schema.py` passed its assertions but hung after completion when
  pytest cacheprovider was enabled.
- The same schema test exited normally when pytest ran with
  `-p no:cacheprovider`.
- A sandboxed `run_tests.ps1` execution of `tests/test_io_jsonl.py` failed in
  0.15 seconds with `PermissionError` when writing inside the temp directory.
- The same bounded command outside the sandbox passed in 0.04 seconds.
- The bounded `light` probe outside the sandbox passed in 8.017 seconds.

Changes:

- `scripts/run_pytest_with_timeout.py` runs pytest with
  `-p no:cacheprovider`.
- `scripts/diagnose_test_runtime.py` runs pytest with
  `-p no:cacheprovider`.
- `scripts/run_tests.ps1`, `scripts/run_pytest_with_timeout.py`, and
  `scripts/diagnose_test_runtime.py` default test temp files to
  `C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic-explainable-link-tests`
  when that directory exists.
- `scripts/diagnose_test_runtime.ps1` no longer exposes the old `all-probes`
  option.

Commands:

```powershell
.\scripts\run_python.ps1 -m compileall scripts
.\scripts\run_tests.ps1 --full --timeout-seconds 30 -q --maxfail=1 -vv tests/test_io_jsonl.py
.\scripts\diagnose_test_runtime.ps1 -Group light -TimeoutSeconds 60
```

Results:

- Script syntax check passed.
- Sandboxed `tests/test_io_jsonl.py` still failed with `PermissionError`, so
  the failure was not treated as a pipeline-code regression.
- The same bounded single-file pytest command outside the sandbox passed:
  `2 passed in 0.04s`.
- Outside-sandbox `light` probe passed:
  `elapsed_seconds=8.017`, `timeout_seconds=60`, `exit_code=0`.
- Light probe summary:
  `C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic-explainable-link-tests\test_runtime_20260703_142216.summary.tsv`

Interpretation:

- The earlier post-pass hang was caused by pytest cache finalization behavior in
  this junction/sandbox environment, not by the schema tests themselves.
- The later temp write failures are sandbox subprocess permission failures, not
  JSONL writer failures.
- Future pytest runs should use the bounded wrappers and avoid raw pytest.
- If a sandboxed pytest run reports temp-directory `PermissionError`, confirm
  with the same bounded command outside the sandbox before changing pipeline
  code.

## 2026-07-03: Make Unittest The Default Test Runner

Reason:

- Current tests are `unittest.TestCase` based.
- No pytest fixture-only test syntax was found in the test files.
- Pytest remains useful for diagnostic collection and duration reports, but it
  is not needed for the default correctness path.
- The default path should avoid pytest unless pytest-specific diagnostics are
  needed.

Changes:

- Added `scripts/run_unittest_with_timeout.py`.
- `scripts/run_tests.ps1` now runs bounded `unittest` by default.
- Pytest is now reached only with explicit `--pytest`.
- `AGENTS.md` now states the default runner policy as `unittest` first, pytest
  only for diagnostic exceptions.

Commands:

```powershell
.\scripts\run_python.ps1 -m compileall scripts
.\scripts\run_tests.ps1 --timeout-seconds 30 tests.test_io_jsonl
.\scripts\run_tests.ps1 --timeout-seconds 30 discover -s tests -p test_io_jsonl.py
```

Results:

- Script syntax passed.
- `tests.test_io_jsonl` module-name execution failed because `tests` is not a
  package. Targeted unittest execution should use discovery syntax:
  `discover -s tests -p test_io_jsonl.py`.
- Sandboxed discovery still failed with temp-directory `PermissionError`.
- The same bounded unittest discovery command outside the sandbox passed:
  `Ran 2 tests in 0.011s`, `OK`.

Interpretation:

- Switching to `unittest` is still useful because the default runner no longer
  depends on pytest or pytest cache behavior.
- It does not solve Codex sandbox temp-write restrictions for tests that create
  `TemporaryDirectory` files.
- Temp-writing tests must still be verified with the bounded runner outside the
  sandbox when the sandbox reports `PermissionError`.

## 2026-07-05: Atomic TSV Writer Unit Test Temp Directory

Reason:

- Generated TSV writers were changed to write a same-directory temp file and
  then atomically replace the final path.
- The first atomic writer unittest used Python's default
  `tempfile.TemporaryDirectory()`, which resolved to
  `C:\Users\Public\Documents\ESTsoft\CreatorTemp` in this environment.

Command:

```powershell
.\scripts\run_python.ps1 -m unittest tests.test_atomic_io -v
```

Initial result:

- Failed before exercising `atomic_text_writer`.
- Error: `PermissionError` while writing `out.tsv` inside the default temp
  directory.

Fix:

- Updated `tests/test_atomic_io.py` to create its temp directories under the
  repo-local `.tmp_tests/atomic_io` path and remove them after each test.

Interpretation:

- This failure was a test temp-directory sandbox issue, not evidence that the
  atomic writer itself was broken.
- Future tests that need filesystem writes should choose an explicit writable
  temp root instead of relying on Python's default temp directory.

## 2026-07-05: Generated TSV Write Timeout And Sandbox Permission Diagnosis

Problem:

- A raw Objects365 candidate generation command was interrupted after a long
  wait.
- A bounded `scripts/run_script_with_timeout.py` run later timed out at 90
  seconds.
- The first implementation of `atomic_text_writer` used
  `tempfile.NamedTemporaryFile(dir=target.parent, delete=False)`.

Verified observations:

- The bounded runner killed the script with `SCRIPT_TIMEOUT` and left no Python
  child process behind.
- Phase logging showed the expensive normal phase was `Morphy(oewn)`, around
  18 to 21 seconds.
- Candidate row construction took about 1 second.
- In sandboxed execution, same-directory generated TSV temp creation failed
  with `PermissionError`.
- The same bounded generation command outside the sandbox completed in about
  25 seconds.

Changes:

- `atomic_text_writer` no longer uses `NamedTemporaryFile`.
- It now creates an explicit same-directory temp path using
  `.final_name.pid.uuid.tmp`, opens it with exclusive `"x"` mode, fsyncs it,
  and replaces the final path with `os.replace`.
- `scripts/build_objects365_oewn_candidates.py` now prints coarse phase timing
  and TSV write timing so future runs show where time is spent.

Commands:

```powershell
.\scripts\run_python.ps1 -m compileall scripts src tests
.\scripts\run_python.ps1 -m unittest tests.test_atomic_io -v
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 90 scripts\build_objects365_oewn_candidates.py
```

Results:

- Compile passed.
- Atomic writer unit tests passed: 2 tests.
- Sandboxed generated TSV write failed with `PermissionError`.
- Outside-sandbox bounded generation succeeded.
- Objects365 summary after successful generation:
  `rows=365`, `selected_rows=230`, `reused_selected_rows=68`,
  `rejected_rows=6`, `ambiguous_like_rows=0`, `unresolved_like_rows=61`.

Interpretation:

- The long wait was not a lingering Python child after the bounded runner was
  added.
- The main recurring issue is that generated artifact writes under this
  junction/OneDrive-backed repo path can be denied inside the Codex sandbox.
- `require_escalated` is not a permission fix; it is the correct execution mode
  for this generated artifact command when the sandbox denies the write.
- Long generated artifact scripts must still use the bounded runner.

## 2026-07-06: Stage 2 Tokenizer Source Alignment Test

Change under test:

- `make_stage2_nlp()` now loads `en_core_web_trf` in tokenizer-only mode instead
  of `spacy.blank("en")`.
- Stage 2 still runs only `nlp.make_doc(caption)` plus span protection.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage2_preprocess.py
.\scripts\run_python.ps1 -c "import ast, pathlib; files=['src/gpic_concepts_v1/stage2_preprocess.py','tests/test_stage2_preprocess.py','scripts/run_unittest_with_timeout.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('ast ok')"
```

Results:

- Stage 2 tests passed: 6 tests.
- Changed-file syntax check passed: `ast ok`.

Related test runner adjustment:

- `scripts/run_unittest_with_timeout.py` now uses
  `root.parent/.gpic_tmp/gpic-explainable-link-tests` as its default temp root
  instead of Public CreatorTemp.
- `tests/test_stage2_preprocess.py` now writes unique temp files under the
  runner-provided temp root instead of creating a fresh `TemporaryDirectory`.

Compile note:

- `.\scripts\run_python.ps1 -m compileall src tests scripts` failed because
  `compileall` writes `.pyc` files into `__pycache__` under the
  junction/OneDrive-backed repo path.
- This failure is a write-permission issue, not a syntax error in the changed
  files.

## 2026-07-06: Stage 2/3/4/5 Object Span Pipeline Update

Change under test:

- Stage 2 no longer merges object MWE spans.
- Stage 3 no longer runs object-MWE POS correction.
- Stage 4 now selects object spans inside noun chunks via OEWN noun lookup
  semantics and maps all selected-span tokens to the object mention.
- Stage 5 now uses raw surface labels for object fallback and does not attach
  action types.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast, pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('ast ok')"
.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage2_preprocess.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage3_annotate.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_stage5_canonicalize.py
```

Results:

- Syntax check passed: `ast ok`.
- Stage 2 tests passed: 7 tests.
- Stage 3 tests passed: 5 tests.
- Stage 4 tests passed: 6 tests.
- Stage 5 tests passed: 4 tests.
- Full stage test bundle passed:
  - command: `.\scripts\run_tests.ps1 --timeout-seconds 240 discover -s tests -p "test_stage*_*.py"`
  - result: 25 tests passed.
- Runtime OEWN sanity check:
  - command: synthetic Stage 3 record for `A dog.` through
    `extract_raw_concepts_from_stage3_record`
  - result: one object mention, `text=dog`,
    `selected_oewn_synset=oewn-02086723-n`.

Test environment note:

- Several tests no longer rely on Python's default temp directory because this
  Codex sandbox can deny writes under AppData or the OneDrive-backed repo
  junction. Tests now probe candidate temp roots before writing.

## 2026-07-06: Object MWE Dead Path Cleanup

Change under test:

- Removed the remaining Stage 2 object MWE loader, PhraseMatcher merge code,
  token extension, and Stage 3 object-MWE compatibility arguments.
- Removed `--object-mwes` from Stage 2, Stage 3, and fast benchmark CLIs.
- Removed the stale `object_mwe` token column from caption concept Markdown
  rendering.
- Updated IO/atomic tests to use the same writable-temp probing policy as the
  Stage tests.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast, pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 240 discover -s tests -p "test_*.py"
```

Results:

- Syntax check passed: `ast ok 12`.
- Full bounded unittest discovery passed:
  - command: `.\scripts\run_tests.ps1 --timeout-seconds 240 discover -s tests -p "test_*.py"`
  - result: 48 tests passed.

Compile note:

- `compileall src scripts tests` still fails in this sandbox because it writes
  `.pyc` files under the junction/OneDrive-backed repo path. Use AST parsing for
  syntax checks here unless pycache write permissions are fixed.

## 2026-07-06: Stage 4 Ambiguous Synset Gate

Issue found:

- The 20-caption sample output contained object mentions whose OEWN lookup had
  noun synsets but no selected synset:
  - `ambiguous_wn30_all_zero`: 21 mentions
  - `ambiguous_wn30_tie`: 2 mentions
- Stage 4 had accepted those spans because it checked `lookup.synsets` but did
  not require `lookup.selected_synset`.
- Stage 5/6 then continued through raw fallback, which violated the current
  object-synset policy.

Fix under test:

- Stage 4 now raises `Stage4SynsetAmbiguityError` when an object span has OEWN
  noun candidates but no selected synset.
- Missing OEWN lookup still means "do not create an object mention"; ambiguous
  lookup means "stop and resolve offline first."

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --raw-mentions outputs\case_reports_sentence20_current_after_ambiguous_gate\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current_after_ambiguous_gate\raw_edges.jsonl --summary outputs\case_reports_sentence20_current_after_ambiguous_gate\stage4_summary.jsonl
```

Results:

- Syntax check passed: `ast ok 2`.
- Stage 4 tests passed: 7 tests.
- Runtime 20-caption Stage 4 run now stops at the first unresolved ambiguity:
  - caption_id: `c90e89252ab6c4dde38fddfe360d0ce85dd31790e7ae838dc610bebb349f2b5f`
  - surface/query: `graphics`
  - tag: `ambiguous_wn30_all_zero`
  - candidate synsets: `oewn-07011408-n`, `oewn-03458929-n`

## 2026-07-06: GPIC Observed Object Inventory Runtime Boundary

Issue found:

- The active pipeline boundary was still easy to confuse with the earlier
  external source-label inventory work.
- COCO/LVIS/Objects365/OpenImages/Visual Genome source-label inventories are
  not active runtime input for GPIC caption extraction.
- Stage 4 must consume a GPIC observed object inventory built from Stage 3 GPIC
  records.

Fix under test:

- Added `scripts/build_gpic_observed_object_inventory.py`.
- Added `load_gpic_object_inventory()` and `GpicObjectInventoryLookup`.
- Added human-facing inventory queue fields:
  - `decision_status`
  - `decision_reason`
  - `objectness_gate` as evidence, not as the main status
- `scripts/run_stage4_extract_raw.py` and `scripts/benchmark_fast_pipeline.py`
  now require `--object-inventory` unless `--allow-runtime-oewn-lookup` is
  explicitly passed for probe/debug runs.
- Updated Stage 4 tests to verify inventory-driven object span selection.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 -- scripts\build_gpic_observed_object_inventory.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --output outputs\case_reports_sentence20_current\gpic_observed_object_inventory.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_object_inventory_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 90 -- scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory.tsv --raw-mentions outputs\case_reports_sentence20_current_after_gpic_inventory\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current_after_gpic_inventory\raw_edges.jsonl --summary outputs\case_reports_sentence20_current_after_gpic_inventory\stage4_summary.jsonl
```

Results:

- Syntax check passed: `ast ok 3`.
- Stage 4 tests passed: 9 tests.
- GPIC observed inventory builder over 20 captions:
  - caption_total: 20
  - noun_chunk_total: 263
  - inventory_rows: 194
  - decision_status_counts:
    - chosen: 105
    - needs_manual: 81
    - excluded: 8
  - decision_reason_counts:
    - selected_object_compatible: 105
    - manual_objectness_required: 66
    - manual_synset_required: 15
    - no_oewn_noun_synset: 8
  - plural common noun lookup examples:
    - `men`: observed surface `men`, selected query `man`, chosen
    - `windows`: observed surface `windows`, selected query `window`, chosen
    - `leaves`: observed surface `leaves`, selected query `leaf`, chosen
- Stage 4 with the generated GPIC inventory stopped as intended on the first
  row that is not chosen:
  - caption_id: `c90e89252ab6c4dde38fddfe360d0ce85dd31790e7ae838dc610bebb349f2b5f`
  - surface/query: `front`
  - decision_status: `needs_manual`
  - objectness_gate: `conditional`
  - tag: `selected_by_wn30_lemma_count`

Environment note:

- The active repo path is a junction to the OneDrive-backed repository.
- The sandboxed generated TSV write failed with `PermissionError` while opening
  a same-directory atomic temp file.
- The successful generated-artifact run used the same narrow bounded command
  with `require_escalated`, following the generated artifact policy in
  `AGENTS.md`.

## 2026-07-07: Joined Variant False Positive Guard

Issue found:

- Separator removal during OEWN lookup can create unrelated joined words:
  - `black shirt -> blackshirt`
  - `black top -> blacktop`
  - `A man -> aman`
- These should not be automatically counted as chosen object spans.

Fix under test:

- Multiword spans starting with function words such as `DET`, `ADP`, or `PRON`
  are skipped before OEWN probe. This makes `A man` fall through to `man`.
- If a span is found only through `joined_variant` or
  `last_word_morphy_after_joined_variant`, it is kept as `needs_manual` with
  `decision_reason=manual_joined_variant_required`.
- Exact and space-preserving MWE lookup can still become `chosen`.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 -- scripts\build_gpic_observed_object_inventory.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --output outputs\case_reports_sentence20_current\gpic_observed_object_inventory.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_object_inventory_summary.json
```

Results:

- Syntax check passed: `ast ok 3`.
- `git diff --check` passed for changed files.
- Stage 4 unit tests: 13 passed.
- Regenerated 20-caption GPIC observed object inventory:
  - `chosen`: 103
  - `needs_manual`: 83
  - `excluded`: 8
  - `manual_joined_variant_required`: 3
- Confirmed joined-variant manual rows:
  - `black shirt -> blackshirt`
  - `black top -> blacktop`
  - `seed pods -> seedpod`
- Confirmed determiner-start span behavior:
  - `man -> man`, chosen
  - `men -> man`, chosen

## 2026-07-07: Excluded Inventory Rows Counted As Status-Tagged Objects

Issue found:

- `excluded` rows were being treated like dropped rows during runtime object span
  selection.
- This made no-synset or non-object-status labels disappear from count output,
  even though the row had already been explicitly tagged as `excluded`.

Decision:

- `decision_status=excluded` is a quality/status tag, not a count gate.
- `decision_status=chosen` and `decision_status=excluded` both create object
  mentions.
- `decision_status=needs_manual` stops Stage 4 extraction.
- A row with a selected synset but unresolved canonical surface also stops
  Stage 4 extraction.
- Missing inventory rows are still not counted.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=['src/gpic_concepts_v1/stage4_extract_raw.py','tests/test_stage4_extract_raw.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
git diff --check -- src\gpic_concepts_v1\stage4_extract_raw.py tests\test_stage4_extract_raw.py docs\rules_v1.md docs\implementation_plan_v1.md docs\output_schema_v1.md
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_excluded_count_stage4_probe\raw_mentions.jsonl --raw-edges C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_excluded_count_stage4_probe\raw_edges.jsonl --summary C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_excluded_count_stage4_probe\stage4_summary.jsonl
```

Results:

- Syntax check passed: `ast ok 2`.
- `git diff --check` passed for changed files.
- Stage 4 unit tests: 14 passed.
- Added regression coverage for an `excluded` inventory row with no OEWN synset:
  - object mention is created
  - `decision_status=excluded` is preserved in `source_detail`
  - `has_oewn_noun_synset=false` is preserved in `source_detail`
- 20-caption Stage 4 probe with the redecided inventory completed:
  - raw mentions: 510
  - object mentions: 263

## 2026-07-07: Canonical Ambiguity Gate

Issue found:

- Canonical enrichment could be run even when `decision_status=needs_manual`
  rows were still present, which violated the intended order:
  synset/objectness manual resolution first, canonical surface selection second.
- Canonical enrichment could leave unresolved canonical rows in the ambiguous
  TSV while still exiting successfully.
- Stage 4 also needed to reject rows with a selected synset but empty
  `canonical_surface`.

Fix:

- `enrich_gpic_inventory_canonical.py` now exits before OEWN loading if any
  `needs_manual` row remains.
- `enrich_gpic_inventory_canonical.py` now writes output, ambiguous TSV, and
  summary first, then exits nonzero if `canonical_ambiguous_rows > 0`.
- Stage 4 raises `Stage4SynsetAmbiguityError` for selected-synset rows whose
  canonical surface is unresolved.

Verification:

- Syntax check passed for:
  - `src/gpic_concepts_v1/stage4_extract_raw.py`
  - `scripts/enrich_gpic_inventory_canonical.py`
  - `tests/test_stage4_extract_raw.py`
- `git diff --check` passed for changed gate files and docs.
- `test_enrich_gpic_inventory_canonical.py`: 3 tests passed.
- Real sentence 101-200 inventory canonical precondition check:
  - status: `blocked_needs_manual_before_canonical`
  - needs_manual_rows: 212
  - confirmed no output TSV was written before failure
- `test_stage4_extract_raw.py`: 15 tests passed.
  - object decision status counts:
    - `chosen`: 244
    - `excluded`: 19
  - first excluded examples counted as object mentions:
    - `them`
    - `another`
    - `center-right`
    - `hours`
    - `"J.B. HUNT Intermodal."`

## 2026-07-07: Selected OEWN Parent Evidence Propagation

Decision under test:

- Once offline/manual synset resolution produces final `selected_oewn_synset`,
  parent evidence must be filled from that selected synset.
- Parent evidence means every immediate OEWN hypernym synset ID, not one chosen
  parent lemma.
- Stage 5 should attach those parent synset IDs as object `parent_concepts`.
- Stage 6 should expose parent columns in object, role, relation, and object
  co-occurrence count tables.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage5_canonicalize.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage6_export_counts.py
.\scripts\run_python.ps1 scripts\enrich_gpic_inventory_parents.py --input outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --output outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_object_inventory_parent_summary.json
.\scripts\run_python.ps1 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --summary outputs\case_reports_sentence20_current\stage4_summary.jsonl
.\scripts\run_python.ps1 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --lexicon-dir resources\lexicons --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges.jsonl --summary outputs\case_reports_sentence20_current\stage5_summary.jsonl
.\scripts\run_python.ps1 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges.jsonl --output-dir outputs\case_reports_sentence20_current\stage6 --summary outputs\case_reports_sentence20_current\stage6_summary.jsonl
```

Results:

- Syntax check passed: `ast ok 9`.
- Stage 4 tests: 14 passed.
- Stage 5 tests: 4 passed.
- Stage 6 tests: 2 passed.
- Parent enrichment summary:
  - rows: 194
  - selected_synset_missing_rows: 10
  - parent_filled_rows: 184
  - parent_empty_rows: 0
- Re-run summary:
  - Stage 4 object mentions: 263
  - Stage 5 object mentions with parent: 251
  - Stage 6 `object_counts.tsv` includes `parent_concepts`.
  - Stage 6 relation/object co-occurrence count tables include source/target
    parent concept columns.

## 2026-07-07: GPIC Observed Canonical Surface Propagation

Decision under test:

- Selected synset alone is not enough; object canonical surface must also be
  chosen by the offline canonical rule.
- Stage 5 should use inventory `canonical_surface` as object canonical label
  and mark `canonical_source=gpic_observed_inventory`.
- If canonical remains ambiguous, the inventory row keeps blank
  `canonical_surface` and the row appears in the canonical ambiguous TSV.

Commands:

```powershell
.\scripts\run_python.ps1 scripts\enrich_gpic_inventory_canonical.py --input outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --output outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --ambiguous-output outputs\case_reports_sentence20_current\gpic_observed_object_inventory_canonical_ambiguous.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_object_inventory_canonical_summary.json
.\scripts\run_python.ps1 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --summary outputs\case_reports_sentence20_current\stage4_summary.jsonl
.\scripts\run_python.ps1 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --lexicon-dir resources\lexicons --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges.jsonl --summary outputs\case_reports_sentence20_current\stage5_summary.jsonl
.\scripts\run_python.ps1 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges.jsonl --output-dir outputs\case_reports_sentence20_current\stage6 --summary outputs\case_reports_sentence20_current\stage6_summary.jsonl
```

Results:

- Initial canonical enrichment exposed one bug:
  - `sun` and `Sun` tied on WN3 count.
  - The implementation used case-insensitive observed-surface matching, leaving
    `sun` ambiguous.
  - Fixed to use exact observed surface display match for this rule step.
- Current canonical enrichment:
  - rows: 194
  - selected_synset_missing_rows: 10
  - canonical_selected_rows: 184
  - canonical_ambiguous_rows: 0
- Stage 5 after re-run:
  - `canonical_source_counts`: `gpic_observed_inventory=251`, `raw_fallback=259`
- Bounded unit tests:
  - `test_atomic_io.py`: 3 passed
  - `test_stage4_extract_raw.py`: 14 passed
  - `test_stage5_canonicalize.py`: 4 passed

## 2026-07-07: Sentence 101-200 Manual Resolution End-to-End Check

Decision under test:

- Canonical enrichment must not run before `needs_manual` rows are resolved.
- After manual resolution removes `needs_manual`, parent/canonical enrichment should run.
- Stage 4 should accept `chosen` and `excluded` inventory rows, but still block `needs_manual`.
- Stage 5/6 should produce count tables from the manual-resolved inventory.

Inputs:

- `outputs/case_reports_sentence100_0101_0200_current/stage3_records.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved.tsv`

Manual resolved inventory validation:

- rows: 567
- `chosen`: 514
- `excluded`: 53
- `needs_manual`: 0
- corrected invalid manual helmet synset:
  - `oewn-03521675-n` -> `oewn-03518281-n`
- corrected missing selected synset for `white feathers`:
  - selected query `white feather` -> `feather`
  - selected synset blank -> `oewn-89570581-n`

Parent enrichment result:

- output: `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved_parents.tsv`
- parent_filled_rows: 514
- parent_lookup_error_rows: 0
- selected_synset_missing_rows: 53

Canonical enrichment result:

- output: `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv`
- canonical_selected_rows: 514
- canonical_ambiguous_rows: 0
- canonical_lookup_error_rows: 0
- selected_synset_missing_rows: 53

Stage 4 result:

- raw mentions: 2242
- raw edges: 1224
- objects: 1169
- attributes: 604
- actions: 432
- quantities: 37
- relations: 197

Stage 5 result:

- canonical mentions: 2242
- canonical edges: 1224
- canonical_source_counts:
  - `gpic_observed_inventory`: 1065
  - `raw_fallback`: 1177

Stage 6 result:

- output: `outputs/case_reports_sentence100_0101_0200_current/counts_manual_resolved`
- fact_total: 21833
- table row counts:
  - object_counts.tsv: 504
  - attribute_counts.tsv: 253
  - object_attribute_pair_counts.tsv: 537
  - action_counts.tsv: 200
  - agent_patient_pair_counts.tsv: 345
  - relation_triple_counts.tsv: 182
  - object_cooccurrence_pair_counts.tsv: 16324

## 2026-07-07: Manual Resolution Gate Regression

Decision under test:

- A final manual-resolved object inventory row must be either `chosen` or
  `excluded`.
- Any other explicit decision status is treated as pending manual work.
- If a `chosen` row changes the surface/head form but has no
  `selected_oewn_synset`, parent/canonical enrichment must stop before OEWN
  loading.

Representative case:

- `white feathers`
  - bad pending state:
    - `decision_status=chosen`
    - `selected_query=white feather`
    - `selected_oewn_synset=` blank
    - `canonical_surface=feather`
  - expected gate:
    - `surface_correction_requires_synset_lookup`

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast,pathlib; files=[...]; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8-sig'), filename=f) for f in files]; print('ast ok', len(files))"
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_inventory_validation.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_enrich_gpic_inventory_canonical.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_enrich_gpic_inventory_parents.py
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
```

Results:

- AST parse: `ast ok 7`
- `test_inventory_validation.py`: 4 passed
- `test_enrich_gpic_inventory_canonical.py`: 4 passed
- `test_enrich_gpic_inventory_parents.py`: 1 passed
- `test_stage4_extract_raw.py`: 15 passed

## 2026-07-08: Attribute Manual No-Synset Chosen Normalization

Decision under test:

- Attribute manual feedback with `decision_status=chosen` but blank
  `selected_oewn_synset` is not a valid chosen row.
- Before attribute canonical enrichment, that row is normalized to
  `decision_status=excluded`.
- `excluded` is a resolved manual status, but it is not a canonical decision.
- Every `excluded` row clears canonical columns and receives
  `canonical_selection_tag=not_applicable_excluded`.
- Feedback-provided `canonical_surface` and `manual_*` canonical tags are ignored
  for non-excluded selected-synset rows; canonical enrichment recomputes them.

Representative case:

- `TYR`
  - previous state:
    - `decision_status=chosen`
    - `selected_oewn_synset=` blank
    - `canonical_surface=tyr`
    - `canonical_selection_tag=manual_surface_canonical`
  - expected state:
    - `decision_status=excluded`
    - `decision_reason=manual_excluded_oewn_false_positive_brand_modifier_no_synset`
    - `canonical_surface=` blank
    - `canonical_selection_tag=not_applicable_excluded`

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_enrich_gpic_attribute_inventory_canonical.py
.\scripts\run_python.ps1 scripts\enrich_gpic_attribute_inventory_canonical.py --input outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_manual_resolved.tsv --output outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_canonical.tsv --ambiguous-output outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_canonical_ambiguous.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_canonical_summary.json
```

Results:

- `test_enrich_gpic_attribute_inventory_canonical.py`: 6 passed
- 20-caption attribute canonical enrichment:
  - rows: 101
  - excluded_not_applicable_rows: 4
  - selected_synset_missing_rows: 0
  - canonical_selected_rows: 97
  - canonical_ambiguous_rows: 0
  - manual_surface_canonical rows: 0
  - canonical tag counts:
    - `selected_single_observed_variant_matched_synset_lemma`: 95
    - `selected_by_wn30_lemma_count_unique_positive_max`: 2
    - `not_applicable_excluded`: 4
  - status counts: `chosen=97`, `excluded=4`
  - all excluded rows: `canonical_selection_tag=not_applicable_excluded`

## 2026-07-08: Attribute Type Lexicon Export and Count Propagation

Decision under test:

- Typed attribute inventory is converted into a Stage 5 lexicon bundle.
- `excluded` rows never export canonical synonyms, even if feedback supplied a
  canonical value.
- `excluded` rows may still export `attribute_type` against the raw-fallback
  key for audit/filtering.
- Stage 6 object-attribute pair counts should carry `attribute_type`.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_export_attribute_stage5_lexicons.py
.\scripts\run_python.ps1 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv --output-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_typed --base-lexicon-dir resources\lexicons --summary outputs\case_reports_sentence20_current\attribute_stage5_lexicon_export_summary.json
.\scripts\run_python.ps1 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_typed --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attr_typed.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attr_typed.jsonl --summary outputs\case_reports_sentence20_current\stage5_attr_typed_summary.jsonl
.\scripts\run_python.ps1 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attr_typed.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attr_typed.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attr_typed --summary outputs\case_reports_sentence20_current\stage6_attr_typed_summary.jsonl
```

Results:

- `test_export_attribute_stage5_lexicons.py`: 1 passed.
- Attribute lexicon export:
  - inventory rows: 101
  - chosen synonym rows added: 97
  - attribute type rows: 99
  - excluded type rows: 4
  - ignored excluded canonical rows: 0
- Stage 5 typed run:
  - canonical mentions: 510
  - canonical edges: 289
  - canonical source counts: `gpic_observed_inventory=251`, `lexicon=128`, `raw_fallback=131`
- Stage 6 typed run:
  - fact total: 4830
  - object-attribute pair rows: 129
  - object-attribute pair rows with `attribute_type`: 129
  - excluded attributes remain raw fallback:
    - `Several -> several`, `canonical_source=raw_fallback`
    - `entire -> entire`, `canonical_source=raw_fallback`
    - `overall -> overall`, `canonical_source=raw_fallback`
    - `TYR -> tyr`, `canonical_source=raw_fallback`

## 2026-07-08: Invalidated Attribute Export Test Runner Attempt

Decision under test:

- Attribute inventory `decision_status` should use only `chosen`, `excluded`,
  and `needs_manual`.
- OEWN lookup failure should be represented by reason/metadata, not by a fourth
  `decision_status=no_synset`.

Invalid command:

```powershell
.\scripts\run_python.ps1 -m unittest tests.test_export_attribute_stage5_lexicons
```

Result:

- Invalidated. This command was the wrong runner for repository validation.
- It repeated the temp/PermissionError failure pattern and was interrupted by
  the user after it remained visible for many minutes.
- The result must not be used as pass/fail evidence.

Root-cause record:

- See `docs/test_runner_incident_log_v1.md`.

## 2026-07-08: 20 Caption Attribute-Current Report Regeneration

Decision under test:

- Attribute type export is deferred: Stage 5 lexicon bundle should carry
  attribute canonical synonyms but no `attribute_type` rows.
- Stage 4 object span selection should not consume modifier tokens when the
  selected object core is the head, so `black top`, `black shirt`, and
  `blue wall` still produce color attributes.

Commands:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --summary outputs\case_reports_sentence20_current\stage4_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv --output-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_current --base-lexicon-dir resources\lexicons --summary outputs\case_reports_sentence20_current\attribute_stage5_lexicon_export_summary_current.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_current --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_current --summary outputs\case_reports_sentence20_current\stage6_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_current\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_current.md --start 0 --limit 20 --max-object-pairs-per-caption 40
```

Execution note:

- The first sandboxed attempts hit `PermissionError` because
  `C:\Users\rlath\Documents\Codex\gpic-explainable-link` is a junction to the
  OneDrive repo path. The successful rerun used the bounded
  `run_script_with_timeout.py` wrapper with sandbox escalation.

Results:

- Stage 4:
  - mentions: 513
  - edges: 292
  - `has_attribute`: 138
- Attribute lexicon export:
  - `attribute_synonym_rows`: 97
  - `attribute_type_rows`: 0
  - `attribute_type_rows_deferred`: 101
- Stage 5:
  - canonical mentions: 513
  - canonical edges: 292
  - canonical source counts:
    `gpic_observed_inventory=251`, `lexicon=131`, `raw_fallback=131`
- Stage 6:
  - fact total: 4833
  - `has_attribute`: 138
  - object-attribute pair rows: 132
- Markdown report:
  - `outputs/case_reports_sentence20_current/caption_to_concept_cases_0001_0020_attribute_current.md`

Validation:

- `outputs/case_reports_sentence20_current/stage5_lexicons_attribute_current/attribute_types.tsv`
  contains only the header row.
- `rg attribute_type` over the current Markdown, Stage 5 JSONL, and Stage 6
  output returned no matches.
- Expected restored pairs are present:
  - `top` + `black`
  - `shirt` + `black`
  - `headphone` + `black`
  - `wall` + `blue`

## 2026-07-08: Attribute Modifier `nmod` Recall Expansion

Decision under test:

- R11.1 and R13 attribute modifier dependencies include `nmod` in addition to
  `amod` and `compound`.
- `conj` is intentionally not included in this change.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_build_gpic_observed_attribute_inventory.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --summary outputs\case_reports_sentence20_current\stage4_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_current --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_current --summary outputs\case_reports_sentence20_current\stage6_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_current.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_current\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_current.md --start 0 --limit 20 --max-object-pairs-per-caption 40
```

Results:

- `test_stage4_extract_raw.py`: 17 passed.
- `test_build_gpic_observed_attribute_inventory.py`: 6 passed.

## 2026-07-09: 20-Caption Rerun With OEWN-Based Phrasal Action Selection

Decision under test:

- R15 can select OEWN-backed phrasal action spans.
- R17 can use the direct `pobj` of a consumed phrasal-action ADP as patient.
- R18 excludes ADP tokens consumed by selected phrasal actions.
- Corrected on 2026-07-09: action synset ambiguity is not pass-through
  metadata. The generated `attribute_action_current` files from this run are
  invalid as formal output because Stage 4 should have stopped on action
  `needs_manual`.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_action_current.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_action_current.jsonl --summary outputs\case_reports_sentence20_current\stage4_action_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_action_current.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_action_current.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_current --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_current.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_action_current_summary.jsonl --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_current.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_action_current --summary outputs\case_reports_sentence20_current\stage6_attribute_action_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_current.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_current.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_action_current\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_action_current.md --start 0 --limit 20 --max-object-pairs-per-caption 40
```

Results:

- `test_stage4_extract_raw.py`: 19 passed.
- Stage 4:
  - mentions: 516
  - edges: 307
  - actions: 104
  - event roles: 108
  - relations: 50
- Stage 5:
  - canonical mentions: 516
  - canonical edges: 307
  - canonical source counts:
    `gpic_observed_inventory=251`, `lexicon=131`, `raw_fallback=134`
- Stage 6:
  - fact total: 4848
  - action events: 104
  - event roles: 108
  - relation facts: 50
  - action count rows: 82
  - agent/patient pair rows: 105
- Phrasal action spans selected: 13.
- Markdown report:
  - `outputs/case_reports_sentence20_current/caption_to_concept_cases_0001_0020_attribute_action_current.md`

Inspection note:

- Some selected phrasal action spans look useful, e.g. `stand in`, `run on`,
  `cascade down`, `cling to`.
- Some spans need review as possible false positives, e.g. `frame In`.
- Stage 4:
  - mentions: 516
  - edges: 295
  - `has_attribute`: 141
- Stage 5:
  - canonical mentions: 516
  - canonical edges: 295
  - canonical source counts:
    `gpic_observed_inventory=251`, `lexicon=131`, `raw_fallback=134`
- Stage 6:
  - fact total: 4836
  - `has_attribute`: 141
  - object-attribute pair rows: 135

Validation:

- `outputs/case_reports_sentence20_current/stage6_attribute_current/object_attribute_pair_counts.tsv`
  contains `object_attribute_pair:jersey:maroon`.
- The 20-caption Markdown contains `jersey (jerseys) has_attribute maroon`.
- `yellow` in `maroon and yellow jerseys` is still not attached to `jersey`
  because `yellow.dep_ == conj`, and `conj` is outside this approved change.

## 2026-07-08: Sentence 101-200 Attribute-Current Report Regeneration

Decision under test:

- Re-run the 100-caption sentence 101-200 report with the current Stage 4
  attribute modifier dependency set: `amod`, `compound`, `nmod`.
- Do not rebuild the 100-caption attribute manual inventory yet.
- Use the existing manual-resolved object inventory for object
  canonicalization and parent concepts.
- Attribute canonicalization remains raw fallback for this 100-caption run
  because the base `resources/lexicons/attribute_synonyms.tsv` has only a
  header row.

Commands:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv --raw-mentions outputs\case_reports_sentence100_0101_0200_current\raw_mentions_attribute_current.jsonl --raw-edges outputs\case_reports_sentence100_0101_0200_current\raw_edges_attribute_current.jsonl --summary outputs\case_reports_sentence100_0101_0200_current\stage4_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence100_0101_0200_current\raw_mentions_attribute_current.jsonl --raw-edges outputs\case_reports_sentence100_0101_0200_current\raw_edges_attribute_current.jsonl --lexicon-dir resources\lexicons --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current.jsonl --summary outputs\case_reports_sentence100_0101_0200_current\stage5_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current.jsonl --output-dir outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current --summary outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_caption_concept_md.py --sentence-rows outputs\case_reports_sentence100_0101_0200_current\sentence_rows_0101_0200.jsonl --stage3-records outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current.jsonl --facts outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current\facts.jsonl --output outputs\case_reports_sentence100_0101_0200_current\caption_to_concept_cases_0101_0200_attribute_current.md --start 0 --limit 100 --max-object-pairs-per-caption 40
```

Results:

- Stage 4:
  - mentions: 2252
  - edges: 1234
  - `has_attribute`: 614
- Stage 5:
  - canonical mentions: 2252
  - canonical edges: 1234
  - canonical source counts:
    `gpic_observed_inventory=1065`, `raw_fallback=1187`
- Stage 6:
  - fact total: 21843
  - `has_attribute`: 614
  - object-attribute pair rows: 547
  - object co-occurrence pair facts: 19008
- Markdown report:
  - `outputs/case_reports_sentence100_0101_0200_current/caption_to_concept_cases_0101_0200_attribute_current.md`

Validation:

- `rg attribute_type` over the 100-caption Markdown, Stage 5 JSONL, and Stage 6
  output returned no matches.

## 2026-07-08: Sentence 101-200 Attribute Inventory Status Refresh

Issue:

- The existing 100-caption attribute inventory summary still contained the
  legacy status `decision_status=no_synset`.
- Current rules use only `chosen`, `needs_manual`, and `excluded` as the main
  queue status. Missing OEWN attribute synsets are represented as
  `decision_status=chosen` with
  `decision_reason=no_oewn_attribute_synset`.

Command:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_gpic_observed_attribute_inventory.py --input outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv --output C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_attr_inventory_probe_100.tsv --summary C:\Users\Public\Documents\ESTsoft\CreatorTemp\gpic_attr_inventory_probe_100_summary.json
```

Result:

- Probe regenerated successfully outside the sandbox after the sandboxed run
  failed to open the OEWN sqlite database.
- Current status counts:
  - `chosen`: 161
  - `needs_manual`: 96
  - `no_synset`: 0
- Current copied outputs:
  - `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_attribute_inventory_current.tsv`
  - `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_attribute_inventory_current_needs_manual.tsv`

Interpretation:

- The old `gpic_observed_attribute_inventory.tsv` in this folder is a stale
  snapshot for status naming.
- Use the `_current` files for the next manual attribute-resolution pass.

## 2026-07-08: Formal Stage4 and Stage5 Inventory Gate Enforcement

Decision under test:

- Stage 4 runner must block before raw extraction when the object inventory has
  pending rows or a selected synset without canonical surface.
- Stage 5 runner must require a resolved attribute inventory for formal output.
- Stage 5 runner must block before canonicalization when the attribute inventory
  has pending rows or a selected synset without canonical surface.
- Stage 5 unresolved runs must be explicit preview runs.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_inventory_validation.py
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_formal_inventory_gates.py
.\scripts\run_python.ps1 -c "import ast, pathlib; files=['src/gpic_concepts_v1/inventory_validation.py','scripts/run_stage4_extract_raw.py','scripts/run_stage5_canonicalize.py','tests/test_inventory_validation.py','tests/test_formal_inventory_gates.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8'), filename=f) for f in files]; print('ast ok', len(files))"
```

Results:

- `test_inventory_validation.py`: 5 passed.
- `test_formal_inventory_gates.py`: 6 passed.
- AST parse: `ast ok 5`.
- Actual 100-caption Stage 5 gate probe with
  `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_attribute_inventory_current.tsv`
  stopped before canonicalization:
  - status: `blocked_attribute_inventory_before_stage5`
  - rows: 257
  - blocked_rows: 231
  - first blocker reasons include `selected_synset_missing_canonical_surface`

Interpretation:

- Formal Stage 4/5 runners now stop before incomplete inventories can be
  promoted into formal Stage 5/6/Markdown outputs.
- Stage 5 preview output is still possible only with
  `--allow-unresolved-attribute-preview`.

## 2026-07-08: Sentence 101-200 Attribute Manual Resolution Applied

Decision under test:

- The user-provided 96-row attribute manual resolution file should replace the
  96 pending rows in the full 257-row sentence 101-200 attribute inventory.
- After canonical enrichment, the full attribute inventory should have no
  pending manual rows and no selected synset rows missing canonical surface.
- The resulting Stage 5 run should pass the formal attribute inventory gate.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_apply_attribute_manual_resolution.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 60 scripts\apply_attribute_manual_resolution.py --full-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current.tsv --resolved-subset C:\Users\rlath\Downloads\gpic_observed_attribute_inventory_current_resolved.tsv --manual-decisions C:\Users\rlath\Downloads\gpic_observed_attribute_inventory_current_manual_decisions.tsv --output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved.tsv --resolved-copy outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_subset.tsv --manual-decisions-copy outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_decisions.tsv --summary outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolution_apply_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\enrich_gpic_attribute_inventory_canonical.py --input outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved.tsv --output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv --ambiguous-output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical_ambiguous.tsv --summary outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv --output-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_current_manual_resolved --base-lexicon-dir resources\lexicons --summary outputs\case_reports_sentence100_0101_0200_current\attribute_stage5_lexicon_export_summary_current_manual_resolved.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence100_0101_0200_current\raw_mentions_attribute_current.jsonl --raw-edges outputs\case_reports_sentence100_0101_0200_current\raw_edges_attribute_current.jsonl --lexicon-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_current_manual_resolved --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current_manual_resolved.jsonl --summary outputs\case_reports_sentence100_0101_0200_current\stage5_attribute_current_manual_resolved_summary.jsonl --attribute-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current_manual_resolved.jsonl --output-dir outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current_manual_resolved --summary outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current_manual_resolved_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_caption_concept_md.py --sentence-rows outputs\case_reports_sentence100_0101_0200_current\sentence_rows_0101_0200.jsonl --stage3-records outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_current_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_current_manual_resolved.jsonl --facts outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_current_manual_resolved\facts.jsonl --output outputs\case_reports_sentence100_0101_0200_current\caption_to_concept_cases_0101_0200_attribute_current_manual_resolved.md --start 0 --limit 100 --max-object-pairs-per-caption 40
.\scripts\run_tests.ps1 --timeout-seconds 180 discover -s tests -p test_enrich_gpic_attribute_inventory_canonical.py
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_export_attribute_stage5_lexicons.py
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_formal_inventory_gates.py
```

Results:

- Manual resolution overlay:
  - full rows: 257
  - resolved rows: 96
  - merged status counts: `chosen=257`
  - merged selected synset rows: 231
  - merged empty canonical surface rows before enrichment: 257
  - manual canonical fields from the user-provided TSV are not copied into the
    full resolved inventory.
- Canonical enrichment:
  - rows: 257
  - canonical selected rows: 231
  - selected synset missing rows: 26
  - canonical ambiguous rows: 0
  - canonical lookup error rows: 0
- Stage 5 lexicon export:
  - attribute synonym rows: 231
  - attribute type rows: 0
- Stage 5 formal output:
  - `formal_attribute_inventory_gate=True`
  - canonical mentions: 2252
  - canonical edges: 1234
  - canonical source counts:
    `gpic_observed_inventory=1065`, `lexicon=587`, `raw_fallback=600`
- Stage 6:
  - fact total: 21843
  - `has_attribute`: 614
  - object-attribute pair rows: 547
  - object co-occurrence pair rows: 16324
- Markdown report:
  - `outputs/case_reports_sentence100_0101_0200_current/caption_to_concept_cases_0101_0200_attribute_current_manual_resolved.md`
- Tests:
  - `test_apply_attribute_manual_resolution.py`: 2 passed.
  - `test_enrich_gpic_attribute_inventory_canonical.py`: 6 passed.
  - `test_export_attribute_stage5_lexicons.py`: 1 passed.
  - `test_formal_inventory_gates.py`: 6 passed.
  - AST parse: `ast ok 5`.
- Additional verification after clearing manual canonical overlay:
  - `manual_surface_preserved` count is 0 in:
    - `gpic_observed_attribute_inventory_current_manual_resolved.tsv`
    - `gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv`
    - exported `attribute_synonyms.tsv`
  - selected synset rows missing canonical surface after enrichment: 0

Interpretation:

- The provided manual decisions are now applied to the full 100-caption
  attribute inventory.
- User-provided canonical fields are ignored at overlay time; canonical surfaces
  are recomputed by `enrich_gpic_attribute_inventory_canonical.py`.
- The formal Stage 5 gate now passes for this 100-caption run.
- Attribute type remains inactive in Stage 5/6 by current v1 rule.

## 2026-07-09: Action `needs_manual` Gate Correction

Decision under test:

- A selected R15 action span with `decision_status=needs_manual` must stop
  Stage 4.
- The previous 20-caption `attribute_action_current` outputs were produced
  before this correction and must not be treated as formal caption-to-concept
  output.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_action_gate_probe.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_action_gate_probe.jsonl --summary outputs\case_reports_sentence20_current\stage4_action_gate_probe_summary.jsonl
```

Results:

- `test_stage4_extract_raw.py`: 19 tests passed.
- The 20-caption Stage 4 probe stopped before writing raw output files.
- First blocker:
  - action surface: `marked`
  - lookup query: `mark`
  - `decision_status`: `needs_manual`
  - selection tag: `ambiguous_wn30_tie`

Interpretation:

- Stage 4 no longer lets unresolved action synset decisions pass into raw
  mentions, Stage 5, Stage 6, or Markdown reports.
- The failed probe did not create:
  - `raw_mentions_action_gate_probe.jsonl`
  - `raw_edges_action_gate_probe.jsonl`
  - `stage4_action_gate_probe_summary.jsonl`

## 2026-07-09: 20-Caption Action Inventory Manual File Generated

Decision under test:

- Build the offline action inventory file needed before formal Stage 4 can
  proceed with OEWN-backed action spans.
- Provide a `needs_manual` subset TSV for manual resolution.

Commands:

```powershell
.\scripts\run_python.ps1 -c "import ast, pathlib; path=pathlib.Path('scripts/build_gpic_observed_action_inventory.py'); ast.parse(path.read_text(encoding='utf-8'), filename=str(path)); print('ast ok')"
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_gpic_observed_action_inventory.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory.tsv --needs-manual-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_needs_manual.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_summary.json

## 2026-07-09: Sentence-20 Action Manual Resolution And Formal Stage 4 Gate

Scope:

- Applied the 8 user-provided action `needs_manual` decisions for the
  sentence-20 current sample.
- Added a resolved action inventory input to Stage 4.
- Regenerated Stage 4/5/6 and Markdown report under `action_manual_resolved`
  output names.

Manual decisions:

- `deepening -> oewn-00226992-v`
- `depicts -> oewn-01690851-v`
- `marked -> oewn-01591414-v`
- `shimmering -> oewn-02769408-v`
- `shining -> oewn-02771882-v`, selected query `shine`
- `sits in -> oewn-02619175-v`, known false positive note preserved
- `slopes -> oewn-02040935-v`, selected query `slope`
- `stands out -> oewn-02680375-v`

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_apply_action_manual_resolution.py"
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_stage4_extract_raw.py"
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_formal_inventory_gates.py"
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\apply_action_manual_resolution.py --full-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory.tsv --manual-decisions outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_decisions.tsv --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --resolved-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved_subset.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolution_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --action-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_action_manual_resolved.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_action_manual_resolved.jsonl --summary outputs\case_reports_sentence20_current\stage4_action_manual_resolved_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_action_manual_resolved.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_action_manual_resolved.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_current --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_manual_resolved.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_action_manual_resolved_summary.jsonl --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_manual_resolved.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_action_manual_resolved --summary outputs\case_reports_sentence20_current\stage6_attribute_action_manual_resolved_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_manual_resolved.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_manual_resolved.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_action_manual_resolved\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_action_manual_resolved.md --start 0 --limit 20 --max-object-pairs-per-caption 40
.\scripts\run_python.ps1 -m compileall scripts src tests
```

Results:

- `test_apply_action_manual_resolution.py`: 2 passed.
- `test_stage4_extract_raw.py`: 22 passed.
- `test_formal_inventory_gates.py`: 8 passed.
- compileall passed for changed scripts/src/tests.
- Manual overlay status counts:
  - before: `chosen=71`, `needs_manual=8`, `raw_fallback=3`
  - after: `chosen=79`, `raw_fallback=3`
- Stage 4 manual-resolved summary:
  - `raw_mention_total=516`
  - `raw_edge_total=307`
  - mention counts: `action=104`, `attribute=141`, `object=263`, `quantity=8`
- Stage 5 manual-resolved summary:
  - `canonical_mention_total=516`
  - `canonical_edge_total=307`
  - `formal_attribute_inventory_gate=True`
- Stage 6 manual-resolved summary:
  - `fact_total=4848`
  - `action_counts.tsv` rows: 82
- Sanity note:
  - Stage 4 action mentions carry the manual `selected_query` in `lemma` and
    source metadata.
  - Stage 5 action counts still use the existing R22 action synonym path. The
    action inventory canonical export is not implemented in this snapshot, so
    several action count labels remain surface forms such as `deepening` and
    `depicts`.

Generated artifacts:

- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_manual_decisions.tsv`
- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_manual_resolved.tsv`
- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_manual_resolved_subset.tsv`
- `outputs/case_reports_sentence20_current/raw_mentions_action_manual_resolved.jsonl`
- `outputs/case_reports_sentence20_current/raw_edges_action_manual_resolved.jsonl`
- `outputs/case_reports_sentence20_current/canonical_mentions_attribute_action_manual_resolved.jsonl`
- `outputs/case_reports_sentence20_current/canonical_edges_attribute_action_manual_resolved.jsonl`
- `outputs/case_reports_sentence20_current/stage6_attribute_action_manual_resolved/`
- `outputs/case_reports_sentence20_current/caption_to_concept_cases_0001_0020_attribute_action_manual_resolved.md`
```

Results:

- AST parse: `ast ok`.
- Full action inventory:
  - `outputs/case_reports_sentence20_current/gpic_observed_action_inventory.tsv`
  - rows: 82
- Manual subset:
  - `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_needs_manual.tsv`
  - rows: 14
- Summary:
  - `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_summary.json`
  - caption_total: 20
  - verb_token_total: 104
  - decision_status_counts: `chosen=68`, `needs_manual=14`
  - decision_reason_counts:
    - `selected_verb_synset=65`
    - `manual_action_synset_required=14`
    - `no_oewn_verb_synset=3`

Interpretation:

- The generated `needs_manual` TSV is the file to resolve before rerunning
  formal Stage 4 with action inventory support.
- `compileall` was not used as validation because it attempted to write
  `scripts/__pycache__` and hit a local `PermissionError`; the AST check avoids
  bytecode writes.

Correction:

- The first generated action inventory incorrectly wrote no-synset raw fallback
  action rows as `decision_status=chosen`.
- Correct status for no-synset action fallback is `decision_status=raw_fallback`
  because selected synset is absent.

## 2026-07-09: Action Verb Exact Surface Filter And Morphy Ambiguity

Decision under test:

- R15 action lookup must not treat OEWN's internal morphology as an exact
  surface hit.
- R15 action lookup must not auto-select the first Morphy candidate when
  multiple Morphy queries produce OEWN verb hits.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_stage4_extract_raw.py
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_gpic_observed_action_inventory.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory.tsv --needs-manual-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_needs_manual.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_summary.json
```

Results:

- `test_stage4_extract_raw.py`: 21 tests passed in 2.414 seconds.
- Regenerated 20-caption action inventory summary:
  - inventory_rows: 82
  - verb_token_total: 104
  - decision_status_counts: `chosen=71`, `needs_manual=8`,
    `raw_fallback=3`
  - decision_reason_counts:
    - `selected_verb_synset=71`
    - `manual_action_synset_required=6`
    - `manual_action_morphy_required=2`
    - `no_oewn_verb_synset=3`

Representative row check:

- `lit -> light`, `lying -> lie`, `made -> make`, `sitting -> sit`,
  `splitting -> split`, and `worn -> wear` now use
  `selected_lookup_case=verb_head_morphy`.
- `shining -> shin|shine` and `slopes -> slop|slope` now use
  `selected_lookup_case=verb_head_morphy_ambiguous` and
  `decision_status=needs_manual`.

Interpretation:

- Inflected action surfaces no longer become artificial raw-surface
  `needs_manual` rows when OEWN internally returns base-lemma verb synsets.
- Multiple Morphy verb-hit queries are now explicit manual decisions rather
  than hidden automatic choices.

## 2026-07-10: Sentence-20 Action Canonical Inventory Build

Decision under test:

- After action synset `needs_manual` rows are resolved, the next offline step is
  action canonical inventory build, not runtime Stage 4/5 execution.
- Canonical inventory must stop if canonical selection creates new manual
  blockers.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_enrich_gpic_action_inventory_canonical.py"
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\enrich_gpic_action_inventory_canonical.py --input outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical.tsv --ambiguous-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical_ambiguous.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical_summary.json
.\scripts\run_python.ps1 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['scripts/enrich_gpic_action_inventory_canonical.py','tests/test_enrich_gpic_action_inventory_canonical.py']]; print('ast ok')"
```

Results:

- `test_enrich_gpic_action_inventory_canonical.py`: 3 tests passed.
- AST parse: `ast ok`.
- Canonical summary:
  - rows: 82
  - canonical_selected_rows: 79
  - raw_fallback_not_applicable_rows: 3
  - canonical_ambiguous_rows: 0
  - canonical_lookup_error_rows: 0

Representative row check:

- `deepening -> deepen`
- `depicts -> depict`
- `marked -> mark`
- `shimmering -> shimmer`
- `shining -> shine`
- `sits in -> sit in`
- `slopes -> slope`
- `stands out -> stand out`

Generated artifacts:

- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_canonical.tsv`
- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_canonical_ambiguous.tsv`
- `outputs/case_reports_sentence20_current/gpic_observed_action_inventory_canonical_summary.json`

Interpretation:

- Sentence-20 action canonical inventory has no remaining canonical manual
  blockers.
- The 3 raw fallback rows have no selected synset, so canonical selection is
  intentionally not applicable for those rows.

## 2026-07-10: Sentence-20 Stage 4/5/6 Rerun With Action Canonical Export

Decision under test:

- Completed action canonical inventory should feed Stage 5 R22 through
  `action_synonyms.tsv`.
- Stage 4 extraction graph should remain the same shape, while Stage 5/6 action
  labels should use canonical action surfaces where available.

Commands:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_export_attribute_stage5_lexicons.py"
.\scripts\run_python.ps1 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in ['scripts/export_attribute_stage5_lexicons.py','tests/test_export_attribute_stage5_lexicons.py']]; print('ast ok')"
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv --action-canonical-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical.tsv --output-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_action_canonical --summary outputs\case_reports_sentence20_current\attribute_action_stage5_lexicon_export_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --action-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence20_current\stage4_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_attribute_action_canonical.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_action_canonical --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_action_canonical_summary.jsonl --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_action_canonical --summary outputs\case_reports_sentence20_current\stage6_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_action_canonical\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_action_canonical.md --start 0 --limit 20 --max-object-pairs-per-caption 40
```

Results:

- `test_export_attribute_stage5_lexicons.py`: 2 tests passed.
- AST parse: `ast ok`.
- Stage 5 lexicon export:
  - action_inventory_rows: 82
  - action_synonym_rows_added: 79
  - action_raw_fallback_rows_skipped: 3
  - attribute synonym rows added: 97
- Stage 4:
  - raw mentions: 516
  - raw edges: 307
  - mention counts: `action=104`, `attribute=141`, `object=263`,
    `quantity=8`
- Stage 5:
  - canonical mentions: 516
  - canonical edges: 307
  - canonical source counts:
    `gpic_observed_inventory=251`, `lexicon=232`, `raw_fallback=33`
- Stage 6:
  - facts: 4848
  - action events: 104
  - action count rows: 71

Representative action count check:

- `deepening -> deepen`
- `depicts -> depict`
- `shimmering -> shimmer`
- `shining -> shine`
- `sits in -> sit in`
- `slopes -> slope`
- `stands out -> stand out`

Generated artifacts:

- `outputs/case_reports_sentence20_current/stage5_lexicons_attribute_action_canonical/`
- `outputs/case_reports_sentence20_current/raw_mentions_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence20_current/raw_edges_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence20_current/canonical_mentions_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence20_current/canonical_edges_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence20_current/stage6_attribute_action_canonical/`
- `outputs/case_reports_sentence20_current/caption_to_concept_cases_0001_0020_attribute_action_canonical.md`

Interpretation:

- The action canonical inventory is now connected to active R22 via generated
  `action_synonyms.tsv`.
- Stage 6 action counts now use canonical action keys where action canonical
  evidence exists.
- Raw fallback actions remain raw-surface counted.

## 2026-07-10: R15 Fronted Preposition Rejection Regression

Decision under test:

- R15 should not build a phrasal action candidate from a preposition token that
  appears before the VERB head.
- Following prepositions such as `look at` should still be valid phrasal action
  candidates.

Command:

```powershell
.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p test_stage4_extract_raw.py
```

Result:

- 23 tests passed in 1.652 seconds.

Interpretation:

- The new fronted-PP regression test confirms `In ... frame` does not become
  `frame in` even when `frame in` exists in action lookup.
- The existing `look at` regression test confirms following-preposition phrasal
  action behavior still works.

## 2026-07-10: Sentence-20 Rerun After R15 Fronted Preposition Filter

Decision under test:

- The generated 20-caption action inventory and report should reflect the R15
  `prep.i > verb.i` constraint.
- Previously observed `frame In` and `frames In` action spans should become
  single-verb `frame` and `frames` actions.

Commands:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\build_gpic_observed_action_inventory.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory.tsv --needs-manual-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_needs_manual.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\apply_action_manual_resolution.py --full-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory.tsv --manual-decisions outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_decisions.tsv --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --resolved-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved_subset.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolution_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 180 scripts\enrich_gpic_action_inventory_canonical.py --input outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical.tsv --ambiguous-output outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical_ambiguous.tsv --summary outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv --action-canonical-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory_canonical.tsv --output-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_action_canonical --summary outputs\case_reports_sentence20_current\attribute_action_stage5_lexicon_export_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence20_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence20_current\gpic_observed_object_inventory_redecided_from_manual_review.tsv --action-inventory outputs\case_reports_sentence20_current\gpic_observed_action_inventory_manual_resolved.tsv --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence20_current\stage4_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence20_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence20_current\raw_edges_attribute_action_canonical.jsonl --lexicon-dir outputs\case_reports_sentence20_current\stage5_lexicons_attribute_action_canonical --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence20_current\stage5_attribute_action_canonical_summary.jsonl --attribute-inventory outputs\case_reports_sentence20_current\gpic_observed_attribute_inventory_typed.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --output-dir outputs\case_reports_sentence20_current\stage6_attribute_action_canonical --summary outputs\case_reports_sentence20_current\stage6_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_caption_concept_md.py --sentence-rows outputs\benchmark_real10k_train\sentence_rows_9896.jsonl.gz --stage3-records outputs\case_reports_sentence20_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence20_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence20_current\canonical_edges_attribute_action_canonical.jsonl --facts outputs\case_reports_sentence20_current\stage6_attribute_action_canonical\facts.jsonl --output outputs\case_reports_sentence20_current\caption_to_concept_cases_0001_0020_attribute_action_canonical.md --start 0 --limit 20 --max-object-pairs-per-caption 40
```

Results:

- Action inventory:
  - rows: 82
  - chosen: 71
  - needs_manual: 8
  - raw_fallback: 3
  - candidate types: `verb=71`, `verb_prep=10`, `verb_prt=1`
- Manual action resolution:
  - overlaid rows: 8
  - merged status: `chosen=79`, `raw_fallback=3`
- Action canonical inventory:
  - selected rows: 79
  - ambiguous rows: 0
  - raw fallback not applicable rows: 3
- Stage 4:
  - raw mentions: 516
  - raw edges: 305
  - edge types: `event_role=106`, `has_attribute=141`, `has_quantity=8`,
    `relation=50`
- Stage 6:
  - facts: 4846
  - action events: 104
  - action count rows: 71
  - agent/patient pair rows: 103
  - relation triple rows: 50

Verification:

- `frame In` and `frames In` no longer appear in the regenerated raw mentions,
  canonical mentions, action count table, or Markdown report.
- `action:frame in` and `action:frames in` no longer appear in regenerated
  Stage 6 action counts.
- The regenerated report shows `frames` and `frame` as single-verb actions for
  the two former fronted-PP cases.

## 2026-07-10: Sentence-100 Action Inventory Gate Probe

Decision under test:

- Expand the latest R15 action inventory flow from 20 sentence captions to the
  existing 100-caption `0101_0200` sample.
- Stop before Stage 4 if unresolved action `needs_manual` rows remain.

Command:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 300 scripts\build_gpic_observed_action_inventory.py --input outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory.tsv --needs-manual-output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_needs_manual.tsv --summary outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_summary.json
```

Result:

- caption_total: 100
- verb_token_total: 432
- inventory_rows: 221
- decision_status_counts:
  - chosen: 206
  - needs_manual: 13
  - raw_fallback: 2
- candidate_type_counts:
  - verb: 189
  - verb_prep: 30
  - verb_prt: 2
- decision_reason_counts:
  - selected_verb_synset: 206
  - manual_action_synset_required: 12
  - manual_action_morphy_required: 1
  - no_oewn_verb_synset: 2

Generated artifacts:

- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory_needs_manual.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory_summary.json`

Interpretation:

- Formal Stage 4/5/6 100-caption regeneration did not proceed because 13
  action rows still require manual action synset resolution.
- The next step is to resolve
  `gpic_observed_action_inventory_needs_manual.tsv`, then rerun action manual
  resolution, action canonical enrichment, Stage 5 lexicon export, and Stage
  4/5/6.

## 2026-07-10: Sentence-100 Full Rerun With Action Manual Decisions

Decision under test:

- Apply the 13 user-provided action synset manual decisions for the 100-caption
  `0101_0200` sample.
- Continue through action canonical enrichment, Stage 5 lexicon export, Stage
  4/5/6, and Markdown report generation after the action gate is clear.

Manual decisions:

```text
sit in -> oewn-02619175-v
sits in -> oewn-02619175-v
holding in -> oewn-02716988-v
hold in -> oewn-02716988-v
holds in -> oewn-02716988-v
combed -> oewn-00038078-v
drawn in -> oewn-01509215-v
marked -> oewn-01591414-v
marking -> oewn-01591414-v
neighboring -> oewn-02614211-v
silhouetting -> oewn-01684516-v
stands out -> oewn-02680375-v
striped -> oewn-01275827-v
```

Commands:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\apply_action_manual_resolution.py --full-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory.tsv --manual-decisions outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_decisions.tsv --output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_resolved.tsv --resolved-output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_resolved_subset.tsv --summary outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_resolution_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 240 scripts\enrich_gpic_action_inventory_canonical.py --input outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_resolved.tsv --output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_canonical.tsv --ambiguous-output outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_canonical_ambiguous.tsv --summary outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_canonical_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\export_attribute_stage5_lexicons.py --attribute-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv --action-canonical-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_canonical.tsv --output-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_action_canonical --summary outputs\case_reports_sentence100_0101_0200_current\attribute_action_stage5_lexicon_export_summary.json
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 240 scripts\run_stage4_extract_raw.py --input outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --object-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv --action-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_action_inventory_manual_resolved.tsv --raw-mentions outputs\case_reports_sentence100_0101_0200_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence100_0101_0200_current\raw_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence100_0101_0200_current\stage4_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 240 scripts\run_stage5_canonicalize.py --raw-mentions outputs\case_reports_sentence100_0101_0200_current\raw_mentions_attribute_action_canonical.jsonl --raw-edges outputs\case_reports_sentence100_0101_0200_current\raw_edges_attribute_action_canonical.jsonl --lexicon-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_action_canonical --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_action_canonical.jsonl --summary outputs\case_reports_sentence100_0101_0200_current\stage5_attribute_action_canonical_summary.jsonl --attribute-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_attribute_inventory_current_manual_resolved_canonical.tsv
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 240 scripts\run_stage6_export_counts.py --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_action_canonical.jsonl --output-dir outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_action_canonical --summary outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_action_canonical_summary.jsonl
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 240 scripts\build_caption_concept_md.py --sentence-rows outputs\case_reports_sentence100_0101_0200_current\sentence_rows_0101_0200.jsonl --stage3-records outputs\case_reports_sentence100_0101_0200_current\stage3_records.jsonl --canonical-mentions outputs\case_reports_sentence100_0101_0200_current\canonical_mentions_attribute_action_canonical.jsonl --canonical-edges outputs\case_reports_sentence100_0101_0200_current\canonical_edges_attribute_action_canonical.jsonl --facts outputs\case_reports_sentence100_0101_0200_current\stage6_attribute_action_canonical\facts.jsonl --output outputs\case_reports_sentence100_0101_0200_current\caption_to_concept_cases_0101_0200_attribute_action_canonical.md --start 0 --limit 100 --max-object-pairs-per-caption 40
```

Results:

- Action manual resolution:
  - overlaid rows: 13
  - merged status: `chosen=219`, `raw_fallback=2`
- Action canonical inventory:
  - rows: 221
  - canonical selected rows: 219
  - canonical ambiguous rows: 0
  - raw fallback not applicable rows: 2
- Stage 4:
  - raw mentions: 2252
  - raw edges: 1278
  - mention counts: `action=432`, `attribute=614`, `object=1169`,
    `quantity=37`
  - edge counts: `event_role=430`, `has_attribute=614`, `has_quantity=37`,
    `relation=197`
- Stage 5:
  - canonical mentions: 2252
  - canonical edges: 1278
  - canonical source counts:
    `gpic_observed_inventory=1065`, `lexicon=1016`, `raw_fallback=171`
- Stage 6:
  - facts: 21887
  - action events: 432
  - entity exists: 1169
  - event roles: 430
  - relations: 197
  - object pair facts: 19008
  - table row counts:
    - action_counts.tsv: 163
    - agent_patient_pair_counts.tsv: 377
    - attribute_counts.tsv: 255
    - object_attribute_pair_counts.tsv: 547
    - object_cooccurrence_pair_counts.tsv: 16324
    - object_counts.tsv: 504
    - relation_triple_counts.tsv: 182

Validation:

- `gpic_observed_action_inventory_manual_resolved.tsv` has no remaining
  `needs_manual` rows.
- Action canonical summary has `canonical_ambiguous_rows=0`.
- The regenerated action counts and Markdown report do not contain
  `action:frame in`, `frame In`, or `frames In`.

## 2026-07-10: Wiktionary Preposition MWE Candidate Probe

Decision under test:

- Build an offline preposition-form MWE candidate inventory from
  Wiktionary/Wiktextract evidence.
- Keep only English entries with `pos == "prep"` and at least two
  whitespace-delimited surface tokens.
- Do not promote the result into active Stage 4 relation MWE behavior.

Command:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_wiktionary_prep_mwe_candidates.py --output-dir outputs\wiktionary_prep_mwe_candidates
```

Result:

- JSONL entries read: 870
- English prep entries: 870
- single-token prep entries excluded: 592
- MWE prep entries: 278
- MWE prep senses: 389
- unique MWE surfaces: 278
- generated candidate rows have `min_token_count=2`, `max_token_count=5`,
  and no single-token rows.

Generated artifacts:

- `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_candidates.tsv`
- `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_senses.tsv`
- `outputs/wiktionary_prep_mwe_candidates/wiktionary_prep_mwe_summary.json`

Interpretation:

- The probe produced a source candidate inventory only.
- Active relation extraction remains raw-preserving under R18/R24.

## 2026-07-10: External Preposition Source Candidate Probe

Decision under test:

- Pull and summarize TPP/PDEP/STREUSLE/PASTRIE-related preposition sources for
  manual relation-MWE candidate review.
- Keep the result as offline evidence only.
- Do not promote candidates into active Stage 4 relation MWE behavior.

Source pulls completed:

- `git clone --depth 1 https://github.com/nert-nlp/streusle.git outputs\external_preposition_sources\streusle`
- `git clone --depth 1 https://github.com/nert-nlp/pastrie.git outputs\external_preposition_sources\pastrie`
- `git clone --depth 1 https://github.com/kenclr/ca4pdep.git outputs\external_preposition_sources\pdep_ca4pdep`

Generation command:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 120 scripts\build_external_preposition_source_candidates.py
```

Result:

- combined MWE candidate rows: 1,014
- STREUSLE preposition-related MWE occurrences: 1,177
- STREUSLE unique candidates: 653
- STREUSLE `lexcat == P` occurrences: 137
- STREUSLE `lexcat == P` unique candidates: 50
- PASTRIE MWE occurrences: 329
- PASTRIE unique candidates: 210
- PASTRIE `lexcat == P` occurrences: 74
- PASTRIE `lexcat == P` unique candidates: 34
- combined STREUSLE/PASTRIE `lexcat == P` source rows: 84
- combined STREUSLE/PASTRIE `lexcat == P` unique surface keys: 62
- clean STREUSLE/PASTRIE `lexcat == P` source rows: 82
- clean STREUSLE/PASTRIE `lexcat == P` unique surface keys: 60
- excluded STREUSLE/PASTRIE `lexcat == P` artifact rows: 2
- clean STREUSLE/PASTRIE `lexcat == P` rows flagged for unknown SNACS supersense: 3
- PDEP preposition entries: 304
- PDEP multiword preposition entries: 166
- PDEP sense rows: 1,039
- TPP feature-summary prepositions: 44
- TPP feature-summary multiword prepositions: 0
- TPP appendix prepositions: 373
- TPP appendix multiword prepositions: 222
- TPP appendix final curation KEEP rows: 199
- TPP appendix final curation DROP rows: 23
- TPP appendix final curation REVIEW rows: 0
- TPP appendix final curation extraction corrections: 5
- combined preposition MWE source rows: 699
- combined preposition MWE unique entries: 365
- combined non-preposition-MWE source rows: 190
- combined non-preposition-MWE unique entries: 179
- combined source disagreement entries after manual drop: 0

Generated artifacts:

- `outputs/external_preposition_sources/candidate_tables/external_preposition_mwe_candidates_combined.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_preposition_mwe_candidates.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_preposition_mwe_occurrences.tsv`
- `outputs/external_preposition_sources/candidate_tables/pastrie_preposition_mwe_candidates.tsv`
- `outputs/external_preposition_sources/candidate_tables/pastrie_preposition_mwe_occurrences.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_p_lexcat_preposition_mwe_candidates.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_p_lexcat_preposition_mwe_occurrences.tsv`
- `outputs/external_preposition_sources/candidate_tables/pastrie_p_lexcat_preposition_mwe_candidates.tsv`
- `outputs/external_preposition_sources/candidate_tables/pastrie_p_lexcat_preposition_mwe_occurrences.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates_clean.tsv`
- `outputs/external_preposition_sources/candidate_tables/streusle_pastrie_p_lexcat_preposition_mwe_candidates_excluded.tsv`
- `outputs/external_preposition_sources/candidate_tables/pdep_preposition_inventory.tsv`
- `outputs/external_preposition_sources/candidate_tables/pdep_sense_substitutes.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_feature_preposition_summary.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_inventory.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_manual_reaudit.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory_clean.tsv`
- `outputs/external_preposition_sources/candidate_tables/tpp_litkowski_2002_appendix_preposition_mwe_inventory_excluded.tsv`
- `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_inventory.tsv`
- `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_source_rows.tsv`
- `outputs/external_preposition_sources/candidate_tables/combined_non_preposition_mwe_inventory.tsv`
- `outputs/external_preposition_sources/candidate_tables/combined_non_preposition_mwe_source_rows.tsv`
- `outputs/external_preposition_sources/candidate_tables/combined_preposition_mwe_conflicts.tsv`
- `outputs/external_preposition_sources/candidate_tables/external_preposition_source_manifest.tsv`
- `outputs/external_preposition_sources/candidate_tables/external_preposition_source_summary.json`

Validation:

- The builder was run through `scripts\run_script_with_timeout.py`.
- Final generation completed within the 120 second script timeout.
- `compileall` succeeded for
  `scripts\build_external_preposition_source_candidates.py` when run outside
  the sandbox. A sandboxed `compileall` attempt failed only because it could not
  write `scripts\__pycache__` under the project path.

Interpretation:

- STREUSLE, PASTRIE, and PDEP-derived candidate tables are available for manual
  review.
- The original combined STREUSLE/PASTRIE rows are intentionally broad because
  they include `contains_adp_token` and `p_supersense` evidence. A stricter
  follow-up subset keeps only occurrence rows whose holistic MWE lexical
  category is exactly `P`.
- The stricter STREUSLE/PASTRIE `lexcat == P` subset has 84 source rows and 62
  unique surface keys. It excludes `contains_adp_token`-only rows, `PP`
  idiomatic prepositional phrases, and verbal MWE rows.
- A follow-up review-clean step removes two single-token lexical artifacts:
  `into` with surface `In To`, and `within` with surface `win in`. The clean
  STREUSLE/PASTRIE `lexcat == P` inventory therefore has 82 source rows and 60
  unique surface keys.
- The clean STREUSLE/PASTRIE source table still records three `lexcat == P`
  candidates with unknown SNACS supersense evidence: `at hand`, `in my hand`
  (surface `in my hands`), and `in this day`. In the combined prep-MWE
  inventory these are manually dropped because they are idiomatic or ordinary
  PP expressions, not preposition MWEs that take an NP complement.
- The PDEP inventory extraction did perform the intended inventory filter:
  `prepcnts.csv` has 304 preposition entries, and 166 of them have at least two
  whitespace-delimited tokens.
- The TPP artifact in this probe is limited to the `ca4pdep` TPP feature
  summary, where the 44 retrieved preposition labels are all single-token
  labels. This is not the full original TPP database or the original TPP
  phrasal-preposition inventory.
- A follow-up check found the original NODE/TPP appendix inventory in Litkowski
  (2002), Table A-2. It was extracted from the ACL Anthology PDF with
  coordinate-based column reconstruction. The extracted table has exactly 373
  entries, including 222 multiword entries.
- Therefore `TPP feature-summary multiword prepositions: 0` must not be read as
  evidence that original TPP has no phrasal prepositions.
- The archived `clres.com/prepositions.html` TPP page confirms that Online TPP
  once linked `tppdata.zip` for downloading the full database. The exact zip was
  not retrievable from Wayback CDX during this probe, so the appendix PDF table
  is the retrieved original inventory source.
- The current historical `clres.com/prepositions.html` host was checked on
  2026-07-10 and redirects to unrelated casino content, so the live host was not
  used as a data source.
- The TPP appendix multiword candidates were then curated from
  `C:\Users\rlath\Downloads\tpp_preposition_mwe_final (1).xlsx`. The final
  clean inventory keeps 199 rows, excludes 23 rows, and leaves 0 rows in review.
- The final curation records five extraction corrections: `#à la -> à la`,
  `head and shoulders -> head and shoulders above`, `above inside -> inside`,
  `not someone's idea -> not someone's idea of`, and
  `of this side of -> this side of`.
- The curated source rows were combined with PDEP multiword preposition rows,
  Wiktionary English `pos=prep` MWE rows, and clean STREUSLE/PASTRIE
  `lexcat == P` rows. After the user-approved conflict drop decision and the
  Wiktionary misspelling/manual-drop filters, the combined preposition MWE
  inventory has 699 source rows and 365 deduplicated entries.
- The combined non-preposition-MWE inventory has 190 source rows and 179
  deduplicated entries. It includes TPP final DROP rows, STREUSLE/PASTRIE
  artifact exclusions, PDEP single-token prepositions, Wiktionary
  `misspelling` rows, manual-drop rows, and source rows moved by the
  `manual_conflict_drop` decision.
- STREUSLE/PASTRIE `lexcat == P` rows now use observed corpus surfaces as
  matcher/lookup `entry` and `lookup_forms`; their corpus MWE `lexlemma` is
  retained separately as `canonical_lemma` evidence. This prevents source
  lemmas such as `accord to`, `in term of`, `see as`, and `when it come to`
  from becoming direct lookup entries when only inflected observed surfaces
  were attested.
- Wiktionary `misspelling` rows such as `as oppose to`, `incase of`, and
  `infront of` are retained only in the non-preposition-MWE inventory.
- `a matter of`, `as if`, `at hand`, `for example`, `from the ground up`,
  `in my hands`, `in this day`, `seeing as`, and `the dickens` are manually
  dropped from the prep-MWE inventory.
- `d t`, `out ta`, and `rather then` are not standalone prep-MWE entries; they
  are retained only as surface-variant evidence under `due to`, `out of`, and
  `rather than`.
- The originally reviewed eight source-disagreement entries were all dropped
  from the prep-MWE inventory by explicit user decision: `a cut above`,
  `bare of`, `in memoriam`, `little short of`, `nothing short of`,
  `preparatory to`, `short for`, and `shot through with`. The same
  conflict-drop rule is applied to the current combined source audit, and the
  regenerated `combined_preposition_mwe_conflicts.tsv` has 0 unresolved rows.
- Active relation extraction remains raw-preserving under R18/R24.

Generated artifacts:

- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory_manual_decisions.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory_manual_resolved.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/gpic_observed_action_inventory_canonical.tsv`
- `outputs/case_reports_sentence100_0101_0200_current/stage5_lexicons_attribute_action_canonical/`
- `outputs/case_reports_sentence100_0101_0200_current/raw_mentions_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/raw_edges_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/canonical_mentions_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/canonical_edges_attribute_action_canonical.jsonl`
- `outputs/case_reports_sentence100_0101_0200_current/stage6_attribute_action_canonical/`
- `outputs/case_reports_sentence100_0101_0200_current/caption_to_concept_cases_0101_0200_attribute_action_canonical.md`

## 2026-07-11: Active preposition MWE relation implementation tests

Change under test:

- Stage 4 now loads active `resources/lexicons/preposition_mwes.tsv` rows.
- Stage 4 detects contiguous preposition MWE spans, marks their tokens as
  `relation_mwe_consumed`, creates R18.1 relation edges only when source/target
  dependency evidence is present, and suppresses consumed single-ADP relation
  extraction.
- Stage 5 preserves relation MWE edge metadata.
- Stage 6 emits `attribute_exists`, `quantity_exists`, `object_parent`, and
  `relation_component` facts/counts.

Generated artifact:

- `resources/lexicons/preposition_mwes.tsv`

Validation commands:

- `.\scripts\run_python.ps1 -c "import ast, pathlib; ..."`
  - Result: `ast parse ok 9`
  - Interpretation: syntax parse passed without writing `__pycache__`.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage4_extract_raw.py`
  - Result: 25 tests passed in 2.247 seconds.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage5_canonicalize.py`
  - Result: 5 tests passed in 0.096 seconds.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage6_export_counts.py`
  - Result: 2 tests passed in 0.099 seconds.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_schema.py`
  - Result: 6 tests passed.

Permission note:

- A direct `compileall src scripts tests` attempt failed because Python tried to
  write `__pycache__` files under the project path. This was not a syntax
  failure.
- `scripts\run_tests.ps1` now sets `PYTHONDONTWRITEBYTECODE=1` so bounded test
  runs do not depend on project `__pycache__` write permission.

## 2026-07-11: Preposition MWE matcher index optimization

Change under test:

- Stage 4 preposition MWE span matching was changed from scanning every lexicon
  entry against every caption position to building a token-sequence index once
  and matching caption n-grams by dictionary lookup.
- The semantic rule is unchanged: exact contiguous token span matching,
  longest overlapping span first, and earlier span as the tie-breaker.

Validation commands:

- `.\scripts\run_python.ps1 -c "import ast, pathlib; ..."`
  - Result: `ast ok`
  - Interpretation: `stage4_extract_raw.py` and `test_stage4_extract_raw.py`
    parsed successfully without writing bytecode.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p test_stage4_extract_raw.py`
  - Result: 26 tests passed in 1.484 seconds.
  - Interpretation: Stage 4 raw extraction behavior, including the indexed
    preposition MWE lookup path and longest-overlap policy, still passes the
    focused regression suite.

Invocation note:

- `.\scripts\run_tests.ps1 --timeout-seconds 60 tests.test_stage4_extract_raw`
  failed because `tests` is not a Python package. The corrected bounded unittest
  invocation is the `discover -s tests -p test_stage4_extract_raw.py` command
  above.

## 2026-07-11: Action-Attached Preposition MWE Relation Candidate Preservation

Change under test:

- R18.1 now creates a normal relation edge when a preposition MWE is attached to
  a VERB head and that VERB has exactly one direct object-mapped source
  child candidate.
- If multiple direct object-mapped source candidates exist, R18.1 creates
  `ambiguous_relation_candidate` edges instead of normal relation triples.
- Stage 6 exports those candidate edges to
  `ambiguous_relation_candidate_counts.tsv`.

Validation commands:

- `.\scripts\run_python.ps1 -c "import ast, pathlib; ..."`
  - First attempt using `encoding='utf-8'` failed on an existing BOM in one file
    because `ast.parse()` received the BOM character directly.
  - Re-run with `encoding='utf-8-sig'` succeeded: `ast ok`.
- `.\scripts\run_python.ps1 -m compileall -q src\gpic_concepts_v1 scripts tests`
  - Failed with `PermissionError` while writing `__pycache__`; this was not a
    syntax failure.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p "test_stage4_extract_raw.py"`
  - Result: 28 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p "test_stage5_canonicalize.py"`
  - Result: 6 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p "test_stage6_export_counts.py"`
  - Result: 2 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 60 discover -s tests -p "test_schema.py"`
  - Result: 6 tests passed.

20-caption rerun:

- Output directory:
  `outputs/case_reports_sentence20_preposition_mwe_current`
- Stage 4:
  - raw mentions: 515
  - raw edges: 304
  - edge type counts: `event_role=105`, `has_attribute=141`,
    `has_quantity=8`, `relation=50`
  - R18.1 hit count: 1
  - R18.1 hit:
    `woman --in front of--> screen`, source resolution
    `head_direct_object_child`, source dep `nsubj`
- Stage 6:
  - fact total: 5254
  - relation facts: 50
  - relation component facts: 3
  - ambiguous relation candidate table rows: 0
  - new output table exists:
    `stage6/ambiguous_relation_candidate_counts.tsv`
- Markdown report regenerated:
  `outputs/case_reports_sentence20_preposition_mwe_current/caption_to_concept_cases_0001_0020_preposition_mwe_current.md`

Interpretation:

- The original first-caption case now produces the intended normal relation
  row: `relation:woman:in front of:screen`.
- No ambiguous relation candidate case happened in this 20-caption sample, but
  unit tests cover the multiple-source candidate path.

## 2026-07-11: 100-Caption Preposition MWE Relation Rerun

Purpose:

- Re-run the 0101-0200 100-caption sample after R18.1 action-attached
  preposition MWE handling, including `ambiguous_relation_candidate` export.

Output directory:

- `outputs/case_reports_sentence100_0101_0200_preposition_mwe_current`

Validation command group:

- Stage 4 raw extraction, Stage 5 canonicalization, Stage 6 count export, and
  Markdown report generation were run with bounded 240-second wrappers.

Results:

- Stage 4:
  - raw mentions: 2246
  - raw edges: 1280
  - edge type counts: `event_role=428`, `has_attribute=614`,
    `has_quantity=37`, `relation=197`,
    `ambiguous_relation_candidate=4`
- Stage 5:
  - canonical mentions: 2246
  - canonical edges: 1280
  - `formal_attribute_inventory_gate=true`
- Stage 6:
  - fact total: 23567
  - relation facts: 197
  - relation component facts: 19
  - ambiguous relation candidate facts: 4
  - ambiguous relation candidate table rows: 4
- Markdown report:
  `outputs/case_reports_sentence100_0101_0200_preposition_mwe_current/caption_to_concept_cases_0101_0200_preposition_mwe_current.md`

Observed relation MWE checks:

- `in front of` relation triples appeared in 3 captions.
- `in front of` relation components appeared as 3 component tokens across those
  3 captions.
- The 4 ambiguous relation candidates all came from an `along with` case where
  multiple object-mapped source/target candidates were preserved for review.

## 2026-07-11: 100-Caption R18.1 Rerun After VERB/AUX Head Source Rule

Purpose:

- Re-run the same 0101-0200 100-caption sample after extending R18.1 source
  candidates from `VERB` heads to `VERB`/`AUX` heads.

Output directory:

- `outputs/case_reports_sentence100_0101_0200_preposition_mwe_aux_head`

Validation commands:

- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage4_extract_raw.py`
  - Result: 32 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage5_canonicalize.py`
  - Result: 6 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage6_export_counts.py`
  - Result: 3 tests passed.
- `git diff --check`
  - Result: passed. Git warned that existing `AGENTS_ko.md` line endings will
    be normalized when Git touches that file.

Rerun results:

- Stage 4:
  - raw mentions: 2246
  - raw edges: 1289
  - edge type counts: `event_role=428`, `has_attribute=614`,
    `has_quantity=37`, `relation=206`,
    `ambiguous_relation_candidate=4`
- Stage 5:
  - canonical mentions: 2246
  - canonical edges: 1289
  - `formal_attribute_inventory_gate=true`
- Stage 6:
  - fact total: 23593
  - relation facts: 206
  - relation component facts: 39
  - ambiguous relation candidate facts: 1
  - relation triple table rows: 192
- Markdown report:
  `outputs/case_reports_sentence100_0101_0200_preposition_mwe_aux_head/caption_to_concept_cases_0101_0200_preposition_mwe_aux_head.md`

Previously discussed relation MWE checks:

- `0015`: `leg --out of--> focus` now appears.
- `0025`: still emits `scene --next to--> wall`; the desired `area --next to--> wall`
  is not recovered because the current rule still does not do semantic source
  disambiguation.
- `0048`: `building --along with--> sign` now appears.
- `0050`: `bowl --next to--> it` now appears.
- `0076`: `van --in front of--> building` now appears.
- `0076`: `along with contact details` is still not semantically recovered as
  `markings --along with--> details`; current dependency evidence gives
  `"Marc Sovaerts" --along with--> detail`.
- `0090`: `screen --in front of--> building` now appears.
- `0100`: still missing. In the parse, `man` is `nsubj` of `speaks`, while
  `in front of` is attached to `standing`; `man` is not a direct child of the
  MWE head, and R18.1 still does not climb to sibling/ancestor event roles.

## 2026-07-11: 100-Caption R18.1 Rerun After Missing Endpoint Preservation

Purpose:

- Re-run the same 0101-0200 100-caption sample after preserving matched R18.1
  MWE occurrences as `ambiguous_relation_candidate` rows when source or target
  candidates are missing.

Output directory:

- `outputs/case_reports_sentence100_0101_0200_preposition_mwe_missing_endpoint`

Validation commands:

- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_schema.py`
  - Result: 7 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage4_extract_raw.py`
  - Result: 33 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage5_canonicalize.py`
  - Result: 7 tests passed.
- `.\scripts\run_tests.ps1 --timeout-seconds 90 discover -s tests -p test_stage6_export_counts.py`
  - Result: 4 tests passed.

Rerun results:

- Stage 4:
  - raw mentions: 2246
  - raw edges: 1291
  - edge type counts: `event_role=428`, `has_attribute=614`,
    `has_quantity=37`, `relation=206`,
    `ambiguous_relation_candidate=6`
- Stage 5:
  - canonical mentions: 2246
  - canonical edges: 1291
  - `formal_attribute_inventory_gate=true`
- Stage 6:
  - fact total: 23595
  - relation facts: 206
  - relation component facts: 39
  - ambiguous relation candidate facts: 3
  - relation triple table rows: 192
  - ambiguous relation candidate table rows: 3
- Markdown report:
  `outputs/case_reports_sentence100_0101_0200_preposition_mwe_missing_endpoint/caption_to_concept_cases_0101_0200_preposition_mwe_missing_endpoint.md`

Observed ambiguous relation occurrences:

- `0015`: existing `along with` candidate remains
  `source_ambiguous / along with / target_ambiguous`.
- `0048`: previously dropped `such as` occurrence is now visible as
  `source_missing / such as / target_resolved`.
- `0100`: previously dropped `standing in front of a brick wall` occurrence is
  now visible as `source_missing / in front of / target_resolved`, with target
  `wall`.

Interpretation:

- Missing-endpoint occurrences no longer disappear silently.
- Normal relation facts stayed at 206, so missing endpoint candidates are not
  mixed into confirmed relation triples.
- Object count stayed at 1163, because missing endpoints do not create object
  mentions.

## 2026-07-11: Broad Preposition MWE Lexicon Merge Speed Probe

Purpose:

- Compare 100-caption runtime before and after merging the user-approved Google
  Ngram ADP...of relation pattern rows into the active Stage 4 preposition MWE
  lexicon.

Lexicon change:

- Baseline active lexicon: 370 rows.
- Broad active lexicon: 5021 rows.
- Broad rows by source:
  - `GOOGLE_NGRAM_RELATION_PATTERN`: 4651
  - reviewed external preposition MWE rows: 370
- Broad lexicon widths:
  - 2 tokens: 129
  - 3 tokens: 1322
  - 4 tokens: 2243
  - 5 tokens: 1327

Validation commands:

- `.\scripts\run_tests.ps1 --timeout-seconds 120 discover -s tests -p "test_stage4_extract_raw.py"`
  - Result: 33 tests passed.
- `.\scripts\run_python.ps1 -c "import ast; from pathlib import Path; ast.parse(Path('scripts/export_preposition_mwe_stage4_lexicon.py').read_text(encoding='utf-8'))"`
  - Result: passed.
- `.\scripts\run_python.ps1 -m compileall scripts\export_preposition_mwe_stage4_lexicon.py`
  - Result: failed with `PermissionError` while writing `scripts\__pycache__`.
  - Interpretation: bytecode write permission failure, not a syntax failure.

Benchmark command:

- `.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 300 scripts\benchmark_fast_pipeline.py --input outputs\case_reports_sentence100_0101_0200_current\sentence_rows_0101_0200.jsonl --object-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv --lexicon-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_action_canonical --batch-size 512 --summary outputs\benchmark_preposition_mwe_broad\baseline_370_summary.json`
- `.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 300 scripts\benchmark_fast_pipeline.py --input outputs\case_reports_sentence100_0101_0200_current\sentence_rows_0101_0200.jsonl --object-inventory outputs\case_reports_sentence100_0101_0200_current\gpic_observed_object_inventory_manual_resolved_parent_canonical.tsv --lexicon-dir outputs\case_reports_sentence100_0101_0200_current\stage5_lexicons_attribute_action_canonical --batch-size 512 --summary outputs\benchmark_preposition_mwe_broad\broad_5021_summary.json`

Benchmark scope:

- Input: 100 sentence captions, `0101-0200`.
- Model: `en_core_web_trf`.
- Batch size: 512.
- Length bucketing: disabled.
- Raw extraction mode: `stage3-record`.
- GPU mode: none; latest run reported `gpu_enabled=false`.
- GPU metadata was recorded in both summary JSON files.
- This is a speed probe through `benchmark_fast_pipeline.py`; the benchmark
  path does not write formal Stage 4/5/6 JSONL artifacts.

Benchmark result:

| metric | baseline 370 | broad 5021 | delta |
|---|---:|---:|---:|
| processing seconds | 3.7338 | 3.9036 | +0.1698 |
| processing captions/sec | 26.78 | 25.62 | -1.17 |
| total seconds | 5.1837 | 5.2059 | +0.0221 |
| total captions/sec | 19.29 | 19.21 | -0.08 |
| Stage 3 seconds | 3.0634 | 3.0984 | +0.0350 |
| Stage 4 seconds | 0.1783 | 0.2146 | +0.0362 |
| Stage 6 seconds | 0.3999 | 0.4936 | +0.0937 |

Count-impact observation from benchmark output:

- `relation_component` facts increased from 39 to 74.
- `ambiguous_relation_candidate` facts increased from 3 to 4.
- `relation` facts changed from 206 to 205.
- `entity_exists` facts changed from 1163 to 1155.
- The object/fact-total changes mean broad preposition MWE consumption affects
  more than relation labels in this sample, so formal report review is still
  needed before treating the broad lexicon output as the new report baseline.

Interpretation:

- The active lexicon grew from 370 to 5021 rows.
- Stage 4 time increased by about 0.036 seconds on 100 captions in this run.
- The dominant runtime remains Stage 3 transformer parsing in this 100-caption
  benchmark.
