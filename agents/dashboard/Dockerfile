FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY agents/__init__.py ./agents/__init__.py
COPY agents/monitor/schemas.py ./agents/monitor/schemas.py
COPY agents/monitor/__init__.py ./agents/monitor/__init__.py
COPY agents/detector/schemas.py ./agents/detector/schemas.py
COPY agents/detector/__init__.py ./agents/detector/__init__.py
COPY agents/dashboard/ ./agents/dashboard/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8001

CMD ["python", "-m", "agents.dashboard"]
