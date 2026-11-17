"""Production WSGI entry point for Rolodex Contacts app.
Used by gunicorn:  gunicorn -c gunicorn_config.py wsgi_entry:app
"""
from app import app as application

# Expose as `app` for gunicorn's default module:attribute convention
app = application
