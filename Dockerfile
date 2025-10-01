FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN useradd -m appuser
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src

RUN chown -R appuser:appuser /app
USER appuser

# This calls src/kyc_pipeline/main.py: if __name__ == "__main__": run()
CMD ["python", "-m", "kyc_pipeline.main"]




