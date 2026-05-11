FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el proyecto (necesita acceso a alembic + todos los módulos)
COPY shared/ ./shared/
COPY agents/ ./agents/
COPY orchestrator/ ./orchestrator/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8080

# El orchestrator corre las migraciones antes de arrancar (dentro del lifespan)
CMD ["python", "-m", "orchestrator.main"]
