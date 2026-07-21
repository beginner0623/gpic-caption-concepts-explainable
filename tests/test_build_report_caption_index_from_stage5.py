from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_interactive_count_report import main as build_report_main
from build_patient_action_agent_triples_from_facts import (
    build_triples_from_facts,
    write_triples_tsv,
)
from build_patient_action_agent_triples_from_stage5 import (
    build_triples_from_stage5_dirs,
)
from build_report_caption_index_from_facts import main as facts_index_main
from build_report_caption_index_from_stage5 import main as stage5_index_main
from gpic_concepts_v1.io_jsonl import write_jsonl
from gpic_concepts_v1.schema import CanonicalEdge, CanonicalMention
from gpic_concepts_v1.stage6_export_counts import run_stage6_export_counts
from validate_interactive_report_db import main as validate_report_main


def mention(
    caption_id: str,
    mention_id: str,
    mention_type: str,
    canonical: str,
    *,
    raw_text: str | None = None,
    parent_concepts: list[str] | None = None,
    parent_synsets: list[str] | None = None,
) -> CanonicalMention:
    return CanonicalMention(
        caption_id=caption_id,
        mention_id=mention_id,
        mention_type=mention_type,  # type: ignore[arg-type]
        raw_text=raw_text or canonical,
        raw_lemma=canonical,
        canonical=canonical,
        parent_concepts=parent_concepts or [],
        canonical_rule_id="R19" if mention_type == "object" else "R22",
        parent_rule_id="R23" if parent_concepts else None,
        canonical_source="raw_fallback",
        parent_source="lexicon" if parent_concepts else None,
        canonical_detail={
            "parent_oewn_synsets": parent_synsets or [],
        },
    )


def edge(
    caption_id: str,
    edge_id: str,
    edge_type: str,
    source: str,
    target: str,
    label: str,
    *,
    canonical_detail: dict[str, object] | None = None,
) -> CanonicalEdge:
    return CanonicalEdge(
        caption_id=caption_id,
        edge_id=edge_id,
        edge_type=edge_type,  # type: ignore[arg-type]
        source_mention_id=source,
        target_mention_id=target,
        label=label,
        canonical_label=label,
        source_canonical="unused",
        target_canonical="unused",
        rule_id="R18" if edge_type == "relation" else "R16",
        canonical_rule_id="R24" if edge_type == "relation" else None,
        canonical_detail=canonical_detail or {},
    )


class BuildReportCaptionIndexFromStage5Test(unittest.TestCase):
    def test_stage5_direct_index_matches_existing_facts_index(self) -> None:
        tmp_path = _temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            stage5_dir = tmp_path / "stage5"
            stage6_dir = tmp_path / "stage6"
            report_dir = tmp_path / "report"
            stage5_dir.mkdir()
            mentions_path = stage5_dir / "canonical_mentions.jsonl"
            edges_path = stage5_dir / "canonical_edges.jsonl"
            captions_path = tmp_path / "caption_records.jsonl"

            write_jsonl(mentions_path, _sample_mentions())
            write_jsonl(edges_path, _sample_edges())
            write_jsonl(captions_path, _sample_caption_records())

            run_stage6_export_counts(
                mentions_path,
                edges_path,
                output_dir=stage6_dir,
                count_backend="memory",
                max_rss_gib=1000,
            )
            triples_from_facts = build_triples_from_facts(stage6_dir / "facts.jsonl")
            triples_from_stage5, _ = build_triples_from_stage5_dirs([stage5_dir])
            facts_triples_tsv = tmp_path / "facts_triples.tsv"
            stage5_triples_tsv = stage6_dir / "patient_action_agent_triple_counts.tsv"
            write_triples_tsv(facts_triples_tsv, triples_from_facts)
            write_triples_tsv(stage5_triples_tsv, triples_from_stage5)
            self.assertEqual(
                stage5_triples_tsv.read_text(encoding="utf-8"),
                facts_triples_tsv.read_text(encoding="utf-8"),
            )
            build_report_main(
                [
                    "--input-mode",
                    "stage6-tsv",
                    "--stage6-dir",
                    str(stage6_dir),
                    "--caption-records",
                    str(captions_path),
                    "--output-dir",
                    str(report_dir),
                    "--title",
                    "test report",
                    "--overwrite",
                ],
            )

            base_db = report_dir / "report.db"
            facts_db = tmp_path / "facts_index.db"
            stage5_db = tmp_path / "stage5_index.db"
            shutil.copyfile(base_db, facts_db)
            shutil.copyfile(base_db, stage5_db)

            facts_index_main(
                [
                    "--report-db",
                    str(facts_db),
                    "--facts-jsonl",
                    str(stage6_dir / "facts.jsonl"),
                    "--overwrite",
                ],
            )
            stage5_index_main(
                [
                    "--report-db",
                    str(stage5_db),
                    "--stage5-dir",
                    str(stage5_dir),
                    "--progress-json",
                    str(tmp_path / "stage5_index_progress.json"),
                    "--progress-every-captions",
                    "1",
                    "--overwrite",
                ],
            )

            self.assertEqual(_index_rows(stage5_db), _index_rows(facts_db))
            validate_report_main(
                [
                    "--report-db",
                    str(stage5_db),
                    "--summary-json",
                    str(report_dir / "summary.json"),
                    "--require-caption-index",
                    "--check-top-caption-counts",
                    "1",
                    "--min-patient-action-agent-triples",
                    "1",
                ],
            )
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)


def _sample_mentions() -> list[CanonicalMention]:
    return [
        mention(
            "c1",
            "m0",
            "object",
            "dog",
            raw_text="dogs",
            parent_concepts=["animal"],
            parent_synsets=["oewn-animal-n"],
        ),
        mention("c1", "m1", "object", "ball", raw_text="ball"),
        mention("c1", "m2", "action", "chase", raw_text="chased"),
        mention("c1", "m3", "attribute", "red", raw_text="red"),
        mention("c2", "m0", "object", "cat", raw_text="cat"),
        mention("c2", "m1", "object", "mat", raw_text="mat"),
        mention("c2", "m2", "action", "sit", raw_text="sat"),
    ]


def _sample_edges() -> list[CanonicalEdge]:
    return [
        edge("c1", "e0", "event_role", "m2", "m0", "agent"),
        edge("c1", "e1", "event_role", "m2", "m1", "patient"),
        edge("c1", "e2", "has_attribute", "m1", "m3", "has_attribute"),
        edge("c1", "e3", "relation", "m0", "m1", "near"),
        edge("c2", "e0", "event_role", "m2", "m0", "agent"),
        edge("c2", "e1", "relation", "m0", "m1", "on"),
    ]


def _sample_caption_records() -> list[dict[str, object]]:
    return [
        {
            "caption_id": "c1",
            "caption": "Dogs chased a red ball.",
            "caption_type": "sentence",
            "caption_shape": "sentence",
        },
        {
            "caption_id": "c2",
            "caption": "A cat sat on a mat.",
            "caption_type": "sentence",
            "caption_shape": "sentence",
        },
    ]


def _index_rows(db_path: Path) -> list[tuple[str, int, str]]:
    with sqlite3.connect(db_path) as conn:
        return [
            (str(row[0]), int(row[1]), str(row[2]))
            for row in conn.execute(
                "SELECT view_name, row_id, caption_id FROM report_caption_index "
                "ORDER BY view_name, row_id, caption_id",
            )
        ]


def _temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage5_report_caption_index"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for report caption index tests")


if __name__ == "__main__":
    unittest.main()
