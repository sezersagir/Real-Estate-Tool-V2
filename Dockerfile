FROM python:3.11-slim

# Verhindert, dass Python .pyc Dateien schreibt
ENV PYTHONDONTWRITEBYTECODE 1
# Stellt sicher, dass Logs sofort gesendet werden
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Wir nutzen gunicorn, weil es für echte Webseiten stabiler ist als der Flask-Testserver
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
