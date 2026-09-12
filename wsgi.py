"""
WSGI entry point untuk Gunicorn
Usage: gunicorn -c gunicorn.conf.py wsgi:app
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()