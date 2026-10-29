# TODOS

## Security: audit sign-in throttling and API-key loading (run /cso)

- **What:** Review two security smells found during the 2026-10-28 DX review.
  1. `_client_ip()` (`app.py:381-383`) trusts `X-Forwarded-For` from any client. On a self-hosted install with no proxy, an attacker can rotate that header and skip the 20-failures-per-IP lock (the 5-per-email lock still holds). On Vercel the header is set by the platform, so the fix needs a trusted-proxy setting (for example, trust XFF only when `VERCEL` or a `ROLODEX_TRUSTED_PROXIES` value is set).
  2. `app.py:55-62` falls back to reading the Fireworks API key from `/tmp/fireworks_key.txt`, a path any local user can write to.
- **Why:** Brute-force protection is weaker than the code comments claim, and a planted key file redirects AI calls to someone else's account.
- **Pros:** Closes real gaps before the app is exposed beyond loopback.
- **Cons:** Must not break real client IPs on Vercel.
- **Context:** `app.py:376-433` (throttling), `app.py:55-62` (key loading). Related: a successful sign-in clears only the email counter, never the IP counter (`app.py:427-433`).
- **Depends on:** nothing.

## Cleanup: remove the dead classic UI and the unused Vault wiring

- **What:** Delete code that looks live but isn't.
  1. The classic 3D UI: no route serves its `index.html` (`/` and `/vintage/` serve the vintage UI, `app.py:302-331`), yet `/app.js`, `/styles.css`, `/manifest.json` and `/sw.js` are still routed (`app.py:307-321`). The vintage UI loads none of them.
  2. Vault: `secrets_loader.py` is imported nowhere, `hvac` is commented out of `requirements.txt`, and compose still defines a `vault` service under the `with-vault` profile.
- **Why:** Agents edit code nobody sees (PR #1 changed the classic UI's merge dialog).
- **Pros:** Smaller surface to read, test and document.
- **Cons:** Hard to undo if you meant to revive either one. Browsers that installed the classic service worker at `/` will drop it once `/sw.js` returns 404 (the desired outcome, but intentional).
- **Context:** files `index.html`, `app.js`, `styles.css`, `sw.js`, `manifest.json`, `secrets_loader.py`, the `vault` service in `docker-compose.yml`, the `README.md` Vault/Features sections.
- **Depends on:** the README rewrite (T6 in the DX plan) landing first.
