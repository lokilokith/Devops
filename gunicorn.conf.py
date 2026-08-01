import multiprocessing
import os

# Binding
bind = "0.0.0.0:5000"

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
threads = 2

# Timeouts
timeout = 120
keepalive = 5

# Logging
accesslog = "-" # stdout
errorlog = "-"  # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process Naming
proc_name = "opsforge-backend"

# Graceful Reloading
graceful_timeout = 30
