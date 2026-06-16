#!/bin/bash
# Runs once on first cluster init (empty pg_data volume). Creates a dedicated
# database + role for Airflow metadata and for the Iceberg REST JDBC catalog,
# so a single Postgres instance backs both with logical isolation.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE ${AIRFLOW_DB_USER} WITH LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
    CREATE DATABASE ${AIRFLOW_DB_NAME} OWNER ${AIRFLOW_DB_USER};
    GRANT ALL PRIVILEGES ON DATABASE ${AIRFLOW_DB_NAME} TO ${AIRFLOW_DB_USER};

    CREATE ROLE ${ICEBERG_DB_USER} WITH LOGIN PASSWORD '${ICEBERG_DB_PASSWORD}';
    CREATE DATABASE ${ICEBERG_DB_NAME} OWNER ${ICEBERG_DB_USER};
    GRANT ALL PRIVILEGES ON DATABASE ${ICEBERG_DB_NAME} TO ${ICEBERG_DB_USER};
EOSQL

echo "postgres init: created databases ${AIRFLOW_DB_NAME} (Airflow) and ${ICEBERG_DB_NAME} (Iceberg catalog)"
