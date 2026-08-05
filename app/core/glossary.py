"""Glossary term protection for translation.

Strategy (industry-standard "placeholder masking"):
  1. Before translation, replace each glossary source term in the input with a
     sentinel placeholder that MT models tend to pass through unchanged.
  2. Translate the masked text.
  3. Replace each placeholder in the output with the glossary's target term.

This forces terminology (brand names, product terms) to render exactly as
specified rather than being translated. Caveat: no MT model preserves arbitrary
tokens perfectly, so ``restore`` matches placeholders case-insensitively and
tolerates surrounding whitespace changes; a term the model mangled beyond that
falls back to the model's own translation.

Pure functions (no DB/IO) so the mask/restore round-trip is unit-testable.
"""
import re

# Sentinel that is unlikely to collide with real text and tends to survive
# tokenization as a unit. Indexed so multiple terms don't clash.
_PLACEHOLDER = "GLOSSARYTERM{i}X"
_PLACEHOLDER_RE = re.compile(r"GLOSSARYTERM(\d+)X", re.IGNORECASE)


def mask_terms(text: str, entries: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Replace glossary source terms with placeholders.

    Returns (masked_text, mapping) where mapping is placeholder -> target term.
    Longer source terms are masked first so multi-word terms win over substrings.
    """
    mapping: dict[str, str] = {}
    masked = text
    for i, src in enumerate(sorted(entries, key=len, reverse=True)):
        if not src:
            continue
        placeholder = _PLACEHOLDER.format(i=i)
        pattern = re.compile(re.escape(src), re.IGNORECASE)
        new_masked = pattern.sub(placeholder, masked)
        if new_masked != masked:
            mapping[placeholder] = entries[src]
            masked = new_masked
    return masked, mapping


def restore_terms(text: str, mapping: dict[str, str]) -> str:
    """Replace placeholders in translated text with target terms."""
    def _sub(m: re.Match) -> str:
        placeholder = _PLACEHOLDER.format(i=int(m.group(1)))
        return mapping.get(placeholder, m.group(0))

    return _PLACEHOLDER_RE.sub(_sub, text)
