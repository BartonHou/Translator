# Language-pair -> HF model mapping.
#
# Two engines back the router:
#   * opus-mt: dedicated Helsinki-NLP models for high-resource pairs (fast, good
#     quality). Non-English pairs route through an English pivot (es->en->de).
#   * NLLB: a single multilingual model (facebook/nllb-200-distilled-600M) used
#     for languages where opus-mt has no usable model — the ja/ko opus repos
#     produce garbage. NLLB translates these directly, any-to-any, no pivot.
#
# A pair is routed to NLLB whenever its source or target is an NLLB language.
# NLLB routes are encoded as a pseudo model name "nllb:<src_code>:<tgt_code>"
# so the rest of the pipeline (engine/orchestrator) treats them like any other
# model; ModelManager parses the prefix and loads the shared NLLB model.

MODEL_REGISTRY = {
    ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
    ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
    ("en", "it"): "Helsinki-NLP/opus-mt-en-it",
    ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
    # opus-mt-en-pt does not exist as a public repo; tc-big is the supported one.
    ("en", "pt"): "Helsinki-NLP/opus-mt-tc-big-en-pt",
    # opus-mt-pt-en does not exist; roa-en (Romance->English) covers Portuguese.
    ("pt", "en"): "Helsinki-NLP/opus-mt-roa-en",
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}

PIVOT_LANG = "en"

# Multilingual fallback engine. Japanese/Korean go here because the opus-mt
# repos for them output garbage (wrong tokenizer / untrained direction).
NLLB_MODEL = "facebook/nllb-200-distilled-600M"
NLLB_LANGS = {"ja", "ko"}
# ISO code -> NLLB FLORES-200 language code.
NLLB_CODES = {
    "en": "eng_Latn",
    "es": "spa_Latn",
    "de": "deu_Latn",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "fr": "fra_Latn",
    "zh": "zho_Hans",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
}

SUPPORTED_LANGUAGES = sorted(NLLB_CODES.keys())


def _nllb_route(src: str, tgt: str) -> str:
    """Pseudo model name that bakes the NLLB src/tgt codes in, e.g.
    ``nllb:zho_Hans:kor_Hang``. ModelManager parses this prefix."""
    return f"nllb:{NLLB_CODES[src]}:{NLLB_CODES[tgt]}"


def display_model(model_name: str) -> str:
    """Human-friendly name for API responses: hide the internal nllb pseudo
    name and drop the HF org prefix (Helsinki-NLP/opus-mt-en-zh -> opus-mt-en-zh)."""
    if model_name.startswith("nllb:"):
        return "nllb-200-distilled-600M"
    return model_name.split("/")[-1]


def display_path(model_path: list[str]) -> str:
    if not model_path:
        return "identity"
    return " -> ".join(display_model(m) for m in model_path)


def all_supported_pairs() -> list[dict]:
    """Every resolvable (src, tgt) pair with how it routes.

    Includes direct model pairs, English-pivot pairs, and NLLB direct pairs, so
    clients can present exactly the combinations that will succeed.
    """
    pairs: list[dict] = []
    for src in SUPPORTED_LANGUAGES:
        for tgt in SUPPORTED_LANGUAGES:
            if src == tgt:
                continue
            try:
                path = resolve_model_path(src, tgt)
            except ValueError:
                continue
            pairs.append({
                "source": src,
                "target": tgt,
                "hops": len(path),
                "via_pivot": len(path) > 1,
                "models": path,
            })
    return pairs


def resolve_model(source_lang: str, target_lang: str) -> str:
    key = (source_lang.lower(), target_lang.lower())
    if key not in MODEL_REGISTRY:
        raise ValueError(f"Unsupported language pair: {source_lang}->{target_lang}")
    return MODEL_REGISTRY[key]


def resolve_model_path(source_lang: str, target_lang: str) -> list[str]:
    src = source_lang.lower().strip()
    tgt = target_lang.lower().strip()

    if src == tgt:
        return []

    # NLLB handles any pair touching a language opus-mt can't do, directly.
    if src in NLLB_LANGS or tgt in NLLB_LANGS:
        if src in NLLB_CODES and tgt in NLLB_CODES:
            return [_nllb_route(src, tgt)]
        raise ValueError(
            f"Unsupported language pair: {source_lang}->{target_lang}. "
            f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
        )

    direct = MODEL_REGISTRY.get((src, tgt))
    if direct:
        return [direct]

    src_to_pivot = MODEL_REGISTRY.get((src, PIVOT_LANG))
    pivot_to_tgt = MODEL_REGISTRY.get((PIVOT_LANG, tgt))
    if src_to_pivot and pivot_to_tgt:
        return [src_to_pivot, pivot_to_tgt]

    raise ValueError(
        f"Unsupported language pair: {source_lang}->{target_lang}. "
        f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
    )
