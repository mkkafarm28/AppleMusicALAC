# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir poetry

RUN poetry config virtualenvs.create false \
    && poetry install --only main

RUN pip install --no-cache-dir pyrogram==2.0.106 tgcrypto==1.2.5

RUN mkdir -p downloads assets

# ✅ Added restart policy check
CMD ["python", "-u", "bot.py"]
