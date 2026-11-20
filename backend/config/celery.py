"""Celery application used for background OCR / AI processing."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("docintel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
