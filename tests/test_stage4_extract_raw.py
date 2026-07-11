from pathlib import Path
import importlib.util
import os
import tempfile
import unittest
import uuid

from gpic_concepts_v1.io_jsonl import iter_jsonl, write_jsonl
from gpic_concepts_v1.schema import MISSING_SOURCE_MENTION_ID
from gpic_concepts_v1.stage4_extract_raw import (
    _ActionLookupResult,
    _ObjectLookupResult,
    _PrepositionMweEntry,
    _build_preposition_mwe_index,
    _lookup_oewn_verb_synsets,
    _with_selected_synset,
    Stage4SynsetAmbiguityError,
    extract_raw_concepts_from_doc,
    extract_raw_concepts_from_stage3_record,
    load_gpic_action_inventory,
    load_gpic_object_inventory,
    run_stage4_extract_raw,
)
from gpic_concepts_v1.stage3_annotate import (
    DEFAULT_STAGE3_MODEL,
    iter_annotated_docs_from_rows,
    iter_stage3_records_from_rows,
    make_stage3_nlp,
    spacy,
)


def token(
    i: int,
    text: str,
    lemma: str,
    pos: str,
    dep: str,
    head_i: int,
    *,
    tag: str = "NN",
) -> dict[str, object]:
    return {
        "i": i,
        "text": text,
        "lemma": lemma,
        "pos": pos,
        "tag": tag,
        "morph": "",
        "dep": dep,
        "head_i": head_i,
        "head_text": "",
        "char_start": i * 2,
        "char_end": i * 2 + len(text),
        "whitespace": " ",
    }


def chunk(
    text: str,
    root_i: int,
    start: int,
    end: int,
    root_text: str,
) -> dict[str, object]:
    return {
        "text": text,
        "root_i": root_i,
        "root_text": root_text,
        "root_lemma": root_text.lower(),
        "root_pos": "NOUN",
        "root_tag": "NN",
        "root_dep": "dep",
        "root_head_i": 0,
        "root_head_text": "",
        "token_start": start,
        "token_end": end,
        "char_start": start * 2,
        "char_end": end * 2,
    }


