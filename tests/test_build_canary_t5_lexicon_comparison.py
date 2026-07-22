import unittest

from scripts.build_canary_t5_lexicon_comparison import CountRow, LabelMatcher


class CanaryT5LexiconComparisonTest(unittest.TestCase):
    def test_attribute_variant_match_does_not_attach_lowercase_query_to_proper_name(self) -> None:
        matcher = LabelMatcher(
            [
                CountRow(label="red", raw_surfaces="red|reds", caption_count=10),
                CountRow(label="Redding", raw_surfaces="redding", caption_count=1),
            ],
            include_variants_with_exact=True,
        )

        match = matcher.match("red")

        self.assertEqual(match.labels, ("red",))
        self.assertEqual(match.caption_count, 10)

    def test_attribute_variant_match_keeps_regular_and_irregular_participles(self) -> None:
        matcher = LabelMatcher(
            [
                CountRow(label="spotted", raw_surfaces="spotted", caption_count=7),
                CountRow(label="hand-drawn", raw_surfaces="hand-drawn", caption_count=5),
            ],
            include_variants_with_exact=True,
        )

        self.assertEqual(matcher.match("spot").labels, ("spotted",))
        self.assertEqual(matcher.match("hand - draw").labels, ("hand-drawn",))

    def test_display_labels_strip_quotes_and_dedupe(self) -> None:
        matcher = LabelMatcher(
            [
                CountRow(label="sculpture", raw_surfaces="sculpture", caption_count=21),
                CountRow(label='"sculpture"', raw_surfaces='"sculpture"', caption_count=1),
            ],
            include_variants_with_exact=True,
        )

        match = matcher.match("sculpture")

        self.assertEqual(match.labels, ("sculpture",))
        self.assertEqual(match.caption_count, 22)


if __name__ == "__main__":
    unittest.main()
