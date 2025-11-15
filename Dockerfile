# Dockerfile - အခု ချက်ချင်း အလုပ်လုပ်မယ် (pyrogram ပါပြီ)
FROM python:3.11-slim

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy repo
COPY . /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Install project dependencies (from pyproject.toml)
RUN poetry config virtualenvs.create false \
    && poetry install --only main

# ဒီ line ၂ ခု ထည့်ပေးလိုက်တယ် → pyrogram နဲ့ tgcrypto ချက်ချင်း ထည့်ပေးတယ်
RUN pip install --no-cache-dir pyrogram==2.0.106 tgcrypto==1.2.5

# Create folders
RUN mkdir -p downloads assets

# Run bot
CMD ["python", "bot.py"]
