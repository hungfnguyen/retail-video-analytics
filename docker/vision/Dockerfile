# Vision service — NVIDIA CUDA base for GPU inference
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

# System dependencies
# - libgl1-mesa-glx, libglib2.0-0: required by OpenCV headless
# - ffmpeg: RTSP stream decoding backend for cv2.VideoCapture
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace configuration first (cached layer)
COPY pyproject.toml .python-version ./
COPY packages/ packages/
COPY services/vision/ services/vision/

# Install rva-vision with GPU PyTorch index
RUN uv sync --frozen --package rva-vision \
    --extra-index-url https://download.pytorch.org/whl/cu121

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["uv", "run", "rva-vision"]
