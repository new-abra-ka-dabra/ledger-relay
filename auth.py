"""
Google OAuth login + email whitelist + 30-day session cookie.

Only Google accounts whose email is listed in ALLOWED_EMAILS (from .env) may
sign in. On success a signed session cookie is stored on the device for 30
days (Starlette SessionMiddleware, itsdangerous-signed).

Setup (one time) — set these environment variables in Render:
  1. Create Google OAuth credentials at
     https://console.cloud.google.com/apis/credentials
     (Application type: Web application)
   2. Add this Authorized redirect URI:
        https://ledger-relay.onrender.com/auth/callback
  3. Add the client id / secret to the Render environment
  4. Put the allowed Gmail addresses in ALLOWED_EMAILS
"""

import os
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL", "https://ledger-relay.onrender.com"
).rstrip("/")
OAUTH_REDIRECT_URI = os.getenv(
    "OAUTH_REDIRECT_URI", PUBLIC_BASE_URL + "/auth/callback"
)
ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter()
_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "templates"
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def get_current_user(request: Request):
    """FastAPI dependency: return the logged-in user or raise 401."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    allowed = ", ".join(sorted(ALLOWED_EMAILS))
    return templates.TemplateResponse(
        request, "login.html", {"allowed": allowed}
    )


def public_base_url(request: Request) -> str:
    """Return the configured Render origin, not a request-controlled origin."""
    return PUBLIC_BASE_URL


@router.get("/auth/login")
async def auth_login(request: Request):
    origin = public_base_url(request)
    return await oauth.google.authorize_redirect(request, OAUTH_REDIRECT_URI)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(
        request, redirect_uri=OAUTH_REDIRECT_URI
    )
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await oauth.google.userinfo(token)
    email = (user_info.get("email") or "").lower()
    if email not in ALLOWED_EMAILS:
        request.session.clear()
        raise HTTPException(
            status_code=403,
            detail="This Google account is not on the allowed list.",
        )
    request.session["user"] = {
        "email": email,
        "name": user_info.get("name", ""),
    }
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)