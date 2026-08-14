# Render deployment with SQLite kept on your PC

## What this does

**Render:** hosts FastAPI/Jinja and Google OAuth only.  
**Your PC:** keeps `ledger.db` and `credit.db`.  
**PC data API:** exposes database operations through HTTPS; it is protected by `DATA_API_TOKEN`.

The database files are intentionally absent from this project.

## Render files

Upload to GitHub:
- `main.py`
- `database.py`
- `credit.py`
- `auth.py`
- `templates/`
- `static/`
- `requirements.txt`
- `render.yaml`

Do NOT upload:
- `.env`
- `ledger.db`
- `credit.db`
- `database_local.py`
- `credit_local.py`
- `data_server.py`
- PC batch files

## PC files

Keep these on the PC, next to your existing `ledger.db` and `credit.db`:
- `data_server.py`
- `database_local.py`
- `credit_local.py`
- `pc_requirements.txt`

Create a PC `.env` containing:

`DATA_API_TOKEN=<long-random-secret>`

Install and run:

`pip install -r pc_requirements.txt`

`python -m uvicorn data_server:app --host 127.0.0.1 --port 8001`

Then expose **only port 8001** using an HTTPS tunnel. Cloudflare Tunnel is one option. Prefer a stable named tunnel/custom hostname for production; a quick tunnel URL can change after restart.

Set that HTTPS URL as `DATA_API_URL` in Render.

## Render environment variables

Set these in Render:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `ALLOWED_EMAILS`
- `SESSION_SECRET`
- `DATA_API_URL`
- `DATA_API_TOKEN`
- `OAUTH_REDIRECT_URI`
- `SESSION_HTTPS_ONLY=true`

`DATA_API_TOKEN` must be identical on the PC and Render.

## Google OAuth callback URL

After creating the Render Web Service, Render gives you a URL like:

`https://petty-cash-ledger.onrender.com`

Your Google OAuth **Authorized redirect URI** should then be:

`https://petty-cash-ledger.onrender.com/auth/callback`

Use your actual Render service name.

Google requires the redirect URI to match exactly.

## Important security step

The ZIP you uploaded contained a real Google OAuth client secret and a session secret. Rotate the Google OAuth client secret in Google Cloud before deploying, and generate new random values for `SESSION_SECRET` and `DATA_API_TOKEN`.

Never commit `.env` or database files to GitHub.
