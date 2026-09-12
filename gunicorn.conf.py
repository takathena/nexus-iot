"""
Gunicorn configuration
"""
import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', 5000)}"
backlog = 2048

workers = int(os.getenv('WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
threads = int(os.getenv('THREADS', 4))
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 120
keepalive = 5
graceful_timeout = 30

accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

proc_name = 'nexus-iot'

daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None


def on_exit(server):
    """Graceful shutdown"""
    from background import stop_background_tasks
    stop_background_tasks()