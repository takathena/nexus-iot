"""
Gunicorn configuration
"""
import os
import multiprocessing
from dotenv import load_dotenv

load_dotenv()

# Server socket
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', 5000)}"
backlog = 2048

# Worker processes
workers = int(os.getenv('WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'sync'
threads = int(os.getenv('THREADS', 4))
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info').lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# Process naming
proc_name = 'nexus-iot'

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (uncomment jika pakai HTTPS langsung)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'

# Hook untuk cleanup
def on_exit(server):
    """Graceful shutdown"""
    from background import stop_background_tasks
    stop_background_tasks()