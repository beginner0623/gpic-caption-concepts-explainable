# Incident Response Log V1

This log records repeated failure paths and the durable guard added before the
pipeline resumed.

## 2026-07-17: Stage6 TSV Report Lost Full Caption Drill-Down

### What Failed

The 1M interactive report was built from Stage 6 aggregate TSVs and reused
`example_caption_ids` as `_caption_ids`. Row caption panels therefore showed at
most five captions even when `caption_count` was much larger.

### Why It Happened

The Stage 6 TSV report path optimized memory by switching from Stage 5
mention/edge records to aggregate count TSVs. The implementation accepted the
loss of full row-to-caption evidence as a report note instead of treating it as
a feature regression. There was no validation that row-caption drill-down
matched `caption_count`.

### Durable Guard

- `scripts/build_report_caption_index_from_facts.py` streams Stage 6
  `facts.jsonl` and attaches a `report_caption_index` table to `report.db`.
- `scripts/build_interactive_count_report.py` now reads `report_caption_index`
  first and falls back to `_caption_ids` only when the index is absent.
- `scripts/validate_interactive_report_db.py` can require the caption index and
  compare top rows' `caption_count` against indexed caption totals.

### Verification

- Local synthetic DB check: a row with two stored `_caption_ids` was indexed
  from three facts and returned all three caption ids.
- MLXP smoke check on 1M schema: 200,000 facts produced 35,792 indexed
  row-caption entries against the actual report DB schema.
- Production rebuild must run:

```powershell
.\scripts\run_python.ps1 scripts\run_script_with_timeout.py --timeout-seconds 300 -- scripts\run_mlxp_bash.py <script.sh>
```

where `<script.sh>` calls:

```bash
python3 scripts/validate_interactive_report_db.py \
  --report-db "$out/report.db" \
  --summary-json "$out/summary.json" \
  --require-caption-index \
  --check-top-caption-counts 3 \
  --min-patient-action-agent-triples 1
```

## 2026-07-17: MLXP Inline Shell Quoting And BOM Failures

### What Failed

Several MLXP commands were sent as nested PowerShell/Bash inline strings. The
commands failed with broken quotes or a UTF BOM before `set`, and one failed
script still created a partial output directory.

### Why It Happened

The execution path relied on ad hoc nested shell strings:

- PowerShell string interpolation
- WSL argument parsing
- `kubectl exec`
- remote `bash -lc`
- heredocs

This made it easy for quoting, pipes, or BOM bytes to be interpreted at the
wrong layer.

### Durable Guard

- `scripts/run_mlxp_bash.py` sends a local script file as raw bytes to
  `kubectl exec ... bash -s`, strips UTF BOMs, and avoids nested command
  quoting.
- `AGENTS.md` now requires this runner for multi-step MLXP commands from the
  Windows/Codex desktop workspace.

### Verification

The runner successfully executed the MLXP preparation check after the ad hoc
inline command path failed.
