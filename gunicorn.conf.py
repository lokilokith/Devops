"""Gunicorn Configuration File for OpsForge production deployments."""

import multiprocessing
import os

# Server binding
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Worker process management
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("GUNICORN_THREADS", 4))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))

# Logging configurations
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
accesslog = os.getenv("GUNICORN_ACCESSLOG", "-")
errorlog = os.getenv("GUNICORN_ERRORLOG", "-")
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'
    ' "%(f)s" "%(a)s"'
    " (Request-ID: %({X-Request-ID}i)s,"
    " duration: %(M)sms)"
)
