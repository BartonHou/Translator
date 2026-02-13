# Language-pair -> HF model mapping
MODEL_REGISTRY = {
    ("en", "es"): "Helsinki-NLP/opus-mt-en-es",
    ("es", "en"): "Helsinki-NLP/opus-mt-es-en",
    ("en", "de"): "Helsinki-NLP/opus-mt-en-de",
    ("de", "en"): "Helsinki-NLP/opus-mt-de-en",
    ("en", "it"): "Helsinki-NLP/opus-mt-en-it",
    ("it", "en"): "Helsinki-NLP/opus-mt-it-en",
    ("en", "pt"): "Helsinki-NLP/opus-mt-en-pt",
    ("pt", "en"): "Helsinki-NLP/opus-mt-pt-en",
    ("en", "ja"): "Helsinki-NLP/opus-mt-en-jap",
    ("ja", "en"): "Helsinki-NLP/opus-mt-jap-en",
    ("en", "ko"): "Helsinki-NLP/opus-mt-en-ko",
    ("ko", "en"): "Helsinki-NLP/opus-mt-ko-en",
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}

PIVOT_LANG = "en"
SUPPORTED_LANGUAGES = sorted({lang for pair in MODEL_REGISTRY.keys() for lang in pair})


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
