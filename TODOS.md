# TODOS

Nothing open. Both items below were resolved on 2026-11-17.

## Resolved: security audit of sign-in throttling and API-key loading

- `app.py:_client_ip()` now trusts `X-Forwarded-For` only when a trusted proxy is configured
  (`VERCEL` or `ROLODEX_TRUSTED_PROXIES` set); otherwise it uses the socket address, so a
  client can't rotate the header to dodge the per-IP lock. A successful sign-in now clears
  both the email and the IP failure counters.

## Resolved: dead code removed

- The classic 3D UI (`index.html`, `app.js`, `styles.css`, `sw.js`, `manifest.json` at the
  repo root) and its static routes in `app.py` are gone; only the vintage UI is served.
- `secrets_loader.py`, the compose `vault` service and the commented `hvac` dependency are gone.
