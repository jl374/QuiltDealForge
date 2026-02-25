FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2 and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT env var
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "echo DATABASE_URL starts with: $(echo $DATABASE_URL | cut -c1-30)... && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
