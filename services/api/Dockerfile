FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY .python-version pyproject.toml uv.lock /app/
COPY packages /app/packages
COPY services/api /app/services/api
COPY configs /app/configs

RUN pip install --no-cache-dir uv
RUN uv sync --frozen --package rva-api --no-dev

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--package", "rva-api", "uvicorn", "rva_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
