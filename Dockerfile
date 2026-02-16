FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps (torch CPU wheels typically OK; keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first to maximize Docker layer caching.
COPY pyproject.toml /app/

RUN pip install --upgrade pip \
 && python -c "import tomllib, pathlib, subprocess, sys; deps = tomllib.loads(pathlib.Path('/app/pyproject.toml').read_text())['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', *deps])"

# Copy application code after dependencies are installed.
COPY . /app/

# Install local package metadata/code without re-installing dependencies.
RUN pip install --no-deps -e .


EXPOSE 8000

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
