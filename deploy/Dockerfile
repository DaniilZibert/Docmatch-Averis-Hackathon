FROM python:3.11-slim

WORKDIR /app

# System deps for the document extractors (PDF rendering for the vision fallback).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

EXPOSE 8000

# Process the inbox on boot so the review screen has something on it, then serve.
CMD ["sh", "-c", "python -m src.pipeline --out /tmp/submission.json >/dev/null 2>&1; \
     exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000"]
