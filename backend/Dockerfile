FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System packages: PostgreSQL client lib + libraries required by OpenCV (used by the OCR engine)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN DJANGO_DEBUG=true DJANGO_SECRET_KEY=build-only-placeholder python manage.py collectstatic --noinput

# Run as a non-root user (security)
RUN useradd -m appuser && mkdir -p /app/media /app/.cache/fastembed && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
