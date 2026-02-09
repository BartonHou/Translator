import os
from typing import Dict
import structlog
import torch
from transformers import pipeline

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
        pipe = pipeline(
            task="translation",
            model=model_name,
            device=self._device,
        )
        self._pipelines[model_name] = pipe
        return pipe

    def loaded_models(self) -> list[str]:
        return list(self._pipelines.keys())
