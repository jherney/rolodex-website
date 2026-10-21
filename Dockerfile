FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py app.py
COPY index.html index.html
COPY app.js app.js
COPY styles.css styles.css
COPY manifest.json manifest.json
COPY sw.js sw.js
COPY wsgi_entry.py wsgi_entry.py
COPY gunicorn_config.py gunicorn_config.py

# Vintage desk-rolodex frontend, served at /vintage/
COPY vintage-rolodex/index.html vintage-rolodex/app.js vintage-rolodex/styles.css /app/vintage/
ENV ROLODEX_VINTAGE_DIR=/app/vintage
# Listen on all interfaces inside the container; publish the port to loopback on the host
ENV ROLODEX_HOST=0.0.0.0

# Create data directory for persistence
RUN mkdir -p /data && chmod 755 /data

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run with gunicorn in production mode
CMD ["gunicorn", "-c", "gunicorn_config.py", "wsgi_entry:app"]
