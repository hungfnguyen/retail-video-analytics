FROM maven:3.9.9-eclipse-temurin-11 AS flink-jar-builder

WORKDIR /build
COPY services/flink-jobs/java/pom.xml /build/pom.xml
COPY services/flink-jobs/java/src /build/src
RUN --mount=type=cache,target=/root/.m2 mvn -q package -DskipTests

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

COPY infrastructure/airflow/requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    --constraint "${AIRFLOW_CONSTRAINTS_LOCATION}" \
    -r /requirements.txt

USER root
RUN mkdir -p /opt/rva-artifacts
COPY --from=flink-jar-builder /build/target/silver-job-0.1.0.jar /opt/rva-artifacts/gold-jobs.jar
RUN chown -R airflow:0 /opt/rva-artifacts

USER airflow
