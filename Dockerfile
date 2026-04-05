FROM python:3.12-slim

# Cache bust - mini calendar for create form - 2026-03-31
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x start.sh

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

WORKDIR /app

CMD gunicorn run:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 --access-logfile - --error-logfile -
