# Language-pair -> HF model mapping
MODEL_REGISTRY = {
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("zh", "en"): "Helsinki-NLP/opus-mt-zh-en",
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}

def resolve_model(source_lang: str, target_lang: str) -> str:
    key = (source_lang.lower(), target_lang.lower())
    if key not in MODEL_REGISTRY:
        raise ValueError(f"Unsupported language pair: {source_lang}->{target_lang}")
    return MODEL_REGISTRY[key]
