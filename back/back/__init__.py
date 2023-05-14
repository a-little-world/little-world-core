"""
.. include:: ../docs_nav.md

## Backend Development

Backend configuration module.

- [detailed information on the `run.py` script](/run.html)

Contains standart django configurations in `settings.py` and basic setup of our asgi app in `asgi.py` basic initalization for celery task management in `celery.py`.

.. include:: ./README.md
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
