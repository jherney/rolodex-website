# Rolodex Contacts

A modern, production-ready 3D rolodex-style contact manager with Glassmorphism UI, PWA support, offline-first architecture, and optional AI enrichment via Fireworks AI.

## Quick Start (Development)

```bash
cd rolodex-website
python3 app.py
# Open http://localhost:5000
```

Set environment variables to configure:
```bash
ROLODEX_PORT=8080 python3 app.py
ROLODEX_DEBUG=1 python3 app.py     # Enable Flask debug mode
```

## Production Deployment

### Via Gunicorn (bare metal / VM)

```bash
# Install dependencies
pip install -r requirements.txt

# Start with gunicorn config
gunicorn -c gunicorn_config.py wsgi_entry:app

# Or via runner script
./runner.sh start
./runner.sh stop
```

### Via Docker Compose (recommended)

```bash
docker compose up -d --build
```

Without Vault (default):
```bash
docker compose --profile "" up -d --build
```

With Vault secrets management:
```bash
docker compose --profile with-vault up -d --build
```

### Configuration (12-Factor App)

| Variable | Default | Description |
|---|---|---|
| `ROLODEX_PORT` | `5000` | HTTP listen port |
| `ROLODEX_DEBUG` | `0` | Enable Flask debug mode |
| `ROLODEX_WORKERS` | `auto` | Gunicorn worker count |
| `ROLODEX_LOG_LEVEL` | `info` | Log level |
| `ROLODEX_HOST` | `127.0.0.1` | Bind address (the API has no auth; the Docker image uses `0.0.0.0` and compose publishes to host loopback) |
| `ROLODEX_CORS_ORIGIN` | _(empty)_ | CORS allowed origin; empty = same-origin only |
| `ROLODEX_SECRET_KEY` | `change-this-in-production` | Flask secret key |
| `FIREWORKS_API_KEY` | — | Fireworks AI key for AI features |
| `FIREWORKS_API_URL` | `https://api.fireworks.ai/inference/v1` | Fireworks API endpoint |
| `VAULT_ADDR` | — | HashiCorp Vault address (optional) |
| `VAULT_TOKEN` | — | Vault authentication token |

### Health Checks

- `GET /health` — liveness probe (returns `{"status": "healthy"}`)
- `GET /ready` — readiness probe (returns `{"status": "ready"}` when contacts.json is loadable)

## API Reference

### Legacy Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/get_contacts` | Get all contacts |
| POST | `/save_contacts` | Save contacts (list) |

### v1 API

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/contacts` | List contacts (`?search=` and `?tag=` filters) |
| POST | `/api/v1/contacts` | Create contact |
| PUT | `/api/v1/contacts/:id` | Update contact |
| DELETE | `/api/v1/contacts/:id` | Delete contact |
| GET | `/api/v1/tags` | List all tags with counts |
| GET | `/api/v1/duplicates` | Detect duplicate contacts (`?threshold=0.7`) |
| POST | `/api/v1/bulk` | Bulk operations (delete/tag/untag/export) |
| POST | `/api/v1/import` | Import contacts (JSON, CSV, vCard) |

### AI Endpoints (require Fireworks API key)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/ai/enrich` | Suggest tags + summary for a contact |
| POST | `/api/v1/ai/auto-categorize` | Auto-tag all untagged contacts |
| POST | `/api/v1/ai/search` | Natural language semantic search |

## Features

- **3D Rolodex Wheel** — Drag, scroll, or use arrow keys to spin through contacts
- **Tags System** — Custom multi-tags instead of fixed categories
- **Bulk Operations** — Ctrl+B to toggle bulk mode, then tag/delete/export
- **Quick Actions** — Hover on cards to Call, Email, or Copy
- **Dark/Light/System Theme** — Persistent toggle
- **PWA / Offline-First** — Installable as app, works offline via service worker
- **AI Enrichment** — Auto-tagging, smart search, and contact enrichment via Fireworks AI
- **Duplicate Detection** — Fuzzy name + exact email/phone matching
- **Import/Export** — JSON, CSV, and vCard formats
- **Keyboard Shortcuts** — Press ⌨️ or `?` to see all shortcuts

## Testing

```bash
# Start the server first, then:
./runner.sh smoke

# Or run full test cycle (start → test → stop):
./runner.sh test

# Direct:
python3 tests/api_integration_smoke.py
```
