FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Persist the HuggingFace model cache to /models (backed by a named volume in
# docker-compose) so models are downloaded once, not on every container start.
ENV HF_HOME=/models
ENV HF_MODEL_CACHE=/models

# System deps (torch CPU wheels typically OK; keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first to maximize Docker layer caching.
COPY pyproject.toml /app/

RUN pip install --upgrade pip

# Install torch from the CUDA 12.8 wheel index. The default PyPI aarch64 torch is
# a CUDA 13.0 build, which needs a newer NVIDIA driver than the GH200 host has
# (driver supports CUDA 12.9) and therefore silently falls back to CPU. cu128
# matches the driver and runs on the GPU; it still works on CPU-only hosts.
# Pinned here so the pyproject install below sees torch>=2.2 already satisfied.
RUN pip install "torch==2.9.1" --index-url https://download.pytorch.org/whl/cu128

RUN python -c "import tomllib, pathlib, subprocess, sys; deps = tomllib.loads(pathlib.Path('/app/pyproject.toml').read_text())['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', *deps])"

# Copy application code after dependencies are installed.
COPY . /app/

# Install local package metadata/code without re-installing dependencies.
RUN pip install --no-deps -e .


EXPOSE 8000

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
