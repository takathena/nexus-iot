"""
WSGI entry point untuk Gunicorn
Usage: gunicorn -c gunicorn.conf.py wsgi:app

✅ P0 FIX: cukup import `app` dari module `app`.
JANGAN panggil create_app() lagi di sini — itu bikin double init
(background lock di-acquire 2x, DB init 2x, signal handler 2x).
"""
from app import app  # noqa: F401

if __name__ == '__main__':
    app.run()