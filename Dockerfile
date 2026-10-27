FROM apache/airflow:3.3.2

USER root
# Dependencias necesarias a nivel de sistema si hicieran falta
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir \
    requests \
    pandas \
    sqlalchemy \
    psycopg2-binary \
    tzdata \
    openpyxl \
    matplotlib
