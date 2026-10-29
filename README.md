# Rolodex Contacts

A desk-rolodex style contact manager: Flask + PostgreSQL backend, per-account sign-in, and a vintage card-file UI served at `/` (and `/vintage/`). Import JSON, CSV or vCard with a preview, find and merge duplicates, keep reminders and an activity log per contact, and optionally enrich contacts with Fireworks AI.

## Quick start

Needs Docker with Compose v2.

```bash
git clone https://github.com/jherney/rolodex-website.git
cd rolodex-website
./runner.sh up
```

`up` builds the image, starts a throwaway stack with its own empty database, waits for `/ready`, runs the smoke tests and ends with one line:

```
RESULT: pass url=http://127.0.0.1:5000 project=dxr-rolodex-website-1234567890 elapsed=60s stop="./runner.sh down" (the port changes if the app container restarts)
```

Open the URL and create an account. If port 5000 is free you get 5000; otherwise (or with several checkouts running at once) Docker picks a free port and the RESULT line shows it. Stop and delete the stack with `./runner.sh down`.

| Command | What it does |
|---|---|
| `./runner.sh up` | Fresh stack (database wiped every time), wait for `/ready`, smoke tests |
| `./runner.sh smoke` | Smoke tests against the running stack; rerun `up` after editing code |
| `./runner.sh test` | `up`, then the failure-path checks, then `down` (what CI runs) |
| `./runner.sh down` | Remove the stack, its database and its images |

Exit codes: `0` pass, `1` tests failed, `2` Docker missing or not running, `3` the stack never became ready, `4` the build failed.

### Without Docker

The app needs a PostgreSQL database. Point it at one and run Flask directly (it creates its tables on start):

```bash
pip install -r requirements.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/rolodex ROLODEX_DEBUG=1 python3 app.py
# Open http://localhost:5000
```

Without `DATABASE_URL` it connects with the `ROLODEX_DB_*` settings below (default `rolodex:rolodex123@localhost:5432/rolodex`). If it can't connect, startup ends with one line naming the host and port it tried.

## Running it for real

**Docker Compose** (app + Postgres 16, data in the `rolodex-pgdata` volume, app published on `127.0.0.1` only):

```bash
ROLODEX_SECRET_KEY=$(openssl rand -hex 32) docker compose up -d --build
```

**Gunicorn on a VM** (bring your own Postgres):

```bash
pip install -r requirements.txt
gunicorn -c gunicorn_config.py wsgi_entry:app
```

**Vercel**: the project is linked (`.vercel/`). Set `ROLODEX_SECRET_KEY` and connect a Postgres integration (Neon sets `DATABASE_URL`, Supabase sets `POSTGRES_URL`). The app refuses to start on Vercel without `ROLODEX_SECRET_KEY`.

The app binds to loopback by default. To reach it from other machines, put a reverse proxy with HTTPS in front and set `ROLODEX_SECURE_COOKIES=1`.

### Session key

Sign-in cookies are signed with `ROLODEX_SECRET_KEY`. If you don't set it (local and Compose runs), the app generates one key on first start and stores it in the database's `app_settings` table, so every worker and every restart shares it. Anyone who can read that database can forge sessions; set the variable yourself to keep the key out of the database. `VERCEL` or `ROLODEX_ENV=production` makes the variable mandatory.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ROLODEX_PORT` | `5000` | Port to listen on. For `docker compose`, the host port; empty means Docker picks one |
| `ROLODEX_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` inside the container) |
| `ROLODEX_DEBUG` | `0` | Flask debug mode for `python3 app.py` |
| `ROLODEX_SECRET_KEY` | _(generated, stored in the DB)_ | Signs session cookies; required on Vercel and with `ROLODEX_ENV=production` |
| `ROLODEX_ENV` | _(empty)_ | `production` makes `ROLODEX_SECRET_KEY` mandatory |
| `ROLODEX_SECURE_COOKIES` | _(empty)_ | Any value marks the session cookie Secure (automatic on Vercel) |
| `ROLODEX_CORS_ORIGIN` | _(empty)_ | Allowed CORS origin; empty means same-origin only |
| `DATABASE_URL` | _(empty)_ | Postgres connection URL; takes precedence over `ROLODEX_DB_*` |
| `POSTGRES_URL` | _(empty)_ | Used when `DATABASE_URL` is unset (Supabase on Vercel) |
| `ROLODEX_DB_HOST` | `localhost` | Postgres host (`db` in Compose) |
| `ROLODEX_DB_PORT` | `5432` | Postgres port |
| `ROLODEX_DB_NAME` | `rolodex` | Database name |
| `ROLODEX_DB_USER` | `rolodex` | Database user |
| `ROLODEX_DB_PASSWORD` | `rolodex123` | Database password; change it anywhere real |
| `ROLODEX_VINTAGE_DIR` | `./vintage-rolodex` | Folder the UI is served from (`/app/vintage` in the image) |
| `FIREWORKS_API_KEY` | _(empty)_ | Enables the AI endpoints; without it they return a 500 error |
| `FIREWORKS_API_URL` | `https://api.fireworks.ai/inference/v1` | Fireworks API endpoint |
| `FIREWORKS_MODEL` | `accounts/fireworks/models/deepseek-v4-flash` | Model used for enrichment and search |
| `ROLODEX_WORKERS` | CPU cores × 2 + 1 | Gunicorn workers (`4` in Compose) |
| `ROLODEX_TIMEOUT` | `30` | Gunicorn worker timeout, seconds |
| `ROLODEX_KEEPALIVE` | `5` | Gunicorn keep-alive, seconds |
| `ROLODEX_LOG_LEVEL` | `info` | Gunicorn log level |
| `ROLODEX_ACCESS_LOG` | `-` (stdout) | Gunicorn access log path |
| `ROLODEX_ERROR_LOG` | `-` (stderr) | Gunicorn error log path |

