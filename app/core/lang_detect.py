"""Language auto-detection.

CJK languages are detected by Unicode *script* first, because langdetect is
unreliable on short text and routinely confuses Chinese/Japanese/Korean (e.g. it
labels the Chinese "我想睡觉" as Korean). Script detection is deterministic and
correct for CJK: Korean text contains Hangul, Japanese contains kana, and
Chinese is Han-only. Everything else falls back to langdetect, normalized to the
platform's language codes (see routing.SUPPORTED_LANGUAGES).

The langdetect detector is injectable so the mapping/error handling can be
unit-tested without depending on its probabilistic model.
"""
import structlog
from langdetect import DetectorFactory
from langdetect import detect_langs as _ld_detect_langs
from langdetect.lang_detect_exception import LangDetectException

from app.core.routing import SUPPORTED_LANGUAGES

log = structlog.get_logger()

# Deterministic results across runs.
DetectorFactory.seed = 0

# langdetect codes -> our codes. langdetect emits e.g. zh-cn/zh-tw for Chinese.
_NORMALIZE = {
    "zh-cn": "zh",
    "zh-tw": "zh",
    "zh": "zh",
}


class LanguageDetectionError(Exception):
    pass


def _has(text: str, ranges) -> bool:
    return any(any(lo <= ord(c) <= hi for lo, hi in ranges) for c in text)


# Unicode blocks used for CJK script detection.
_HANGUL = [(0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7FF)]
_KANA = [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF)]
_HAN = [(0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)]


def _script_hint(text: str) -> str | None:
    """Return a CJK language code from Unicode script, or None if not CJK.

    Order matters: Korean is identified by Hangul, Japanese by kana (Japanese
    also uses Han, so kana must win over Han), and remaining Han-only text is
    Chinese.
    """
    if _has(text, _HANGUL):
        return "ko"
    if _has(text, _KANA):
        return "ja"
    if _has(text, _HAN):
        return "zh"
    return None


def _normalize(raw: str) -> str | None:
    code = _NORMALIZE.get(raw.lower(), raw.lower())
    return code if code in SUPPORTED_LANGUAGES else None


def _best_supported(text: str) -> str | None:
    """Return the highest-ranked *supported* language from langdetect.

    langdetect's single-best guess is often an unsupported language on short
    text (e.g. English "I want to sleep" ranks Afrikaans first, English second),
    so we scan the ranked candidates and take the first one we support.
    """
    try:
        candidates = _ld_detect_langs(text)
    except LangDetectException:
        return None
    for cand in candidates:
        code = _normalize(cand.lang)
        if code is not None:
            return code
    return None


def detect_language(text: str, detector=None) -> str:
    """Detect the language of ``text`` and return a supported language code.

    Order: (1) deterministic Unicode-script prior for CJK, (2) an injected
    ``detector`` returning a single code (used by tests), else (3) langdetect's
    ranked candidates, preferring the top supported language.

    Raises LanguageDetectionError when the text is empty or no supported language
    can be determined.
    """
    if not text or not text.strip():
        raise LanguageDetectionError("cannot detect language of empty text")

    # Deterministic script prior for CJK (langdetect is unreliable here).
    hint = _script_hint(text)
    if hint is not None:
        return hint

    if detector is not None:  # test hook: single-code detector
        try:
            raw = detector(text)
        except LangDetectException as e:
            raise LanguageDetectionError(f"detection failed: {e}") from e
        code = _normalize(raw)
    else:
        code = _best_supported(text)

    if code is None:
        raise LanguageDetectionError(
            "could not confidently detect a supported language; "
            "please set the source language explicitly"
        )
    return code
