from __future__ import annotations

import unittest

from vanity18035.patterns import PatternError, TaskClass, address_matches, classify_pattern


class PatternTests(unittest.TestCase):
    def test_classification(self) -> None:
        self.assertEqual(classify_pattern("", "Yqvi2").task_class, TaskClass.P0)
        self.assertEqual(classify_pattern("LU", "Yqvi2").task_class, TaskClass.P1)
        self.assertEqual(classify_pattern("ABCDEF", "").task_class, TaskClass.P1)
        self.assertEqual(classify_pattern("", "ABCDEF").task_class, TaskClass.P2)

    def test_invalid_patterns(self) -> None:
        for prefix, suffix in (
            ("", "1234"),
            ("", "123456789"),
            ("0", "12345"),
            ("O", "12345"),
            ("I", "12345"),
            ("l", "12345"),
        ):
            with self.subTest(prefix=prefix, suffix=suffix):
                with self.assertRaises(PatternError):
                    classify_pattern(prefix, suffix)

    def test_impossible_tron_prefix_is_rejected(self) -> None:
        with self.assertRaises(PatternError):
            classify_pattern("zzzzzz", "")

    def test_address_matching(self) -> None:
        p0 = classify_pattern("", "Yqvi2")
        address = "T" + "1" * 28 + "Yqvi2"
        self.assertEqual(len(address), 34)
        self.assertTrue(address_matches(p0, address))
        self.assertFalse(address_matches(p0, address[:-1] + "3"))


if __name__ == "__main__":
    unittest.main()
