"""WSGI entry point: gunicorn -w 4 -b 127.0.0.1:5000 wsgi:app

(`app:app` cannot be used because the `app/` package shadows `app.py`.)
Set ENABLE_SCHEDULER=False for gunicorn and run `python worker.py` once.
"""
from app import create_app

app = create_app()
