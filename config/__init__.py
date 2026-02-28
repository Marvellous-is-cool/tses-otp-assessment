# making celery start up immediately upon starting celery

from .celery import app as celery_app

__all__ = ("celery_app",)