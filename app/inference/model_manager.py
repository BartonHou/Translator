import os
from typing import Dict
import structlog
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app.settings import settings

log = structlog.get_logger()

class ModelManager:
    """
    Loads and caches HF pipelines per model_name.
    """
    def __init__(self):
        self._pipelines: Dict[str, any] = {}
        os.environ["HF_HOME"] = settings.hf_model_cache

        if settings.device.lower() == "cuda" and torch.cuda.is_available():
            self._device = 0
        else:
            self._device = -1

    @property
    def device(self) -> str:
        return "cuda" if self._device == 0 else "cpu"

    def get_pipeline(self, model_name: str):
        if model_name in self._pipelines:
            return self._pipelines[model_name]

        log.info("loading_model", model=model_name, device=self.device)
        translator = self._build_seq2seq_translator(model_name)
        self._pipelines[model_name] = translator
        return translator

    def loaded_models(self) -> list[str]:
        return list(self._pipelines.keys())

    def _build_seq2seq_translator(self, model_name: str):
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        model.eval()
        device = torch.device("cuda" if self._device == 0 else "cpu")
        model.to(device)

        def _translate(texts, num_beams: int, max_new_tokens: int):
            if isinstance(texts, str):
                texts = [texts]
            inputs = tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    num_beams=num_beams,
                    max_new_tokens=max_new_tokens,
                )
            decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)
            return [{"translation_text": t} for t in decoded]

        return _translate
