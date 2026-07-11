"""Build COCO-to-OEWN-2025+ synset candidate rows.

This script creates source-label candidate resources only. It does not update
active Stage 2 or Stage 5 lexicons.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import nltk
import wn
from nltk.corpus import wordnet as wn30
from wn.morphy import Morphy

from gpic_concepts_v1.atomic_io import atomic_text_writer


ROOT = Path(os.environ.get("GPIC_RUNTIME_ROOT", Path.cwd()))
WN_DATA_DIR = ROOT / "resources" / "wn_data"
NLTK_DATA_DIR = ROOT / "resources" / "nltk_data"
INPUT = ROOT / "resources" / "source_labels" / "coco_instances_2017_categories.tsv"
OUTPUT = ROOT / "resources" / "source_labels" / "coco_oewn2025plus_synset_candidates.tsv"
OEWN_SPEC = "oewn:2025+"
MANUAL_COCO_LABEL_REVIEW_TAG = "manual_select"
MANUAL_COCO_REJECTED_TAG = "manual_reject"


MANUAL_COCO_LABEL_DECISIONS = {
    "person": {
        "status": "select",
        "synset": "oewn-00007846-n",
        "note": "COCO person category means human being; OEWN human-being sense is noun.Tops.",
    },
    "traffic light": {
        "status": "select",
        "synset": "oewn-06887235-n",
        "note": "COCO visual object category; OEWN lexfile is communication because it is a signal.",
    },
    "stop sign": {
        "status": "select",
        "synset": "oewn-92470663-n",
        "note": "COCO visual object category; OEWN lexfile is communication because it is a sign.",
    },
    "sports ball": {
        "status": "reject",
        "synset": "oewn-90012761-n",
        "note": "OEWN sportsball sense is an act, not the COCO physical ball category.",
    },
    "kite": {
        "status": "select",
        "synset": "oewn-03626682-n",
        "note": "COCO sports category refers to the toy artifact sense.",
    },
    "hot dog": {
        "status": "select",
        "synset": "oewn-07713282-n",
        "note": "COCO food category refers to the served food on a bun, not the sausage-only sense.",
    },
    "cake": {
        "status": "select",
        "synset": "oewn-07644479-n",
        "note": "COCO food category refers to baked cake.",
    },
    "tv": {
        "status": "select",
        "synset": "oewn-04413042-n",
        "note": "COCO electronic category refers to the physical television receiver.",
    },
    "microwave": {
        "status": "select",
        "synset": "oewn-03766619-n",
        "note": "COCO appliance category refers to the physical microwave oven.",
    },
    "toaster": {
        "status": "select",
        "synset": "oewn-04449446-n",
        "note": "COCO appliance category refers to the physical toaster.",
    },
    "book": {
        "status": "select",
        "synset": "oewn-02873453-n",
        "note": "User decision: COCO book category is treated as the physical artifact sense.",
    },
    "scissors": {
        "status": "select",
        "synset": "oewn-04155119-n",
        "note": "COCO indoor category refers to the physical cutting tool.",
    },
}


COCO_SUPERCATEGORY_TO_OEWN_LEXFILES = {
    "person": {"noun.person"},
    "animal": {"noun.animal"},
    "food": {"noun.food"},
}


OBJECT_COMPATIBLE_LEXFILES = {
    "noun.animal",
    "noun.artifact",
    "noun.body",
    "noun.food",
    "noun.object",
    "noun.person",
    "noun.plant",
    "noun.substance",
}


CONDITIONAL_OBJECT_LEXFILES = {
    "noun.communication",
    "noun.group",
    "noun.location",
    "noun.phenomenon",
    "noun.possession",
    "noun.shape",
    "noun.Tops",
}


HARD_CONFLICT_LEXFILES = {
    "noun.act",
    "noun.attribute",
    "noun.cognition",
    "noun.event",
    "noun.feeling",
    "noun.motive",
    "noun.process",
    "noun.quantity",
    "noun.relation",
    "noun.state",
    "noun.time",
}


FIELDNAMES = [
    "dataset",
    "category_id",
    "label",
    "supercategory",
    "source_version",
    "is_mwe_candidate",
    "mwe_candidate_status",
    "wordnet_source",
    "wordnet_version",
    "wordnet_lexicon_id",
    "selected_lookup_case",
    "selected_query",
    "has_oewn_noun_synset",
    "oewn_synset_count",
    "selected_oewn_synset",
    "selected_oewn_lexfile",
    "all_oewn_synsets",
    "all_oewn_lexfiles",
    "target_oewn_lexfiles",
    "matched_oewn_lexfiles",
    "synset_lemmas",
    "canonical_surface",
    "canonical_selection_tag",
    "canonical_candidate_lemmas",
    "canonical_candidate_lemma_counts",
    "parent_oewn_synsets",
    "parent_oewn_lexfiles",
    "parent_lemmas",
    "parent_selection_tag",
    "selected_oewn_objectness_class",
    "objectness_gate",
    "manual_decision",
    "manual_decision_note",
    "sense_counts_available",
    "wn30_available",
    "wn30_selection_tag",
    "wn30_lemma_counts",
    "synset_selection_tag",
    "decision_basis",
]


def main() -> None:
    wn.config.data_directory = str(WN_DATA_DIR)
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))
    oewn = wn.Wordnet(OEWN_SPEC, expand="")
    morphy = Morphy(oewn)
    wn30_available = _check_wn30_available()

    rows = list(_read_rows(INPUT))
    candidate_rows = [
        _build_candidate_row(row=row, oewn=oewn, morphy=morphy, wn30_available=wn30_available)
        for row in rows
    ]

    with atomic_text_writer(OUTPUT, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(candidate_rows)

    print(f"wrote={OUTPUT}")
    for key, value in sorted(_summarize(candidate_rows).items()):
        print(f"{key}={value}")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def _build_candidate_row(
    row: dict[str, str],
    oewn: wn.Wordnet,
    morphy: Morphy,
    wn30_available: bool,
) -> dict[str, str]:
    label = row["label"]
    lookup_case, query, synsets = _lookup_oewn_synsets(label=label, oewn=oewn, morphy=morphy)
    target_lexfiles = COCO_SUPERCATEGORY_TO_OEWN_LEXFILES.get(row["supercategory"], set())
    matched_synsets = [
        synset for synset in synsets if (synset.lexfile() or "") in target_lexfiles
    ]
    selected_synset, selection_tag, wn30_tag, wn30_counts = _select_synset(
        synsets=synsets,
        matched_synsets=matched_synsets,
        target_lexfiles=target_lexfiles,
        query=query,
        wn30_available=wn30_available,
    )
    selected_synset, selection_tag, lookup_case, query, synsets, manual_decision, manual_note = (
        _apply_manual_coco_label_decision(
            label=label,
            selected_synset=selected_synset,
            selection_tag=selection_tag,
            lookup_case=lookup_case,
            query=query,
            synsets=synsets,
            oewn=oewn,
        )
    )
    if manual_decision.startswith("select"):
        objectness_class = _objectness_class(selected_synset.lexfile() or "")
        objectness_gate = "manual_override"
    else:
        selected_synset, selection_tag, objectness_class, objectness_gate = _apply_objectness_gate(
            selected_synset=selected_synset,
            selection_tag=selection_tag,
        )
    selected_lemmas = selected_synset.lemmas() if selected_synset is not None else []
    canonical_surface, canonical_tag, canonical_candidates, canonical_counts = (
        _select_canonical_surface(
            label=label,
            selected_lookup_case=lookup_case,
            selected_query=query,
            selected_synset=selected_synset,
            wn30_available=wn30_available,
        )
    )
    parent_synsets, parent_selection_tag = _immediate_hypernym_parents(selected_synset)
    is_mwe_candidate = _is_mwe_candidate(label)

    return {
        **row,
        "is_mwe_candidate": _bool(is_mwe_candidate),
        "mwe_candidate_status": _mwe_candidate_status(
            is_mwe_candidate=is_mwe_candidate,
            selected_synset=selected_synset,
            selection_tag=selection_tag,
        ),
        "wordnet_source": "oewn",
        "wordnet_version": "2025-plus",
        "wordnet_lexicon_id": OEWN_SPEC,
        "selected_lookup_case": lookup_case,
        "selected_query": query,
        "has_oewn_noun_synset": _bool(bool(synsets)),
        "oewn_synset_count": str(len(synsets)),
        "selected_oewn_synset": selected_synset.id if selected_synset is not None else "",
        "selected_oewn_lexfile": selected_synset.lexfile()
        if selected_synset is not None
        else "",
        "all_oewn_synsets": "|".join(synset.id for synset in synsets),
        "all_oewn_lexfiles": "|".join(
            f"{synset.id}:{synset.lexfile()}:{';'.join(synset.lemmas())}"
            for synset in synsets
        ),
        "target_oewn_lexfiles": "|".join(sorted(target_lexfiles)),
        "matched_oewn_lexfiles": "|".join(
            f"{synset.id}:{synset.lexfile()}:{';'.join(synset.lemmas())}"
            for synset in matched_synsets
        ),
        "synset_lemmas": "|".join(selected_lemmas),
        "canonical_surface": canonical_surface,
        "canonical_selection_tag": canonical_tag,
        "canonical_candidate_lemmas": canonical_candidates,
        "canonical_candidate_lemma_counts": canonical_counts,
        "parent_oewn_synsets": "|".join(synset.id for synset in parent_synsets),
        "parent_oewn_lexfiles": "|".join(
            f"{synset.id}:{synset.lexfile()}" for synset in parent_synsets
        ),
        "parent_lemmas": "|".join(
            f"{synset.id}:{';'.join(synset.lemmas())}" for synset in parent_synsets
        ),
        "parent_selection_tag": parent_selection_tag,
        "selected_oewn_objectness_class": objectness_class,
        "objectness_gate": objectness_gate,
        "manual_decision": manual_decision,
        "manual_decision_note": manual_note,
        "sense_counts_available": _bool(_has_any_counts(synsets)),
        "wn30_available": _bool(wn30_available),
        "wn30_selection_tag": wn30_tag,
        "wn30_lemma_counts": wn30_counts,
        "synset_selection_tag": selection_tag,
        "decision_basis": selection_tag,
    }


def _apply_manual_coco_label_decision(
    label: str,
    selected_synset: wn.Synset | None,
    selection_tag: str,
    lookup_case: str,
    query: str,
    synsets: list[wn.Synset],
    oewn: wn.Wordnet,
) -> tuple[wn.Synset | None, str, str, str, list[wn.Synset], str, str]:
    decision = MANUAL_COCO_LABEL_DECISIONS.get(label)
    if decision is None:
        return selected_synset, selection_tag, lookup_case, query, synsets, "", ""

    manual_synset = _synset_by_id(oewn, decision["synset"])
    note = decision["note"]
    if decision["status"] == "reject":
        return (
            None,
            MANUAL_COCO_REJECTED_TAG,
            lookup_case,
            query,
            synsets,
            f"reject:{decision['synset']}",
            note,
        )

    selected_query = query
    selected_lookup_case = lookup_case
    selected_synsets = synsets
    if not any(synset.id == manual_synset.id for synset in synsets):
        selected_lookup_case = "manual_synset_override"
        selected_synsets = [manual_synset]
    return (
        manual_synset,
        MANUAL_COCO_LABEL_REVIEW_TAG,
        selected_lookup_case,
        selected_query,
        selected_synsets,
        f"select:{manual_synset.id}",
        note,
    )


def _synset_by_id(oewn: wn.Wordnet, synset_id: str) -> wn.Synset:
    try:
        return oewn.synset(synset_id)
    except Exception as exc:
        raise ValueError(f"manual COCO decision references missing synset: {synset_id}") from exc


def _lookup_oewn_synsets(
    label: str,
    oewn: wn.Wordnet,
    morphy: Morphy,
) -> tuple[str, str, list[wn.Synset]]:
    for case, query in _lookup_queries(label):
        synsets = _noun_synsets(oewn, query)
        if synsets:
            return case, query, synsets

    for query in _morphy_queries(label, morphy):
        synsets = _noun_synsets(oewn, query)
        if synsets:
            return "morphy", query, synsets

    return "unresolved", "", []


def _lookup_queries(label: str) -> list[tuple[str, str]]:
    exact = _normalize_query(label)
    separator_variant = _normalize_query(re.sub(r"[-_]+", " ", label))
    joined_variant = re.sub(r"[\s_-]+", "", exact)

    queries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for case, query in [
        ("exact", exact),
        ("separator_variant", separator_variant),
        ("joined_variant", joined_variant),
    ]:
        if query and query not in seen:
            queries.append((case, query))
            seen.add(query)
    return queries


def _morphy_queries(label: str, morphy: Morphy) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for _, base_query in _lookup_queries(label):
        result = morphy(base_query, "n")
        noun_lemmas = result.get("n", set()) if result else set()
        for lemma in sorted(noun_lemmas):
            query = _normalize_query(lemma)
            if query and query not in seen:
                queries.append(query)
                seen.add(query)
    return queries


def _noun_synsets(oewn: wn.Wordnet, query: str) -> list[wn.Synset]:
    return list(oewn.synsets(query, pos="n"))


def _select_synset(
    synsets: list[wn.Synset],
    matched_synsets: list[wn.Synset],
    target_lexfiles: set[str],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str, str]:
    if not synsets:
        return None, "unresolved_no_oewn_noun_synset", "", ""
    if len(synsets) == 1:
        return synsets[0], "single_oewn_noun_synset", "", ""
    if not target_lexfiles:
        selected, wn30_tag, counts = _select_by_wn30_lemma_count(
            synsets, query, wn30_available
        )
        if selected is not None:
            return selected, "selected_by_wn30_lemma_count", wn30_tag, counts
        return None, "ambiguous_no_dataset_evidence", wn30_tag, counts
    if len(matched_synsets) == 1:
        return matched_synsets[0], "selected_by_coco_supercategory_oewn_lexfile", "", ""
    if len(matched_synsets) > 1:
        selected, wn30_tag, counts = _select_by_wn30_lemma_count(
            matched_synsets, query, wn30_available
        )
        if selected is not None:
            return (
                selected,
                "selected_by_wn30_lemma_count_after_coco_lexfile",
                wn30_tag,
                counts,
            )
        return None, "ambiguous_after_coco_supercategory_oewn_lexfile", wn30_tag, counts
    return None, "ambiguous_no_coco_supercategory_oewn_lexfile_match", "", ""


def _select_by_wn30_lemma_count(
    synsets: list[wn.Synset],
    query: str,
    wn30_available: bool,
) -> tuple[wn.Synset | None, str, str]:
    if not wn30_available:
        return None, "wn30_unavailable", ""

    count_rows: list[tuple[wn.Synset, int, str]] = []
    query_key = _lemma_key(query)
    for synset in synsets:
        count, count_note = _sense_key_lemma_count(synset=synset, query_key=query_key)
        count_rows.append((synset, count, f"{synset.id}:{count_note}"))

    counts = "|".join(row[2] for row in count_rows)
    valid_rows = [(synset, count) for synset, count, _ in count_rows if count >= 0]
    if not valid_rows:
        return None, "wn30_mapping_missing", counts

    max_count = max(count for _, count in valid_rows)
    if max_count <= 0:
        return None, "wn30_all_zero", counts

    winners = [synset for synset, count in valid_rows if count == max_count]
    if len(winners) == 1:
        return winners[0], "wn30_unique_max", counts
    return None, "wn30_tie", counts


def _select_canonical_surface(
    *,
    label: str,
    selected_lookup_case: str,
    selected_query: str,
    selected_synset: wn.Synset | None,
    wn30_available: bool,
) -> tuple[str, str, str, str]:
    if selected_synset is None:
        return "", "not_applicable_no_selected_synset", "", ""
    if not wn30_available:
        return "", "ambiguous_wn30_unavailable", "", ""

    source_keys = _canonical_surface_keys(
        label=label,
        selected_lookup_case=selected_lookup_case,
        selected_query=selected_query,
    )
    candidate_lemmas = [
        lemma for lemma in selected_synset.lemmas() if _lemma_key(lemma) in source_keys
    ]
    if not candidate_lemmas:
        return "", "ambiguous_no_label_or_lookup_matched_wordnet_lemma", "", ""
    if len(candidate_lemmas) == 1:
        count = _selected_synset_lemma_count(selected_synset, candidate_lemmas[0])
        return (
            candidate_lemmas[0],
            "selected_single_label_or_lookup_matched_wordnet_lemma",
            candidate_lemmas[0],
            f"{candidate_lemmas[0]}:{count}",
        )

    count_rows = [
        (lemma, _selected_synset_lemma_count(selected_synset, lemma))
        for lemma in candidate_lemmas
    ]
    counts = "|".join(f"{lemma}:{count}" for lemma, count in count_rows)
    valid_rows = [(lemma, count) for lemma, count in count_rows if count >= 0]
    if not valid_rows:
        return (
            "",
            "ambiguous_wn30_mapping_missing",
            "|".join(candidate_lemmas),
            counts,
        )

    max_count = max(count for _, count in valid_rows)
    if max_count <= 0:
        source_label_match = _select_by_source_label_surface(label, candidate_lemmas)
        if source_label_match:
            return (
                source_label_match,
                "selected_by_source_label_surface_after_wn30_all_zero",
                "|".join(candidate_lemmas),
                counts,
            )
        return "", "ambiguous_wn30_all_zero", "|".join(candidate_lemmas), counts

    winners = [lemma for lemma, count in valid_rows if count == max_count]
    if len(winners) != 1:
        source_label_match = _select_by_source_label_surface(label, winners)
        if source_label_match:
            return (
                source_label_match,
                "selected_by_source_label_surface_after_wn30_tie",
                "|".join(candidate_lemmas),
                counts,
            )
        return "", "ambiguous_wn30_tie", "|".join(candidate_lemmas), counts

    return (
        winners[0],
        "selected_by_label_or_lookup_matched_wn30_lemma_count",
        "|".join(candidate_lemmas),
        counts,
    )


def _selected_synset_lemma_count(synset: wn.Synset, lemma_name: str) -> int:
    target_key = _lemma_key(lemma_name)
    count = 0
    mapped = 0
    for sense in synset.senses():
        sense_key = _sense_key_from_oewn_sense_id(sense.id)
        if not sense_key:
            continue
        try:
            lemma = wn30.lemma_from_key(sense_key)
        except Exception:
            continue
        if _lemma_key(lemma.name()) != target_key:
            continue
        mapped += 1
        count += lemma.count()
    if mapped == 0:
        return -1
    return count


def _select_by_source_label_surface(label: str, lemmas: list[str]) -> str:
    label_key = _surface_key(label)
    matches = [lemma for lemma in lemmas if _surface_key(lemma) == label_key]
    if len(matches) == 1:
        return matches[0]
    return ""


def _immediate_hypernym_parents(synset: wn.Synset | None) -> tuple[list[wn.Synset], str]:
    if synset is None:
        return [], "not_applicable_no_selected_synset"

    parents = list(synset.hypernyms())
    if not parents:
        return [], "no_immediate_oewn_hypernym"
    return parents, "selected_all_immediate_oewn_hypernyms"


def _apply_objectness_gate(
    selected_synset: wn.Synset | None,
    selection_tag: str,
) -> tuple[wn.Synset | None, str, str, str]:
    if selected_synset is None:
        return None, selection_tag, "", "not_applicable"
    lexfile = selected_synset.lexfile() or ""
    objectness_class = _objectness_class(lexfile)
    if objectness_class == "object_compatible":
        return selected_synset, selection_tag, objectness_class, "pass"
    if objectness_class == "conditional":
        return None, "ambiguous_objectness_conditional", objectness_class, "manual_check"
    if objectness_class == "hard_conflict":
        return None, "ambiguous_objectness_hard_conflict", objectness_class, "manual_check"
    return None, "ambiguous_objectness_unknown", objectness_class, "manual_check"


def _objectness_class(lexfile: str) -> str:
    if lexfile in OBJECT_COMPATIBLE_LEXFILES:
        return "object_compatible"
    if lexfile in CONDITIONAL_OBJECT_LEXFILES:
        return "conditional"
    if lexfile in HARD_CONFLICT_LEXFILES:
        return "hard_conflict"
    return "unknown"


def _sense_key_lemma_count(synset: wn.Synset, query_key: str) -> tuple[int, str]:
    count = 0
    mapped = 0
    notes: list[str] = []
    for sense in synset.senses():
        sense_key = _sense_key_from_oewn_sense_id(sense.id)
        if not sense_key:
            notes.append(f"{sense.id}=sense_key_missing")
            continue
        try:
            lemma = wn30.lemma_from_key(sense_key)
        except Exception:
            notes.append(f"{sense_key}=wn30_missing")
            continue
        mapped += 1
        if _lemma_key(lemma.name()) == query_key:
            count += lemma.count()
            notes.append(f"{sense_key}:{lemma.synset().name()}:{lemma.count()}")
    if mapped == 0:
        return -1, "wn30_missing"
    return count, ";".join(notes)


def _sense_key_from_oewn_sense_id(sense_id: str) -> str:
    match = re.match(r"^oewn-(.+)__(\d)\.(\d\d)\.(\d\d)\.\.$", sense_id)
    if match is None:
        return ""
    lemma, ss_type, lex_filenum, lex_id = match.groups()
    return f"{lemma}%{ss_type}:{lex_filenum}:{lex_id}::"


def _check_wn30_available() -> bool:
    try:
        wn30.synsets("dog", pos=wn30.NOUN)
    except LookupError:
        return False
    return True


def _normalize_query(label: str) -> str:
    return " ".join(label.strip().lower().split())


def _lemma_key(text: str) -> str:
    return re.sub(r"[\s_-]+", "", text.strip().lower())


def _surface_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _canonical_surface_keys(
    *,
    label: str,
    selected_lookup_case: str,
    selected_query: str,
) -> set[str]:
    # Canonical candidates are WordNet/OEWN lemmas that are form-supported by
    # the original visual source label or by the actual OEWN lookup query that
    # resolved the label. Separator differences are ignored, but unrelated
    # synset lemmas are not admitted.
    keys = {_lemma_key(label)}
    if selected_lookup_case == "morphy":
        keys.add(_lemma_key(selected_query))
    return {key for key in keys if key}


def _is_mwe_candidate(label: str) -> bool:
    return len(re.split(r"[\s_-]+", label.strip())) >= 2


def _mwe_candidate_status(
    is_mwe_candidate: bool,
    selected_synset: wn.Synset | None,
    selection_tag: str,
) -> str:
    if not is_mwe_candidate:
        return "not_mwe"
    if selected_synset is not None:
        return "selected"
    if selection_tag == MANUAL_COCO_REJECTED_TAG:
        return "rejected"
    if selection_tag.startswith("unresolved"):
        return "unresolved"
    if "conflict" in selection_tag:
        return "conflict"
    if "report" in selection_tag:
        return "report"
    return "ambiguous"


def _has_any_counts(synsets: list[wn.Synset]) -> bool:
    for synset in synsets:
        for sense in synset.senses():
            if sense.counts():
                return True
    return False


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _summarize(rows: list[dict[str, str]]) -> dict[str, int]:
    return {
        "rows": len(rows),
        "mwe_candidate_rows": sum(row["is_mwe_candidate"] == "true" for row in rows),
        "oewn_matched_rows": sum(row["has_oewn_noun_synset"] == "true" for row in rows),
        "selected_oewn_rows": sum(bool(row["selected_oewn_synset"]) for row in rows),
        "single_synset_selected_rows": sum(
            row["synset_selection_tag"] == "single_oewn_noun_synset" for row in rows
        ),
        "lexfile_selected_rows": sum(
            row["synset_selection_tag"]
            == "selected_by_coco_supercategory_oewn_lexfile"
            for row in rows
        ),
        "manual_selected_rows": sum(
            row["synset_selection_tag"] == MANUAL_COCO_LABEL_REVIEW_TAG
            for row in rows
        ),
        "manual_rejected_rows": sum(
            row["synset_selection_tag"] == MANUAL_COCO_REJECTED_TAG
            for row in rows
        ),
        "wn30_selected_rows": sum(
            row["synset_selection_tag"].startswith("selected_by_wn30_lemma_count")
            for row in rows
        ),
        "canonical_selected_rows": sum(bool(row["canonical_surface"]) for row in rows),
        "canonical_ambiguous_rows": sum(
            row["selected_oewn_synset"] != "" and not row["canonical_surface"]
            for row in rows
        ),
        "parent_evidence_rows": sum(bool(row["parent_oewn_synsets"]) for row in rows),
        "ambiguous_oewn_rows": sum(
            row["has_oewn_noun_synset"] == "true" and not row["selected_oewn_synset"]
            and row["synset_selection_tag"] != MANUAL_COCO_REJECTED_TAG
            for row in rows
        ),
        "rejected_oewn_rows": sum(
            row["synset_selection_tag"] == MANUAL_COCO_REJECTED_TAG
            for row in rows
        ),
        "unresolved_oewn_rows": sum(row["has_oewn_noun_synset"] == "false" for row in rows),
        "rows_with_oewn_sense_counts": sum(
            row["sense_counts_available"] == "true" for row in rows
        ),
        "wn30_available_rows": sum(row["wn30_available"] == "true" for row in rows),
    }


if __name__ == "__main__":
    main()
