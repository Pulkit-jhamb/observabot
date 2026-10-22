FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir flask==3.1.3 prometheus-client==0.26.0 gunicorn==23.0.0

COPY app.py .

EXPOSE 8000
# One worker so the in-memory chaos settings are shared by every request.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "app:app"]
