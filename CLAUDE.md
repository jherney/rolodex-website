# Rolodex Contacts — Production App

Flask backend + HTML/CSS/JS frontend with Glassmorphism UI + 3D CSS rolodex wheel.

## Essential Commands

**Development:**
```bash
python3 app.py
# Open http://localhost:5000
```

**Production:**
```bash
gunicorn -c gunicorn_config.py wsgi_entry:app                    # bare metal
docker compose up -d --build                                      # containerized
./runner.sh start / stop / restart / smoke / test                 # via runner
```

**Reset data:**
```bash
echo '[]' > contacts.json
```

**Test suite:**
```bash
python3 tests/api_integration_smoke.py
```

## Configuration (Environment Variables)
| Variable | Default | Description |
|---|---|---|
| `ROLODEX_PORT` | `5000` | Port to bind |
| `ROLODEX_DEBUG` | `0` | Flask debug mode |
| `ROLODEX_WORKERS` | auto | Gunicorn workers |
| `ROLODEX_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` inside Docker) |
| `ROLODEX_CORS_ORIGIN` | _(empty)_ | CORS origin; empty = same-origin only |
| `FIREWORKS_API_KEY` | — | Fireworks AI for AI features |

## Production Checklist
- [ ] Set `ROLODEX_SECRET_KEY` to a strong random value
- [ ] Set `FIREWORKS_API_KEY` via env (not hardcoded)
- [ ] Bind to `127.0.0.1` and use nginx reverse proxy for production
- [ ] Set `ROLODEX_CORS_ORIGIN` to specific domain (not `*`)
- [ ] Configure `docker compose` with persistent volume for contacts.json
- [ ] Set `ROLODEX_LOG_LEVEL=warning` in production
- [ ] Run smoke tests before deployment: `./runner.sh test`

## Vintage frontend (`vintage-rolodex/`)
A second, desk-rolodex style frontend. Flask serves it at `/vintage/` (from `ROLODEX_VINTAGE_DIR`, default `../vintage-rolodex`) and it uses `/api/v1/contacts`; opened as a plain file it falls back to localStorage. It splits the API's single `name` into first/last (last word = surname) and uses the `company`/`title` columns, which `init_db()` adds if missing. The Docker image copies it to `/app/vintage` from a named build context: `docker compose` passes it automatically; a plain build needs `docker build --build-context vintage=../vintage-rolodex .`

## Gotchas / Conventions
- **Postgres in compose**: the `db` service (postgres:16, volume `rolodex-pgdata`) is not published to the host; the app reaches it as `db:5432`. Credentials come from `ROLODEX_DB_NAME/USER/PASSWORD` (defaults match `app.py`)
- **SELinux**: Fedora requires `:z` suffix on podman bind mounts (e.g. `.:/app:z`)
- **Mobile**: Panel/controls collapse responsively; test on mobile after changes
- **CORS / exposure**: CORS headers are only sent when `ROLODEX_CORS_ORIGIN` is set. The API has no auth, so it binds to loopback by default and compose publishes it on `127.0.0.1` only
- **Tests**: never point tests at a database with real data; `/save_contacts` replaces the whole table
- **File writes**: Contacts are written atomically via temp-file + rename
- **AI features**: Require `FIREWORKS_API_KEY` env var; silently degrade when unset

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. Route only to skills in the session's available-skills list; answer directly for quick questions or small scoped edits.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate, unless one read-only check confirms the cause and a narrow fix (then fix it and run the focused test)
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
