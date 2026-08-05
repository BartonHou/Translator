"""Tests for language detection normalization and quality heuristic."""
import unittest

from app.core.lang_detect import LanguageDetectionError, detect_language
from app.core.quality import estimate_confidence


class LangDetectTests(unittest.TestCase):
    def test_supported_language_passthrough(self):
        self.assertEqual(detect_language("x", detector=lambda t: "fr"), "fr")

    def test_chinese_variants_normalized(self):
        self.assertEqual(detect_language("x", detector=lambda t: "zh-cn"), "zh")
        self.assertEqual(detect_language("x", detector=lambda t: "zh-tw"), "zh")

    def test_unsupported_language_raises(self):
        with self.assertRaises(LanguageDetectionError):
            detect_language("x", detector=lambda t: "ru")

    def test_empty_text_raises(self):
        with self.assertRaises(LanguageDetectionError):
            detect_language("   ")

    def test_real_detector_on_clear_english(self):
        # Sanity check against the real langdetect model (deterministic seed).
        self.assertEqual(detect_language("This is clearly an English sentence."), "en")

    def test_chinese_detected_by_script(self):
        # Regression: langdetect mislabels this short Chinese as Korean; the
        # Unicode-script prior must return Chinese.
        self.assertEqual(detect_language("我想睡觉"), "zh")

    def test_japanese_detected_by_script(self):
        self.assertEqual(detect_language("今日はいい天気です"), "ja")

    def test_korean_detected_by_script(self):
        self.assertEqual(detect_language("나는 자고 싶다"), "ko")

    def test_script_prior_overrides_wrong_detector(self):
        # Even if the fallback detector is wrong, CJK script wins.
        self.assertEqual(detect_language("我想睡觉", detector=lambda t: "ko"), "zh")

    def test_short_english_prefers_supported_language(self):
        # Regression: langdetect's top guess for this is Afrikaans (unsupported);
        # we must fall through to the supported English candidate.
        self.assertEqual(detect_language("I want to sleep"), "en")


class QualityTests(unittest.TestCase):
    def test_empty_translation_is_zero(self):
        self.assertEqual(estimate_confidence("hello", ""), 0.0)

    def test_similar_length_scores_high(self):
        self.assertGreater(estimate_confidence("hello world", "hola mundo"), 0.9)

    def test_extreme_ratio_scores_lower(self):
        good = estimate_confidence("hello world", "hola mundo")
        truncated = estimate_confidence("a long sentence here", "x")
        self.assertLess(truncated, good)

    def test_untranslated_echo_penalized(self):
        echo = estimate_confidence("hello world", "hello world")
        real = estimate_confidence("hello world", "hola mundo")
        self.assertLess(echo, real)

    def test_bounded_range(self):
        c = estimate_confidence("abc", "xyz")
        self.assertGreaterEqual(c, 0.0)
        self.assertLessEqual(c, 1.0)


if __name__ == "__main__":
    unittest.main()
