FROM apache/airflow:2.9.2-python3.12

ARG AIRFLOW_CONSTRAINTS_LOCATION="https://raw.githubusercontent.com/apache/airflow/constraints-2.9.2/constraints-3.12.txt"

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    --constraint "${AIRFLOW_CONSTRAINTS_LOCATION}" \
    -r /requirements.txt