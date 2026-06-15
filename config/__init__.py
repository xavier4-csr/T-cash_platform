# This makes our Celery app available at the Django package level
# so that Celery auto-discovery works correctly.
from .celery import app as celery_app  # noqa: F401

__all__ = ('celery_app',)
