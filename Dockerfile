FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=5000

# Use shell form so $PORT gets expanded
CMD ["python", "-c", "import os; os.execvp('gunicorn', ['gunicorn', 'run:app', '--bind', '0.0.0.0:' + os.environ.get('PORT', '5000'), '--workers', '2', '--timeout', '120'])"]
