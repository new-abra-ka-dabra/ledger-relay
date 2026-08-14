#!/usr/bin/env bash
# Start the ledger server and expose it publicly via a Cloudflare quick tunnel.
#
# Requirements:
#   pip install fastapi uvicorn jinja2 pydantic authlib python-dotenv itsdangerous httpx
#   cloudflared installed -> https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
#
# cloudflared prints a random https://*.trycloudflare.com URL. Open it on any device.
# For Google OAuth with a changing URL, host relay/auth-callback.html once and set
# OAUTH_REDIRECT_URI to it (see README). Register that URL in Google Console once.
set -e

python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
UV_PID=$!
trap "kill $UV_PID 2>/dev/null" EXIT

cloudflared tunnel --url http://localhost:8000
