# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gcc \
 && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /build

COPY pyproject.toml uv.lock ./
RUN uv sync --all-extras --no-install-project --no-dev

COPY . .
RUN uv sync --all-extras --no-dev

# Stage 2: Runtime (smaller final image)
FROM python:3.12-slim

# ✅ Install Tesseract (with English data)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy only necessary files from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/pyproject.toml /build/uv.lock ./
COPY --from=builder /build/src ./src
COPY data/ /app/data/
COPY test/ /app/test/

# create the runtime .env (defaults only; NO secrets baked)
COPY .env.example /app/.env
# If a real .env exists in the build context (CI), use it; otherwise fall back to the example.
COPY .env /app/.env
RUN test -f /app/.env || cp /app/.env.example /app/.env

# Clean up
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find . -type f -name "*.pyc" -delete \
    && find . -type f -name "*.pyo" -delete

EXPOSE 8000

ENV APP_MODULE="kyc_pipeline.api:app"
CMD ["uv", "run", "uvicorn", "kyc_pipeline.api:app", "--host", "0.0.0.0", "--port", "8000"]