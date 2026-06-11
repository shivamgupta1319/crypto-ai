# crypto-ai backend — FastAPI + uvicorn
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CRYPTOAI_DB_PATH=/data/cryptoai.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Alembic migrations run at startup, so the image needs them.
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# SQLite DB + candle cache persist in the mounted /data volume.
RUN mkdir -p /data
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
