FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml .python-version ./
COPY packages/ packages/
COPY services/streamlit/ services/streamlit/

RUN uv sync --package rva-streamlit

ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", \
     "services/streamlit/src/streamlit_app/app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0"]
