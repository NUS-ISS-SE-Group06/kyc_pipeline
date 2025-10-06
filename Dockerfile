FROM python:3.12-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=.venv \
    PORT=8000

#OS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install uv (single static binary)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock ./uv.lock

#Create virtualenv and install deps
RUN uv sync --all-extras --no-install-project

# Now copy the rest of your source
COPY . .

# Re-sync in case optional
RUN uv sync --all-extras --no-install-project

# Expose the uvicorn port
EXPOSE 8000

# Default command: run the API
ENV APP_MODULE="kyc_pipeline.api:app"
CMD ["uv", "run", "uvicorn", "kyc_pipeline.api:app", "--host", "0.0.0.0", "--port", "8000"]