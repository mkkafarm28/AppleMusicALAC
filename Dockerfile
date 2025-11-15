# Dockerfile
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy repo
COPY . .

# Install Poetry
RUN pip install --no-cache-dir poetry

# Install dependencies
RUN poetry config virtualenvs.create false
RUN poetry install --only main

# Create folders
RUN mkdir -p downloads assets

# Default command
CMD ["python", "bot.py"]
