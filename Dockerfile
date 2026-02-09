FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps (torch CPU wheels typically OK; keep minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md /app/
RUN pip install --upgrade pip \
 && pip install -e .

COPY app /app/app

EXPOSE 8000

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
