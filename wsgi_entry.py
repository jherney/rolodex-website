"""
Production WSGI entry point for Rolodex Contacts app.
Used by gunicorn:  gunicorn -c gunicorn_config.py wsgi_entry:app
"""
from app import app as application

# Expose as `app` for gunicorn's default module:attribute convention
app = application

# For `python3 wsgi_entry.py` direct execution (debug/dev)
if __name__ == '__main__':
    from app import HOST, PORT, DEBUG
    application.run(host=HOST, port=PORT, debug=DEBUG)
