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

# Run as a non-root user: the container reads documents that arrive from outside.
RUN useradd --create-home --uid 10001 sdoc && chown -R sdoc:sdoc /app
USER sdoc

EXPOSE 8000

# The service processes the inbox itself on startup — see src/api/main.py lifespan.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
