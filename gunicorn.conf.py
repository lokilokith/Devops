"""Gunicorn Configuration File for OpsForge production deployments."""

import multiprocessing

# Server binding
bind = "0.0.0.0:8000"

# Worker process management
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 30
graceful_timeout = 30

# Logging configurations
loglevel = "info"
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (Request-ID: %({X-Request-ID}i)s, duration: %(M)sms)'
