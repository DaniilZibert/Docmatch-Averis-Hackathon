# OWNER: Person B. Starting point — adjust as the service takes shape.
FROM python:3.11-slim

WORKDIR /app

# System deps for the document extractors (pdf rendering, fonts).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
