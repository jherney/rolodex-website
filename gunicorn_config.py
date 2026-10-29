"""
Gunicorn configuration for Rolodex Contacts production deployment.

Usage:
    gunicorn -c gunicorn_config.py wsgi_entry:app

Or override via env:
    ROLODEX_PORT=8080 ROLODEX_WORKERS=8 gunicorn -c gunicorn_config.py wsgi_entry:app
"""
import os
import multiprocessing

# ── Server socket ──────────────────────────────────────────────────────
# Loopback by default; containers set ROLODEX_HOST=0.0.0.0 and publish to host loopback
bind = f"{os.environ.get('ROLODEX_HOST', '127.0.0.1')}:{os.environ.get('ROLODEX_PORT', '5000')}"

# ── Worker processes ───────────────────────────────────────────────────
# Default: number of CPU cores * 2 + 1 (standard gunicorn recommendation)
workers = int(os.environ.get('ROLODEX_WORKERS', str(multiprocessing.cpu_count() * 2 + 1)))
worker_class = 'sync'         # sync workers are fine for this workload
timeout = int(os.environ.get('ROLODEX_TIMEOUT', '30'))
keepalive = int(os.environ.get('ROLODEX_KEEPALIVE', '5'))

# ── Logging ────────────────────────────────────────────────────────────
accesslog = os.environ.get('ROLODEX_ACCESS_LOG', '-')
errorlog = os.environ.get('ROLODEX_ERROR_LOG', '-')
loglevel = os.environ.get('ROLODEX_LOG_LEVEL', 'info')

# ── Process naming ─────────────────────────────────────────────────────
proc_name = 'rolodex'

# ── Graceful reload ────────────────────────────────────────────────────
reload = False                # set True only in dev
spew = False                  # debug tracing (very verbose)

# ── Security ───────────────────────────────────────────────────────────
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