`tests/check_env_docs.py` fails CI when the code reads a variable this table doesn't list.

## API

Every `/api/v1` route except the auth routes needs a signed-in session cookie. Without one you get `401` with a `hint` naming the sign-in call. Errors are JSON: `{"error": "..."}`; server errors add an `id` that matches one line in the server log.

```bash
# Sign up (or POST /api/v1/auth/login with the same body), keeping the session cookie
curl -s -c jar -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"at-least-10-chars"}' \
  http://127.0.0.1:5000/api/v1/auth/signup

# Use the cookie on every call
curl -s -b jar http://127.0.0.1:5000/api/v1/contacts
curl -s -b jar -H 'Content-Type: application/json' -d '{"name":"Ada Lovelace","email":"ada@example.com"}' \
  http://127.0.0.1:5000/api/v1/contacts
```

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/signup` | Create an account and sign in (`email`, `password` ≥ 10 chars) |
| POST | `/api/v1/auth/login` | Sign in; 5 failures lock an email and 20 lock an IP for 15 minutes |
| POST | `/api/v1/auth/logout` | Sign out |
| GET | `/api/v1/auth/me` | `{"email": ...}`, or `null` when signed out |
| GET | `/api/v1/contacts` | List contacts (`?search=`, `?tag=`) |
| POST | `/api/v1/contacts` | Create a contact (`name` required) |
| PUT | `/api/v1/contacts/:id` | Update a contact |
| DELETE | `/api/v1/contacts/:id` | Delete a contact |
| GET | `/api/v1/tags` | Tags with counts |
| GET | `/api/v1/duplicates` | Possible duplicate pairs (`?threshold=0.7`) |
| POST | `/api/v1/merge` | Merge `secondary_id` into `primary_id`; `keep_existing: true` keeps the primary's values |
| POST | `/api/v1/bulk` | `action`: `delete`, `tag`, `untag` or `export` over `ids` |
| POST | `/api/v1/import/preview` | Report each row of a JSON/CSV/vCard file as new, possible duplicate or skipped; writes nothing |
| POST | `/api/v1/import` | Import a JSON/CSV/vCard file, skipping contacts you already have |
| GET/POST | `/api/v1/contacts/:id/reminders` | List or add reminders (`title`, `due_date`) |
| POST | `/api/v1/reminders/:id/complete` | Mark a reminder done |
| DELETE | `/api/v1/reminders/:id` | Delete a reminder |
| GET/POST | `/api/v1/contacts/:id/activities` | List or log activities (`type`, `subject`) |
| POST | `/api/v1/ai/enrich` | Suggest tags and a summary (needs `FIREWORKS_API_KEY`) |
| POST | `/api/v1/ai/auto-categorize` | Tag all untagged contacts (needs `FIREWORKS_API_KEY`) |
| POST | `/api/v1/ai/search` | Natural-language search (needs `FIREWORKS_API_KEY`) |
| GET | `/get_contacts` | Legacy: all of your contacts |
| POST | `/save_contacts` | Legacy and **destructive**: replaces all of your contacts with the posted list |
| GET | `/health` | Liveness: always `200`; `status` is `healthy` or `degraded` |
| GET | `/ready` | Readiness: `200` when the database answers, else `503` |

## Upgrading

- **Contacts from before accounts existed** have no owner, so nobody sees them. On startup the app logs how many there are. Give them to an account (sign up first):

  ```bash
  # Any database you can reach from this machine (local, Neon, Supabase)
  DATABASE_URL=postgresql://user:pass@host:5432/rolodex python3 migrate_to_postgres.py --claim-orphans --owner you@example.com

  # A Docker Compose deployment (the database isn't published to the host)
  docker compose run --rm -v "$PWD/migrate_to_postgres.py:/app/migrate_to_postgres.py:ro,z" \
    app python3 migrate_to_postgres.py --claim-orphans --owner you@example.com
  ```

- **Importing an old `contacts.json`** now needs an owner: `python3 migrate_to_postgres.py --owner you@example.com [--file contacts.json]`. With Compose, add `-v "$PWD/contacts.json:/app/contacts.json:ro,z"` to the command above.
- **Sessions reset once** when you upgrade without `ROLODEX_SECRET_KEY` set: the generated key now lives in the database instead of in each process, so everyone signs in again one time.
- **`runner.sh start`, `stop` and `restart` are gone.** Use `./runner.sh up` / `down` for a test stack, or the gunicorn command above for a VM.
- **Compose host port**: an empty `ROLODEX_PORT` now means "Docker picks a port"; unset still means 5000.

## Testing

```bash
./runner.sh test                                         # everything, in a throwaway stack
BASE_URL=http://127.0.0.1:5000 python3 tests/api_integration_smoke.py   # smoke tests against any server
python3 tests/check_env_docs.py                          # README lists every env var the code reads
```

The smoke tests sign up fresh `@example.test` accounts on every run; don't point them at a database with real data you care about.
