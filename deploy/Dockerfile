FROM python:3.11-slim

# Which commit this image was built from. CI passes it; /health reports it, which is
# how a deploy is confirmed without anyone having to ssh in and look.
ARG GIT_SHA=dev
ENV SDOC_VERSION=$GIT_SHA

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
# /state holds the Claude switch and is a named volume in production. Create it here
# with the right ownership: Docker seeds a fresh named volume from the image, so if the
# directory does not exist owned by this uid, the volume lands owned by root, the app
# cannot write the switch, and the setting silently does not survive a restart.
RUN useradd --create-home --uid 10001 sdoc \
    && mkdir -p /state \
    && chown -R sdoc:sdoc /app /state
USER sdoc

EXPOSE 8000

# The service processes the inbox itself on startup — see src/api/main.py lifespan.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
