# Backend and MCP server image. Build context: repository root.
#   docker build -f backend/Dockerfile -t dealroom-copilot-backend .
FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEALROOM_ROOT=/app
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY backend backend
COPY mcp_server mcp_server
RUN pip install --no-cache-dir ".[postgres]"

COPY data data
RUN useradd --uid 10001 --create-home app \
    && dealroom ingest \
    && chown -R app:app /app
USER 10001

EXPOSE 8000
CMD ["uvicorn", "dealroom.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
