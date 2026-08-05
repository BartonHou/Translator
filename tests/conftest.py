"""Shared test fixtures and lightweight stubs for heavy ML dependencies.

The production stack depends on torch/transformers/spacy, which are large and
platform-sensitive. Tests never exercise real model weights, so we inject small
fakes into ``sys.modules`` *before* the app modules import them. This keeps the
suite fast and runnable in any environment (CI included) while still driving the
real caching / dedupe / routing / orchestration logic.
"""
import sys
import types

import pytest


# --------------------------------------------------------------------------
# Stub: torch
# --------------------------------------------------------------------------
def _install_torch_stub():
    if "torch" in sys.modules:
        return
    torch = types.ModuleType("torch")

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def no_grad():
        return _NoGrad()

    class _Device:
        def __init__(self, spec):
            self.spec = spec

        def __repr__(self):
            return f"device({self.spec})"

    cuda = types.SimpleNamespace(
        is_available=lambda: False,
        empty_cache=lambda: None,
        get_device_name=lambda idx=0: "stub-gpu",
        mem_get_info=lambda idx=0: (0, 0),
    )

    torch.no_grad = no_grad
    torch.device = _Device
    torch.cuda = cuda
    torch.float16 = "float16"
    torch.float32 = "float32"
    sys.modules["torch"] = torch


# --------------------------------------------------------------------------
# Stub: transformers
# --------------------------------------------------------------------------
def _install_transformers_stub():
    if "transformers" in sys.modules:
        return
    transformers = types.ModuleType("transformers")

    # Only needs to be importable + have the right attribute names. Tests that
    # exercise inference inject fake pipelines at the ModelManager boundary
    # rather than driving real tokenizer/model plumbing (that is HF's job).
    class _FromPretrained:
        @classmethod
        def from_pretrained(cls, name, **kw):
            return cls()

    transformers.AutoTokenizer = _FromPretrained
    transformers.AutoModelForSeq2SeqLM = _FromPretrained
    sys.modules["transformers"] = transformers


# --------------------------------------------------------------------------
# Stub: spacy (blank + sentencizer)
# --------------------------------------------------------------------------
def _install_spacy_stub():
    if "spacy" in sys.modules:
        return
    spacy = types.ModuleType("spacy")

    class _Sent:
        def __init__(self, text):
            self.text = text

    class _Doc:
        def __init__(self, text):
            self._text = text

        @property
        def sents(self):
            import re

            parts = re.split(r"(?<=[.!?。！？])\s+", self._text.strip())
            return [_Sent(p) for p in parts if p.strip()]

    class _NLP:
        def add_pipe(self, name):
            return None

        def __call__(self, text):
            return _Doc(text)

    spacy.blank = lambda lang: _NLP()
    sys.modules["spacy"] = spacy


_install_torch_stub()
_install_transformers_stub()
_install_spacy_stub()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def fake_redis():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)
