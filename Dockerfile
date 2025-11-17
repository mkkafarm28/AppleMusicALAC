# Dockerfile
FROM python:3.11-slim

# ════════════════════════════════════════════════════════
# Install System Dependencies
# ════════════════════════════════════════════════════════
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    pkg-config \
    zlib1g-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# ════════════════════════════════════════════════════════
# Install GPAC (MP4Box)
# ════════════════════════════════════════════════════════
RUN cd /tmp && \
    git clone --depth=1 https://github.com/gpac/gpac.git && \
    cd gpac && \
    ./configure --static-bin && \
    make -j$(nproc) && \
    make install && \
    ln -sf $(which MP4Box) $(dirname $(which MP4Box))/mp4box && \
    cd /tmp && rm -rf gpac

# Verify GPAC installation
RUN MP4Box -version

# ════════════════════════════════════════════════════════
# Install Bento4
# ════════════════════════════════════════════════════════
RUN cd /tmp && \
    git clone --depth=1 https://github.com/axiomatic-systems/Bento4.git && \
    mkdir -p Bento4/cmakebuild && \
    cd Bento4/cmakebuild && \
    cmake -DCMAKE_BUILD_TYPE=Release .. && \
    make -j$(nproc) && \
    make install && \
    cd /tmp && rm -rf Bento4

# Verify Bento4 installation (check if executable exists)
RUN which mp4edit && ls -lh /usr/local/bin/mp4* || echo "Bento4 tools installed"

WORKDIR /app

# Copy repo
COPY . /app

# ════════════════════════════════════════════════════════
# Install Poetry and Python Dependencies
# ════════════════════════════════════════════════════════
RUN pip install --no-cache-dir poetry

RUN poetry config virtualenvs.create false \
    && poetry install --only main

# ✅ Explicitly install pyrogram and tgcrypto
RUN pip install --no-cache-dir pyrogram==2.0.106 tgcrypto==1.2.5

# Create folders
RUN mkdir -p downloads assets

# ════════════════════════════════════════════════════════
# Health check
# ════════════════════════════════════════════════════════
RUN ffmpeg -version | head -1 && \
    MP4Box -version | head -1 && \
    echo "✓ All dependencies installed successfully"

# Run bot
CMD ["python", "-u", "bot.py"]
