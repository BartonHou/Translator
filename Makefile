.PHONY: help venv install test lint fmt up gpu down logs

VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help:
	@echo "Targets: venv install test lint fmt up gpu down logs"

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

# Install runtime + dev deps for local testing. Heavy ML deps (torch/transformers/
# spacy) are only needed to actually serve translations; the test suite stubs them.
install:
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check .

fmt:
	$(VENV)/bin/ruff check --fix .

up:
	docker compose up --build

# Run on the GPU (uses the CUDA overlay: GPU reservation + fp16 + higher beam).
gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d

down:
	docker compose down

logs:
	docker compose logs -f
