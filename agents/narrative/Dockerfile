FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY agents/__init__.py ./agents/__init__.py

# Reutiliza OnchainClient (Moralis/Etherscan/Helius) del Monitor Agent
# para holder concentration — no se duplica esa lógica acá.
COPY agents/monitor/__init__.py ./agents/monitor/__init__.py
COPY agents/monitor/onchain_client.py ./agents/monitor/onchain_client.py

COPY agents/narrative/ ./agents/narrative/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

CMD ["python", "-m", "agents.narrative"]
