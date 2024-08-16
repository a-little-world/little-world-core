"""
## Backend Development

Backend configuration module.

.. include:: ./README.md
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