class Stage4ExtractRawTest(unittest.TestCase):
    def test_extracts_objects_attributes_quantity_action_and_roles(self) -> None:
        record = {
            "caption_id": "c1",
            "caption": "Two brown dogs chase a ball.",
            "tokens": [
                token(0, "Two", "two", "NUM", "nummod", 2, tag="CD"),
                token(1, "brown", "brown", "ADJ", "amod", 2, tag="JJ"),
                token(2, "dogs", "dog", "NOUN", "nsubj", 3, tag="NNS"),
                token(3, "chase", "chase", "VERB", "ROOT", 3, tag="VBP"),
                token(4, "a", "a", "DET", "det", 5, tag="DT"),
                token(5, "ball", "ball", "NOUN", "dobj", 3),
            ],
            "noun_chunks": [
                chunk("Two brown dogs", 2, 0, 3, "dogs"),
                chunk("a ball", 5, 4, 6, "ball"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
        )
        mentions = [mention.to_dict() for mention in result.raw_mentions]
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertEqual(
            [(m["mention_type"], m["lemma"], m["rule_id"]) for m in mentions],
            [
                ("object", "dog", "R12"),
                ("quantity", "two", "R14"),
                ("attribute", "brown", "R13"),
                ("object", "ball", "R12"),
                ("action", "chase", "R15"),
            ],
        )
        self.assertIn(("has_quantity", "has_quantity", "R14"), _edge_sig(edges))
        self.assertIn(("has_attribute", "has_attribute", "R13"), _edge_sig(edges))
        self.assertIn(("event_role", "agent", "R16"), _edge_sig(edges))
        self.assertIn(("event_role", "patient", "R17"), _edge_sig(edges))

    def test_ambiguous_object_synset_stops_raw_extraction(self) -> None:
        record = {
            "caption_id": "c-ambiguous",
            "caption": "A bat.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "bat", "bat", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("A bat", 1, 0, 2, "bat")],
        }

        with self.assertRaises(Stage4SynsetAmbiguityError):
            extract_raw_concepts_from_stage3_record(
                record,
                object_lookup=fake_ambiguous_object_lookup,
            )

    def test_gpic_object_inventory_lookup_drives_object_selection(self) -> None:
        record = {
            "caption_id": "c-inventory",
            "caption": "A brown dog.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 2, tag="DT"),
                token(1, "brown", "brown", "ADJ", "amod", 2, tag="JJ"),
                token(2, "dog", "dog", "NOUN", "ROOT", 2),
            ],
            "noun_chunks": [chunk("A brown dog", 2, 0, 3, "dog")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            inventory_path = tmp_path / "observed_object_span_inventory.tsv"
            inventory_path.write_text(
                "\t".join(
                    [
                        "span_key",
                        "observed_surface",
                        "decision_status",
                        "decision_reason",
                        "selected_lookup_case",
                        "selected_query",
                        "all_oewn_synsets",
                        "all_oewn_lexfiles",
                        "selected_oewn_synset",
                        "selected_oewn_lexfile",
                        "objectness_gate",
                        "synset_lemmas",
                        "parent_oewn_synsets",
                        "parent_oewn_lexfiles",
                        "parent_lemmas",
                        "parent_selection_tag",
                        "canonical_surface",
                        "canonical_label_key",
                        "canonical_selection_tag",
                        "canonical_candidate_lemmas",
                        "canonical_candidate_lemma_counts",
                        "google_ngram_candidate_surfaces",
                        "google_ngram_candidate_mean_frequencies",
                        "synset_selection_tag",
                        "wn30_lemma_counts",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "brown dog",
                        "brown dog",
                        "chosen",
                        "selected_object_compatible",
                        "test_inventory",
                        "brown dog",
                        "fake-brown-dog-n",
                        "noun.animal",
                        "fake-brown-dog-n",
                        "noun.animal",
                        "object_compatible",
                        "brown dog|dog",
                        "fake-parent-n",
                        "fake-parent-n:noun.animal",
                        "fake-parent-n:canine",
                        "selected_all_immediate_oewn_hypernyms",
                        "dog",
                        "dog",
                        "selected_by_wn30_lemma_count_unique_positive_max",
                        "dog",
                        "dog:42",
                        "",
                        "",
                        "manual_select",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = extract_raw_concepts_from_stage3_record(
                record,
                object_lookup=load_gpic_object_inventory(inventory_path),
            )
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

        object_mentions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "object"
        ]
        self.assertEqual(len(object_mentions), 1)
        self.assertEqual(object_mentions[0]["text"], "dog")
        self.assertEqual(object_mentions[0]["source_detail"]["lookup_span_surface"], "brown dog")
        self.assertEqual(object_mentions[0]["source_detail"]["lookup_token_indices"], [1, 2])
        self.assertEqual(object_mentions[0]["source_detail"]["selected_token_indices"], [2])
        self.assertEqual(
            object_mentions[0]["source_detail"]["selected_oewn_synset"],
            "fake-brown-dog-n",
        )
        self.assertEqual(
            object_mentions[0]["source_detail"]["parent_oewn_synsets"],
            ["fake-parent-n"],
        )
        self.assertEqual(
            object_mentions[0]["source_detail"]["parent_selection_tag"],
            "selected_all_immediate_oewn_hypernyms",
        )
        self.assertEqual(object_mentions[0]["source_detail"]["canonical_surface"], "dog")
        self.assertEqual(
            object_mentions[0]["source_detail"]["canonical_selection_tag"],
            "selected_by_wn30_lemma_count_unique_positive_max",
        )

    def test_lookup_span_core_suffix_leaves_modifier_as_attribute(self) -> None:
        record = {
            "caption_id": "c-core-suffix",
            "caption": "A black top.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 2, tag="DT"),
                token(1, "black", "black", "ADJ", "amod", 2, tag="JJ"),
                token(2, "top", "top", "NOUN", "ROOT", 2),
            ],
            "noun_chunks": [chunk("A black top", 2, 0, 3, "top")],
        }
        synset = FakeSynset("fake-top-n", "noun.artifact", ["top"])

        def object_lookup(surface: str) -> _ObjectLookupResult | None:
            if surface != "black top":
                return None
            return _ObjectLookupResult(
                lookup_case="test",
                query=surface,
                synsets=(synset,),
                selected_synset=synset,
                synset_selection_tag="manual_select",
                wn30_lemma_counts="",
                objectness_gate="object_compatible",
                decision_status="chosen",
                canonical_surface="top",
                canonical_label_key="top",
                canonical_selection_tag="selected_single_observed_variant_matched_synset_lemma",
            )

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=object_lookup,
        )

        mentions = [mention.to_dict() for mention in result.raw_mentions]
        object_mentions = [m for m in mentions if m["mention_type"] == "object"]
        attribute_mentions = [m for m in mentions if m["mention_type"] == "attribute"]
        self.assertEqual(object_mentions[0]["text"], "top")
        self.assertEqual(object_mentions[0]["source_detail"]["lookup_span_surface"], "black top")
        self.assertEqual(object_mentions[0]["source_detail"]["selected_token_indices"], [2])
        self.assertEqual([m["text"] for m in attribute_mentions], ["black"])
        self.assertIn(("has_attribute", "has_attribute", "R13"), _edge_sig([e.to_dict() for e in result.raw_edges]))

    def test_inventory_canonical_ambiguity_requires_manual_resolution(self) -> None:
        record = {
            "caption_id": "c-canonical-ambiguous",
            "caption": "The sun shines.",
            "tokens": [
                token(0, "The", "the", "DET", "det", 1, tag="DT"),
                token(1, "sun", "sun", "NOUN", "nsubj", 2),
                token(2, "shines", "shine", "VERB", "ROOT", 2),
            ],
            "noun_chunks": [chunk("The sun", 1, 0, 2, "sun")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            inventory_path = tmp_path / "observed_object_span_inventory.tsv"
            inventory_path.write_text(
                "\t".join(
                    [
                        "span_key",
                        "observed_surface",
                        "decision_status",
                        "decision_reason",
                        "selected_lookup_case",
                        "selected_query",
                        "all_oewn_synsets",
                        "all_oewn_lexfiles",
                        "selected_oewn_synset",
                        "selected_oewn_lexfile",
                        "objectness_gate",
                        "synset_lemmas",
                        "canonical_surface",
                        "canonical_label_key",
                        "canonical_selection_tag",
                        "canonical_candidate_lemmas",
                        "canonical_candidate_lemma_counts",
                        "synset_selection_tag",
                        "wn30_lemma_counts",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "sun",
                        "sun",
                        "chosen",
                        "selected_object_compatible",
                        "exact",
                        "sun",
                        "fake-sun-n",
                        "noun.object",
                        "fake-sun-n",
                        "noun.object",
                        "object_compatible",
                        "sun|Sun",
                        "",
                        "",
                        "ambiguous_wn30_tie_google_ngram_evidence_missing",
                        "sun|Sun",
                        "sun:42|Sun:42",
                        "selected_by_wn30_lemma_count",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(Stage4SynsetAmbiguityError) as caught:
                extract_raw_concepts_from_stage3_record(
                    record,
                    object_lookup=load_gpic_object_inventory(inventory_path),
                )
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

        self.assertIn("canonical_surface=''", str(caught.exception))
        self.assertIn("ambiguous_wn30_tie_google_ngram_evidence_missing", str(caught.exception))

    def test_conditional_inventory_synset_requires_manual_resolution(self) -> None:
        record = {
            "caption_id": "c-conditional",
            "caption": "A scene.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "scene", "scene", "NOUN", "ROOT", 1),
            ],
            "noun_chunks": [chunk("A scene", 1, 0, 2, "scene")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            inventory_path = tmp_path / "observed_object_span_inventory.tsv"
            inventory_path.write_text(
                "\t".join(
                    [
                        "span_key",
                        "observed_surface",
                        "decision_status",
                        "decision_reason",
                        "selected_lookup_case",
                        "selected_query",
                        "all_oewn_synsets",
                        "all_oewn_lexfiles",
                        "selected_oewn_synset",
                        "selected_oewn_lexfile",
                        "objectness_gate",
                        "synset_lemmas",
                        "synset_selection_tag",
                        "wn30_lemma_counts",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "scene",
                        "scene",
                        "needs_manual",
                        "manual_objectness_required",
                        "test_inventory",
                        "scene",
                        "fake-scene-n",
                        "noun.location",
                        "fake-scene-n",
                        "noun.location",
                        "conditional",
                        "scene",
                        "selected_by_wn30_lemma_count",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(Stage4SynsetAmbiguityError):
                extract_raw_concepts_from_stage3_record(
                    record,
                    object_lookup=load_gpic_object_inventory(inventory_path),
                )
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

    def test_excluded_inventory_row_is_counted_with_status_metadata(self) -> None:
        record = {
            "caption_id": "c-excluded-counted",
            "caption": "Muted colors.",
            "tokens": [
                token(0, "Muted", "muted", "ADJ", "amod", 1, tag="JJ"),
                token(1, "colors", "color", "NOUN", "ROOT", 1, tag="NNS"),
            ],
            "noun_chunks": [chunk("Muted colors", 1, 0, 2, "colors")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            inventory_path = tmp_path / "observed_object_span_inventory.tsv"
            inventory_path.write_text(
                "\t".join(
                    [
                        "span_key",
                        "observed_surface",
                        "decision_status",
                        "decision_reason",
                        "selected_lookup_case",
                        "selected_query",
                        "all_oewn_synsets",
                        "all_oewn_lexfiles",
                        "selected_oewn_synset",
                        "selected_oewn_lexfile",
                        "objectness_gate",
                        "synset_lemmas",
                        "synset_selection_tag",
                        "wn30_lemma_counts",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "colors",
                        "colors",
                        "excluded",
                        "resolved_excluded_visual_attribute_not_object_inventory_unit",
                        "test_inventory",
                        "color",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "unresolved_no_oewn_noun_synset",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = extract_raw_concepts_from_stage3_record(
                record,
                object_lookup=load_gpic_object_inventory(inventory_path),
            )
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

        object_mentions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "object"
        ]
        self.assertEqual(len(object_mentions), 1)
        self.assertEqual(object_mentions[0]["text"], "colors")
        self.assertEqual(object_mentions[0]["source_detail"]["decision_status"], "excluded")
        self.assertEqual(
            object_mentions[0]["source_detail"]["decision_reason"],
            "resolved_excluded_visual_attribute_not_object_inventory_unit",
        )
        self.assertFalse(object_mentions[0]["source_detail"]["has_oewn_noun_synset"])

    def test_plural_common_noun_prefers_head_lemma_lookup_before_exact_surface(self) -> None:
        record = {
            "caption_id": "c-plural",
            "caption": "Two men stand.",
            "tokens": [
                token(0, "Two", "two", "NUM", "nummod", 1, tag="CD"),
                token(1, "men", "man", "NOUN", "nsubj", 2, tag="NNS"),
                token(2, "stand", "stand", "VERB", "ROOT", 2, tag="VBP"),
            ],
            "noun_chunks": [chunk("Two men", 1, 0, 2, "men")],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_plural_exact_polluted_lookup,
        )

        object_mentions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "object"
        ]
        self.assertEqual(len(object_mentions), 1)
        self.assertEqual(object_mentions[0]["text"], "men")
        self.assertEqual(object_mentions[0]["lemma"], "man")
        self.assertEqual(object_mentions[0]["source_detail"]["lookup_query"], "man")

    def test_joined_variant_lookup_requires_manual_even_when_object_compatible(self) -> None:
        synset = FakeSynset("fake-blackshirt-n", "noun.person", ["Blackshirt"])

        lookup = _with_selected_synset("joined_variant", "blackshirt", (synset,))

        self.assertEqual(lookup.decision_status, "needs_manual")
        self.assertEqual(lookup.decision_reason, "manual_joined_variant_required")

    def test_exact_lookup_can_still_be_chosen_for_object_compatible_synset(self) -> None:
        synset = FakeSynset("fake-trash-can-n", "noun.artifact", ["trash_can"])

        lookup = _with_selected_synset("exact", "trash can", (synset,))

        self.assertEqual(lookup.decision_status, "chosen")
        self.assertEqual(lookup.decision_reason, "selected_object_compatible")

    def test_left_expanding_span_skips_determiner_start(self) -> None:
        record = {
            "caption_id": "c-det-start",
            "caption": "A man stands.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "man", "man", "NOUN", "nsubj", 2),
                token(2, "stands", "stand", "VERB", "ROOT", 2, tag="VBZ"),
            ],
            "noun_chunks": [chunk("A man", 1, 0, 2, "man")],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_determiner_start_polluted_lookup,
        )

        object_mentions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "object"
        ]
        self.assertEqual(len(object_mentions), 1)
        self.assertEqual(object_mentions[0]["text"], "man")
        self.assertEqual(object_mentions[0]["source_detail"]["lookup_query"], "man")

    def test_prepositional_object_is_not_action_patient(self) -> None:
        record = {
            "caption_id": "c2",
            "caption": "A dog sits on a bench.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "nsubj", 2),
                token(2, "sits", "sit", "VERB", "ROOT", 2, tag="VBZ"),
                token(3, "on", "on", "ADP", "prep", 2, tag="IN"),
                token(4, "a", "a", "DET", "det", 5, tag="DT"),
                token(5, "bench", "bench", "NOUN", "pobj", 3),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("a bench", 5, 4, 6, "bench"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("event_role", "agent", "R16"), _edge_sig(edges))
        self.assertNotIn(("event_role", "patient", "R17"), _edge_sig(edges))
        self.assertNotIn(("relation", "on", "R18"), _edge_sig(edges))

    def test_selected_phrasal_action_prep_creates_patient_and_suppresses_relation(self) -> None:
        record = {
            "caption_id": "c-look-at",
            "caption": "A man look at a dog.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "man", "man", "NOUN", "nsubj", 2),
                token(2, "look", "look", "VERB", "ROOT", 2, tag="VB"),
                token(3, "at", "at", "ADP", "prep", 2, tag="IN"),
                token(4, "a", "a", "DET", "det", 5, tag="DT"),
                token(5, "dog", "dog", "NOUN", "pobj", 3),
            ],
            "noun_chunks": [
                chunk("A man", 1, 0, 2, "man"),
                chunk("a dog", 5, 4, 6, "dog"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            action_lookup=fake_action_lookup,
        )
        mentions = [mention.to_dict() for mention in result.raw_mentions]
        edges = [edge.to_dict() for edge in result.raw_edges]

        action_mentions = [
            mention for mention in mentions if mention["mention_type"] == "action"
        ]
        self.assertEqual(action_mentions[0]["text"], "look at")
        self.assertEqual(
            action_mentions[0]["source_detail"]["selected_token_indices"],
            [2, 3],
        )
        self.assertIn(("event_role", "agent", "R16"), _edge_sig(edges))
        self.assertIn(("event_role", "patient", "R17"), _edge_sig(edges))
        self.assertNotIn(("relation", "at", "R18"), _edge_sig(edges))

    def test_action_prep_before_verb_is_not_phrasal_action(self) -> None:
        record = {
            "caption_id": "c-frame-fronted-pp",
            "caption": "In the road, a man frame a dog.",
            "tokens": [
                token(0, "In", "in", "ADP", "prep", 5, tag="IN"),
                token(1, "the", "the", "DET", "det", 2, tag="DT"),
                token(2, "road", "road", "NOUN", "pobj", 0),
                token(3, ",", ",", "PUNCT", "punct", 5, tag=","),
                token(4, "man", "man", "NOUN", "nsubj", 5),
                token(5, "frame", "frame", "VERB", "ROOT", 5, tag="VBP"),
                token(6, "a", "a", "DET", "det", 7, tag="DT"),
                token(7, "dog", "dog", "NOUN", "dobj", 5),
            ],
            "noun_chunks": [
                chunk("the road", 2, 1, 3, "road"),
                chunk("a man", 4, 4, 5, "man"),
                chunk("a dog", 7, 6, 8, "dog"),
            ],
        }

        def frame_in_lookup(surface: str) -> _ActionLookupResult | None:
            key = " ".join(surface.strip().lower().split())
            if key != "frame in":
                return None
            synset = FakeSynset("fake-frame-in-v", "verb.contact", ["frame_in"])
            return _ActionLookupResult(
                lookup_case="test",
                query=key,
                synsets=(synset,),
                selected_synset=synset,
                synset_selection_tag="test_single_verb_synset",
                wn30_lemma_counts="",
                decision_status="chosen",
                decision_reason="selected_verb_synset",
            )

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            action_lookup=frame_in_lookup,
        )
        action_mentions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "action"
        ]

        self.assertEqual(action_mentions[0]["text"], "frame")
        self.assertEqual(action_mentions[0]["source_detail"]["selected_token_indices"], [5])
        self.assertEqual(action_mentions[0]["source_detail"]["prep_token_indices"], [])

    def test_ambiguous_action_synset_blocks_raw_extraction(self) -> None:
        record = {
            "caption_id": "c-ambiguous-action",
            "caption": "A sign marked a road.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "sign", "sign", "NOUN", "nsubj", 2),
                token(2, "marked", "mark", "VERB", "ROOT", 2, tag="VBD"),
                token(3, "a", "a", "DET", "det", 4, tag="DT"),
                token(4, "road", "road", "NOUN", "dobj", 2),
            ],
            "noun_chunks": [
                chunk("A sign", 1, 0, 2, "sign"),
                chunk("a road", 4, 3, 5, "road"),
            ],
        }

        with self.assertRaises(Stage4SynsetAmbiguityError):
            extract_raw_concepts_from_stage3_record(
                record,
                object_lookup=fake_object_lookup,
                action_lookup=fake_ambiguous_action_lookup,
            )

    def test_action_lookup_requires_exact_surface_lemma_before_morphy(self) -> None:
        sit_synset = FakeSynset("fake-sit-v", "verb.contact", ["sit"])
        oewn = FakeOewn(
            {
                ("sitting", "v"): (sit_synset,),
                ("sit", "v"): (sit_synset,),
            }
        )
        morphy = FakeMorphy({"sitting": {"v": {"sit"}}})

        lookup = _lookup_oewn_verb_synsets("sitting", oewn, morphy)

        self.assertEqual(lookup.lookup_case, "verb_head_morphy")
        self.assertEqual(lookup.query, "sit")
        self.assertEqual(lookup.selected_synset, sit_synset)
        self.assertEqual(lookup.decision_status, "chosen")

    def test_action_lookup_keeps_multiple_morphy_hits_manual(self) -> None:
        shin_synset = FakeSynset("fake-shin-v", "verb.motion", ["shin"])
        shine_synset = FakeSynset("fake-shine-v", "verb.weather", ["shine"])
        oewn = FakeOewn(
            {
                ("shining", "v"): (shin_synset, shine_synset),
                ("shin", "v"): (shin_synset,),
                ("shine", "v"): (shine_synset,),
            }
        )
        morphy = FakeMorphy({"shining": {"v": {"shin", "shine"}}})

        lookup = _lookup_oewn_verb_synsets("shining", oewn, morphy)

        self.assertEqual(lookup.lookup_case, "verb_head_morphy_ambiguous")
        self.assertEqual(lookup.query, "shin|shine")
        self.assertEqual(lookup.selected_synset, None)
        self.assertEqual(lookup.decision_status, "needs_manual")
        self.assertEqual(lookup.decision_reason, "manual_action_morphy_required")

    def test_gpic_action_inventory_lookup_drives_action_selection(self) -> None:
        record = {
            "caption_id": "c-action-inventory",
            "caption": "A light shines.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "light", "light", "NOUN", "nsubj", 2),
                token(2, "shines", "shine", "VERB", "ROOT", 2, tag="VBZ"),
            ],
            "noun_chunks": [chunk("A light", 1, 0, 2, "light")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            inventory_path = tmp_path / "observed_action_inventory.tsv"
            inventory_path.write_text(
                "\t".join(
                    [
                        "span_key",
                        "observed_surface",
                        "decision_status",
                        "decision_reason",
                        "selected_lookup_case",
                        "selected_query",
                        "all_oewn_synsets",
                        "all_oewn_lexfiles",
                        "selected_oewn_synset",
                        "selected_oewn_lexfile",
                        "synset_lemmas",
                        "synset_selection_tag",
                        "wn30_lemma_counts",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "shines",
                        "shines",
                        "chosen",
                        "manual_action_synset_selected",
                        "manual_action_inventory_resolution",
                        "shine",
                        "fake-shine-v",
                        "verb.weather",
                        "fake-shine-v",
                        "verb.weather",
                        "shine",
                        "manual_select",
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = extract_raw_concepts_from_stage3_record(
                record,
                object_lookup=fake_object_lookup,
                action_lookup=load_gpic_action_inventory(inventory_path),
            )
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

        actions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "action"
        ]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["lemma"], "shine")
        self.assertEqual(
            actions[0]["source_detail"]["selected_oewn_synset"],
            "fake-shine-v",
        )

    def test_relation_requires_adp_head_and_pobj_to_be_existing_objects(self) -> None:
        record = {
            "caption_id": "c3",
            "caption": "A dog with a collar.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "ROOT", 1),
                token(2, "with", "with", "ADP", "prep", 1, tag="IN"),
                token(3, "a", "a", "DET", "det", 4, tag="DT"),
                token(4, "collar", "collar", "NOUN", "pobj", 2),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("a collar", 4, 3, 5, "collar"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "with", "R18"), _edge_sig(edges))

    def test_preposition_mwe_relation_uses_canonical_span_and_suppresses_single_adp(self) -> None:
        record = {
            "caption_id": "c-front-of",
            "caption": "A dog in front of a house.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "ROOT", 1),
                token(2, "in", "in", "ADP", "prep", 1, tag="IN"),
                token(3, "front", "front", "NOUN", "pobj", 2),
                token(4, "of", "of", "ADP", "prep", 3, tag="IN"),
                token(5, "a", "a", "DET", "det", 6, tag="DT"),
                token(6, "house", "house", "NOUN", "pobj", 4),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("front", 3, 3, 4, "front"),
                chunk("a house", 6, 5, 7, "house"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        mentions = [mention.to_dict() for mention in result.raw_mentions]
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertNotIn(
            ("object", "front", "R12"),
            {(m["mention_type"], m["lemma"], m["rule_id"]) for m in mentions},
        )
        self.assertIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        self.assertNotIn(("relation", "of", "R18"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["rule_id"] == "R18.1")
        self.assertEqual(relation["source_detail"]["relation_components"], ["in", "front", "of"])
        self.assertEqual(relation["source_detail"]["matched_token_indices"], [2, 3, 4])

    def test_preposition_mwe_index_preserves_longest_overlap_policy(self) -> None:
        record = {
            "caption_id": "c-front-of-indexed",
            "caption": "A dog in front of a house.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "ROOT", 1),
                token(2, "in", "in", "ADP", "prep", 1, tag="IN"),
                token(3, "front", "front", "NOUN", "pobj", 2),
                token(4, "of", "of", "ADP", "prep", 3, tag="IN"),
                token(5, "a", "a", "DET", "det", 6, tag="DT"),
                token(6, "house", "house", "NOUN", "pobj", 4),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("front", 3, 3, 4, "front"),
                chunk("a house", 6, 5, 7, "house"),
            ],
        }
        lookup = _build_preposition_mwe_index((front_of_entry(), in_front_of_entry()))

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=lookup,
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["rule_id"] == "R18.1")
        self.assertEqual(relation["source_detail"]["matched_token_indices"], [2, 3, 4])

    def test_action_attached_preposition_mwe_single_source_creates_relation(self) -> None:
        record = {
            "caption_id": "c-stand-front-of",
            "caption": "Dogs stand in front of a house.",
            "tokens": [
                token(0, "Dogs", "dog", "NOUN", "nsubj", 1, tag="NNS"),
                token(1, "stand", "stand", "VERB", "ROOT", 1, tag="VBP"),
                token(2, "in", "in", "ADP", "prep", 1, tag="IN"),
                token(3, "front", "front", "NOUN", "pobj", 2),
                token(4, "of", "of", "ADP", "prep", 3, tag="IN"),
                token(5, "a", "a", "DET", "det", 6, tag="DT"),
                token(6, "house", "house", "NOUN", "pobj", 4),
            ],
            "noun_chunks": [
                chunk("Dogs", 0, 0, 1, "Dogs"),
                chunk("front", 3, 3, 4, "front"),
                chunk("a house", 6, 5, 7, "house"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["edge_type"] == "relation")
        self.assertEqual(relation["source_detail"]["source_resolution"], "head_direct_object_child")
        self.assertEqual(relation["source_detail"]["source_dep"], "nsubj")
        self.assertEqual(relation["source_detail"]["candidate_source_count"], 1)

    def test_action_attached_preposition_mwe_nsubjpass_source_creates_relation(self) -> None:
        record = {
            "caption_id": "c-parked-front-of",
            "caption": "A van is parked in front of a house.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "van", "van", "NOUN", "nsubjpass", 3),
                token(2, "is", "be", "AUX", "auxpass", 3, tag="VBZ"),
                token(3, "parked", "park", "VERB", "ROOT", 3, tag="VBN"),
                token(4, "in", "in", "ADP", "prep", 3, tag="IN"),
                token(5, "front", "front", "NOUN", "pobj", 4),
                token(6, "of", "of", "ADP", "prep", 5, tag="IN"),
                token(7, "a", "a", "DET", "det", 8, tag="DT"),
                token(8, "house", "house", "NOUN", "pobj", 6),
            ],
            "noun_chunks": [
                chunk("A van", 1, 0, 2, "van"),
                chunk("front", 5, 5, 6, "front"),
                chunk("a house", 8, 7, 9, "house"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["edge_type"] == "relation")
        self.assertEqual(relation["source_detail"]["source_resolution"], "head_direct_object_child")
        self.assertEqual(relation["source_detail"]["source_dep"], "nsubjpass")
        self.assertEqual(relation["source_detail"]["candidate_source_count"], 1)

    def test_action_attached_preposition_mwe_attr_source_creates_relation(self) -> None:
        record = {
            "caption_id": "c-screen-front-of",
            "caption": "In front of a house, there is a screen.",
            "tokens": [
                token(0, "In", "in", "ADP", "prep", 7, tag="IN"),
                token(1, "front", "front", "NOUN", "pobj", 0),
                token(2, "of", "of", "ADP", "prep", 1, tag="IN"),
                token(3, "a", "a", "DET", "det", 4, tag="DT"),
                token(4, "house", "house", "NOUN", "pobj", 2),
                token(5, ",", ",", "PUNCT", "punct", 7, tag=","),
                token(6, "there", "there", "PRON", "expl", 7, tag="EX"),
                token(7, "is", "be", "AUX", "ROOT", 7, tag="VBZ"),
                token(8, "a", "a", "DET", "det", 9, tag="DT"),
                token(9, "screen", "screen", "NOUN", "attr", 7),
            ],
            "noun_chunks": [
                chunk("front", 1, 1, 2, "front"),
                chunk("a house", 4, 3, 5, "house"),
                chunk("a screen", 9, 8, 10, "screen"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["edge_type"] == "relation")
        self.assertEqual(relation["source_detail"]["source_resolution"], "head_direct_object_child")
        self.assertEqual(relation["source_detail"]["source_dep"], "attr")
        self.assertEqual(relation["source_detail"]["candidate_source_count"], 1)

    def test_aux_attached_preposition_mwe_nsubj_source_creates_relation(self) -> None:
        record = {
            "caption_id": "c-legs-out-of-focus",
            "caption": "The swimmer's legs are out of focus.",
            "tokens": [
                token(0, "The", "the", "DET", "det", 2, tag="DT"),
                token(1, "swimmer", "swimmer", "NOUN", "poss", 2),
                token(2, "legs", "leg", "NOUN", "nsubj", 3, tag="NNS"),
                token(3, "are", "be", "AUX", "ROOT", 3, tag="VBP"),
                token(4, "out", "out", "ADP", "prep", 3, tag="IN"),
                token(5, "of", "of", "ADP", "prep", 4, tag="IN"),
                token(6, "focus", "focus", "NOUN", "pobj", 5),
            ],
            "noun_chunks": [
                chunk("The swimmer's legs", 2, 0, 3, "legs"),
                chunk("focus", 6, 6, 7, "focus"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(out_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertIn(("relation", "out of", "R18.1"), _edge_sig(edges))
        relation = next(edge for edge in edges if edge["rule_id"] == "R18.1")
        self.assertEqual(relation["source_detail"]["source_resolution"], "head_direct_object_child")
        self.assertEqual(relation["source_detail"]["source_dep"], "nsubj")
        self.assertEqual(relation["source_detail"]["candidate_source_count"], 1)

    def test_preposition_mwe_missing_source_creates_ambiguous_candidate(self) -> None:
        record = {
            "caption_id": "c-standing-front-of",
            "caption": "A man speaks standing in front of a wall.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "man", "man", "NOUN", "nsubj", 2),
                token(2, "speaks", "speak", "VERB", "ROOT", 2, tag="VBZ"),
                token(3, "standing", "stand", "VERB", "advcl", 2, tag="VBG"),
                token(4, "in", "in", "ADP", "prep", 3, tag="IN"),
                token(5, "front", "front", "NOUN", "pobj", 4),
                token(6, "of", "of", "ADP", "prep", 5, tag="IN"),
                token(7, "a", "a", "DET", "det", 8, tag="DT"),
                token(8, "wall", "wall", "NOUN", "pobj", 6),
            ],
            "noun_chunks": [
                chunk("A man", 1, 0, 2, "man"),
                chunk("front", 5, 5, 6, "front"),
                chunk("a wall", 8, 7, 9, "wall"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]
        candidate = next(edge for edge in edges if edge["rule_id"] == "R18.1")

        self.assertEqual(candidate["edge_type"], "ambiguous_relation_candidate")
        self.assertEqual(candidate["source_mention_id"], MISSING_SOURCE_MENTION_ID)
        self.assertEqual(candidate["label"], "in front of")
        self.assertEqual(candidate["source_detail"]["candidate_source_count"], 0)
        self.assertEqual(candidate["source_detail"]["candidate_target_count"], 1)
        self.assertEqual(candidate["source_detail"]["source_endpoint_status"], "source_missing")
        self.assertEqual(candidate["source_detail"]["target_endpoint_status"], "target_resolved")
        self.assertEqual(candidate["source_detail"]["ambiguity_scope"], "source_missing")

    def test_action_attached_preposition_mwe_multiple_sources_creates_candidates(self) -> None:
        record = {
            "caption_id": "c-show-front-of",
            "caption": "A dog shows a ball in front of a house.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "dog", "dog", "NOUN", "nsubj", 2),
                token(2, "shows", "show", "VERB", "ROOT", 2, tag="VBZ"),
                token(3, "a", "a", "DET", "det", 4, tag="DT"),
                token(4, "ball", "ball", "NOUN", "dobj", 2),
                token(5, "in", "in", "ADP", "prep", 2, tag="IN"),
                token(6, "front", "front", "NOUN", "pobj", 5),
                token(7, "of", "of", "ADP", "prep", 6, tag="IN"),
                token(8, "a", "a", "DET", "det", 9, tag="DT"),
                token(9, "house", "house", "NOUN", "pobj", 7),
            ],
            "noun_chunks": [
                chunk("A dog", 1, 0, 2, "dog"),
                chunk("a ball", 4, 3, 5, "ball"),
                chunk("front", 6, 6, 7, "front"),
                chunk("a house", 9, 8, 10, "house"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]
        candidate_edges = [
            edge for edge in edges if edge["edge_type"] == "ambiguous_relation_candidate"
        ]

        self.assertNotIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        self.assertEqual(len(candidate_edges), 2)
        self.assertEqual(
            {edge["source_detail"]["source_dep"] for edge in candidate_edges},
            {"nsubj", "dobj"},
        )
        self.assertTrue(
            all(edge["source_detail"]["candidate_source_count"] == 2 for edge in candidate_edges)
        )
        self.assertTrue(
            all(edge["source_detail"]["candidate_target_count"] == 1 for edge in candidate_edges)
        )

    def test_preposition_mwe_multiple_targets_creates_ambiguous_candidate_edges(self) -> None:
        record = {
            "caption_id": "c-stand-front-of-multiple-targets",
            "caption": "Dogs stand in front of a bench and sign.",
            "tokens": [
                token(0, "Dogs", "dog", "NOUN", "nsubj", 1, tag="NNS"),
                token(1, "stand", "stand", "VERB", "ROOT", 1, tag="VBP"),
                token(2, "in", "in", "ADP", "prep", 1, tag="IN"),
                token(3, "front", "front", "NOUN", "pobj", 2),
                token(4, "of", "of", "ADP", "prep", 3, tag="IN"),
                token(5, "a", "a", "DET", "det", 6, tag="DT"),
                token(6, "bench", "bench", "NOUN", "pobj", 4),
                token(7, "and", "and", "CCONJ", "cc", 8),
                token(8, "sign", "sign", "NOUN", "pobj", 4),
            ],
            "noun_chunks": [
                chunk("Dogs", 0, 0, 1, "Dogs"),
                chunk("front", 3, 3, 4, "front"),
                chunk("a bench", 6, 5, 7, "bench"),
                chunk("sign", 8, 8, 9, "sign"),
            ],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        edges = [edge.to_dict() for edge in result.raw_edges]
        candidate_edges = [
            edge for edge in edges if edge["edge_type"] == "ambiguous_relation_candidate"
        ]

        self.assertNotIn(("relation", "in front of", "R18.1"), _edge_sig(edges))
        self.assertEqual(len(candidate_edges), 2)
        self.assertEqual(
            {edge["target_mention_id"] for edge in candidate_edges},
            {"m1", "m2"},
        )
        self.assertTrue(
            all(edge["source_detail"]["candidate_source_count"] == 1 for edge in candidate_edges)
        )
        self.assertTrue(
            all(edge["source_detail"]["candidate_target_count"] == 2 for edge in candidate_edges)
        )
        self.assertTrue(
            all(edge["source_detail"]["ambiguity_scope"] == "target" for edge in candidate_edges)
        )

    def test_preposition_mwe_tokens_are_excluded_from_action_candidates(self) -> None:
        record = {
            "caption_id": "c-action-mwe-exclusion",
            "caption": "A frame in front of a house.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "frame", "frame", "VERB", "ROOT", 1, tag="VB"),
                token(2, "in", "in", "ADP", "prep", 1, tag="IN"),
                token(3, "front", "front", "NOUN", "pobj", 2),
                token(4, "of", "of", "ADP", "prep", 3, tag="IN"),
                token(5, "a", "a", "DET", "det", 6, tag="DT"),
                token(6, "house", "house", "NOUN", "pobj", 4),
            ],
            "noun_chunks": [chunk("a house", 6, 5, 7, "house")],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
            action_lookup=fake_frame_in_action_lookup,
            preposition_mwe_lookup=(in_front_of_entry(),),
        )
        actions = [
            mention.to_dict()
            for mention in result.raw_mentions
            if mention.mention_type == "action"
        ]

        self.assertEqual(actions[0]["text"], "frame")
        self.assertEqual(actions[0]["source_detail"]["selected_token_indices"], [1])

    def test_nsubjpass_is_not_normalized_to_agent(self) -> None:
        record = {
            "caption_id": "c4",
            "caption": "A ball is held.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 1, tag="DT"),
                token(1, "ball", "ball", "NOUN", "nsubjpass", 3),
                token(2, "is", "be", "AUX", "auxpass", 3, tag="VBZ"),
                token(3, "held", "hold", "VERB", "ROOT", 3, tag="VBN"),
            ],
            "noun_chunks": [chunk("A ball", 1, 0, 2, "ball")],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
        )
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertNotIn(("event_role", "agent", "R16"), _edge_sig(edges))

    def test_run_stage4_extract_raw_writes_outputs(self) -> None:
        record = {
            "caption_id": "c5",
            "caption": "A brown dog.",
            "tokens": [
                token(0, "A", "a", "DET", "det", 2, tag="DT"),
                token(1, "brown", "brown", "ADJ", "amod", 2, tag="JJ"),
                token(2, "dog", "dog", "NOUN", "ROOT", 2),
            ],
            "noun_chunks": [chunk("A brown dog", 2, 0, 3, "dog")],
        }
        tmp_path = _stage4_temp_base() / uuid.uuid4().hex
        tmp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = tmp_path / "stage3_records.jsonl"
            raw_mentions_path = tmp_path / "raw_mentions.jsonl"
            raw_edges_path = tmp_path / "raw_edges.jsonl"
            summary_path = tmp_path / "summary.jsonl"
            write_jsonl(input_path, [record])

            summary = run_stage4_extract_raw(
                input_path,
                raw_mentions_path=raw_mentions_path,
                raw_edges_path=raw_edges_path,
                summary_path=summary_path,
                object_lookup=fake_object_lookup,
            )

            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["raw_mention_total"], 2)
            self.assertEqual(summary["raw_edge_total"], 1)
            self.assertEqual(len(list(iter_jsonl(raw_mentions_path))), 2)
            self.assertEqual(len(list(iter_jsonl(raw_edges_path))), 1)
            self.assertEqual(list(iter_jsonl(summary_path))[0]["raw_mention_total"], 2)
        finally:
            for path in sorted(tmp_path.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            tmp_path.rmdir()

    def test_nmod_inside_noun_chunk_is_attribute_modifier(self) -> None:
        record = {
            "caption_id": "c6",
            "caption": "Players wear maroon jerseys.",
            "tokens": [
                token(0, "maroon", "maroon", "NOUN", "nmod", 1, tag="NN"),
                token(1, "jerseys", "jersey", "NOUN", "ROOT", 1, tag="NNS"),
            ],
            "noun_chunks": [chunk("maroon jerseys", 1, 0, 2, "jerseys")],
        }

        result = extract_raw_concepts_from_stage3_record(
            record,
            object_lookup=fake_object_lookup,
        )
        mentions = [mention.to_dict() for mention in result.raw_mentions]
        edges = [edge.to_dict() for edge in result.raw_edges]

        self.assertTrue(
            any(
                mention["mention_type"] == "attribute"
                and mention["text"] == "maroon"
                and mention["rule_id"] == "R13"
                for mention in mentions
            )
        )
        self.assertIn(("has_attribute", "has_attribute", "R13"), _edge_sig(edges))


def can_load_trf_model() -> bool:
    if spacy is None:
        return False
    return importlib.util.find_spec(DEFAULT_STAGE3_MODEL) is not None


@unittest.skipUnless(can_load_trf_model(), "en_core_web_trf is not installed")
class Stage4DocDirectExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.nlp = make_stage3_nlp()

    def test_doc_direct_path_matches_stage3_record_path(self) -> None:
        rows = [
            {
                "key": "k-doc-direct",
                "caption": "A brown dog sits on a wooden bench.",
                "caption_type": "short",
            }
        ]

        stage3_record = next(
            iter_stage3_records_from_rows(
                rows,
                nlp=self.nlp,
                batch_size=1,
            )
        )
        annotated = next(
            iter_annotated_docs_from_rows(
                rows,
                nlp=self.nlp,
                batch_size=1,
            )
        )

        record_result = extract_raw_concepts_from_stage3_record(
            stage3_record.to_dict(),
            object_lookup=fake_object_lookup,
        )
        doc_result = extract_raw_concepts_from_doc(
            annotated.caption_id,
            annotated.doc,
            object_lookup=fake_object_lookup,
        )

        self.assertEqual(
            [mention.to_dict() for mention in doc_result.raw_mentions],
            [mention.to_dict() for mention in record_result.raw_mentions],
        )
        self.assertEqual(
            [edge.to_dict() for edge in doc_result.raw_edges],
            [edge.to_dict() for edge in record_result.raw_edges],
        )


def _edge_sig(edges: list[dict[str, object]]) -> set[tuple[object, object, object]]:
    return {(edge["edge_type"], edge["label"], edge["rule_id"]) for edge in edges}


class FakeSynset:
    def __init__(self, synset_id: str, lexfile: str, lemmas: list[str]) -> None:
        self.id = synset_id
        self._lexfile = lexfile
        self._lemmas = lemmas

    def lexfile(self) -> str:
        return self._lexfile

    def lemmas(self) -> list[str]:
        return self._lemmas


class FakeOewn:
    def __init__(self, synsets_by_query: dict[tuple[str, str], tuple[FakeSynset, ...]]) -> None:
        self._synsets_by_query = synsets_by_query

    def synsets(self, query: str, *, pos: str) -> tuple[FakeSynset, ...]:
        return self._synsets_by_query.get((query, pos), ())


class FakeMorphy:
    def __init__(self, results_by_query: dict[str, dict[str, set[str]]]) -> None:
        self._results_by_query = results_by_query

    def __call__(self, query: str, pos: str) -> dict[str, set[str]]:
        return self._results_by_query.get(query, {})


def fake_object_lookup(surface: str) -> _ObjectLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    synsets = {
        "man": FakeSynset("fake-man-n", "noun.person", ["man"]),
        "dog": FakeSynset("fake-dog-n", "noun.animal", ["dog"]),
        "dogs": FakeSynset("fake-dog-n", "noun.animal", ["dog"]),
        "ball": FakeSynset("fake-ball-n", "noun.artifact", ["ball"]),
        "bench": FakeSynset("fake-bench-n", "noun.artifact", ["bench"]),
        "collar": FakeSynset("fake-collar-n", "noun.artifact", ["collar"]),
        "house": FakeSynset("fake-house-n", "noun.artifact", ["house"]),
        "jerseys": FakeSynset("fake-jersey-n", "noun.artifact", ["jersey"]),
        "legs": FakeSynset("fake-leg-n", "noun.body", ["leg"]),
        "focus": FakeSynset("fake-focus-n", "noun.attribute", ["focus"]),
        "road": FakeSynset("fake-road-n", "noun.artifact", ["road"]),
        "screen": FakeSynset("fake-screen-n", "noun.artifact", ["screen"]),
        "sign": FakeSynset("fake-sign-n", "noun.artifact", ["sign"]),
        "van": FakeSynset("fake-van-n", "noun.artifact", ["van"]),
        "wall": FakeSynset("fake-wall-n", "noun.artifact", ["wall"]),
    }
    synset = synsets.get(key)
    if synset is None:
        return None
    return _ObjectLookupResult(
        lookup_case="test",
        query=key,
        synsets=(synset,),
        selected_synset=synset,
        synset_selection_tag="test_single_noun_synset",
        wn30_lemma_counts="",
        objectness_gate="object_compatible",
        decision_status="chosen",
        canonical_surface=synset.lemmas()[0],
        canonical_label_key=synset.lemmas()[0],
        canonical_selection_tag="selected_single_observed_variant_matched_synset_lemma",
    )


def fake_action_lookup(surface: str) -> _ActionLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key != "look at":
        return None
    synset = FakeSynset("fake-look-at-v", "verb.perception", ["look_at"])
    return _ActionLookupResult(
        lookup_case="test",
        query=key,
        synsets=(synset,),
        selected_synset=synset,
        synset_selection_tag="test_single_verb_synset",
        wn30_lemma_counts="",
        decision_status="chosen",
        decision_reason="selected_verb_synset",
    )


def fake_frame_in_action_lookup(surface: str) -> _ActionLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key != "frame in":
        return None
    synset = FakeSynset("fake-frame-in-v", "verb.contact", ["frame_in"])
    return _ActionLookupResult(
        lookup_case="test",
        query=key,
        synsets=(synset,),
        selected_synset=synset,
        synset_selection_tag="test_single_verb_synset",
        wn30_lemma_counts="",
        decision_status="chosen",
        decision_reason="selected_verb_synset",
    )


def in_front_of_entry() -> _PrepositionMweEntry:
    return _PrepositionMweEntry(
        surface="in front of",
        token_keys=("in", "front", "of"),
        canonical_relation="in front of",
        relation_components=("in", "front", "of"),
        initial_relation_token_offset=0,
        final_adp_token_offset=2,
        source="test",
    )


def front_of_entry() -> _PrepositionMweEntry:
    return _PrepositionMweEntry(
        surface="front of",
        token_keys=("front", "of"),
        canonical_relation="front of",
        relation_components=("front", "of"),
        initial_relation_token_offset=0,
        final_adp_token_offset=1,
        source="test",
    )


def out_of_entry() -> _PrepositionMweEntry:
    return _PrepositionMweEntry(
        surface="out of",
        token_keys=("out", "of"),
        canonical_relation="out of",
        relation_components=("out", "of"),
        initial_relation_token_offset=0,
        final_adp_token_offset=1,
        source="test",
    )


def fake_ambiguous_action_lookup(surface: str) -> _ActionLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key != "marked":
        return None
    synsets = (
        FakeSynset("fake-mark-contact-v", "verb.contact", ["mark"]),
        FakeSynset("fake-mark-communication-v", "verb.communication", ["mark"]),
    )
    return _ActionLookupResult(
        lookup_case="test",
        query="mark",
        synsets=synsets,
        selected_synset=None,
        synset_selection_tag="ambiguous_wn30_tie",
        wn30_lemma_counts="fake-mark-contact-v:13|fake-mark-communication-v:13",
        decision_status="needs_manual",
        decision_reason="manual_action_synset_required",
    )


def fake_ambiguous_object_lookup(surface: str) -> _ObjectLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key != "bat":
        return None
    synsets = (
        FakeSynset("fake-bat-animal-n", "noun.animal", ["bat"]),
        FakeSynset("fake-bat-artifact-n", "noun.artifact", ["bat"]),
    )
    return _ObjectLookupResult(
        lookup_case="test",
        query=key,
        synsets=synsets,
        selected_synset=None,
        synset_selection_tag="ambiguous_wn30_tie",
        wn30_lemma_counts="fake-bat-animal-n:2|fake-bat-artifact-n:2",
        objectness_gate="",
        decision_status="needs_manual",
    )


def fake_plural_exact_polluted_lookup(surface: str) -> _ObjectLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key == "man":
        synset = FakeSynset("fake-man-n", "noun.person", ["man"])
        return _ObjectLookupResult(
            lookup_case="test_lemma_first",
            query=key,
            synsets=(synset,),
            selected_synset=synset,
            synset_selection_tag="test_single_noun_synset",
            wn30_lemma_counts="",
            objectness_gate="object_compatible",
            decision_status="chosen",
            canonical_surface="man",
            canonical_label_key="man",
            canonical_selection_tag="selected_single_observed_variant_matched_synset_lemma",
        )
    if key == "men":
        synset = FakeSynset("fake-men-group-n", "noun.group", ["men"])
        return _ObjectLookupResult(
            lookup_case="test_exact_pollution",
            query=key,
            synsets=(synset,),
            selected_synset=synset,
            synset_selection_tag="test_exact_pollution",
            wn30_lemma_counts="",
            objectness_gate="conditional",
            decision_status="needs_manual",
        )
    return None


def fake_determiner_start_polluted_lookup(surface: str) -> _ObjectLookupResult | None:
    key = " ".join(surface.strip().lower().split())
    if key == "a man":
        raise AssertionError("determiner-start object span should not be probed")
    if key == "man":
        synset = FakeSynset("fake-man-n", "noun.person", ["man"])
        return _ObjectLookupResult(
            lookup_case="test_root_after_det_skip",
            query=key,
            synsets=(synset,),
            selected_synset=synset,
            synset_selection_tag="test_single_noun_synset",
            wn30_lemma_counts="",
            objectness_gate="object_compatible",
            decision_status="chosen",
            canonical_surface="man",
            canonical_label_key="man",
            canonical_selection_tag="selected_single_observed_variant_matched_synset_lemma",
        )
    return None


def _stage4_temp_base() -> Path:
    roots = [
        os.environ.get("GPIC_TEST_TEMP_ROOT"),
        str(Path.cwd() / ".tmp_tests"),
        r"C:\Users\Public\Documents\ESTsoft\CreatorTemp",
        tempfile.gettempdir(),
    ]
    for root in roots:
        if not root:
            continue
        base = Path(root) / "stage4_extract_raw"
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f"{uuid.uuid4().hex}.tmp"
            probe.write_text("", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except PermissionError:
            continue
    raise PermissionError("no writable temp directory for stage4 tests")


if __name__ == "__main__":
    unittest.main()
