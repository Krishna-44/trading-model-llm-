FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

COPY requirements.txt .
# psycopg added here so the Postgres/Timescale URL works inside the compose stack
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.1"

COPY aifos ./aifos
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "aifos.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
