# NVIDIA CUDA base for GPU inference
FROM nvidia/cuda:12.4.0-runtime-ubuntu22.04

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy workspace config
COPY pyproject.toml .python-version ./
COPY packages/ packages/
COPY services/vision/ services/vision/

# Install dependencies (GPU torch from PyTorch index)
RUN uv sync --package rva-vision \
    --extra-index-url https://download.pytorch.org/whl/cu124

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "rva-vision"]
