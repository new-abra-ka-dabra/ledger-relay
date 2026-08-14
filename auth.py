"""Google OAuth for the Render-hosted app."""
import os
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
load_dotenv()
GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID","")
GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET","")
OAUTH_REDIRECT_URI=os.getenv("OAUTH_REDIRECT_URI","").rstrip("/")
ALLOWED_EMAILS={e.strip().lower() for e in os.getenv("ALLOWED_EMAILS","").split(",") if e.strip()}
oauth=OAuth()
oauth.register(name="google",client_id=GOOGLE_CLIENT_ID,client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope":"openid email profile"})
router=APIRouter()
templates=Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)),"templates"))
def get_current_user(request: Request):
    user=request.session.get("user")
    if not user: raise HTTPException(status_code=401,detail="Not authenticated")
    return user
@router.get("/login",response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request,"login.html",{"allowed":", ".join(sorted(ALLOWED_EMAILS))})
def public_base_url(request: Request):
    host=request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto=request.headers.get("x-forwarded-proto") or "https"
    return f"{proto}://{host}"
@router.get("/auth/login")
async def auth_login(request: Request):
    redirect_uri=OAUTH_REDIRECT_URI or public_base_url(request)+"/auth/callback"
    return await oauth.google.authorize_redirect(request,redirect_uri)
@router.get("/auth/callback")
async def auth_callback(request: Request):
    redirect_uri=OAUTH_REDIRECT_URI or public_base_url(request)+"/auth/callback"
    token=await oauth.google.authorize_access_token(request,redirect_uri=redirect_uri)
    user_info=token.get("userinfo") or await oauth.google.userinfo(token)
    email=(user_info.get("email") or "").strip().lower()
    if email not in ALLOWED_EMAILS:
        request.session.clear()
        raise HTTPException(status_code=403,detail="This Google account is not on the allowed list.")
    request.session["user"]={"email":email,"name":user_info.get("name","")}
    return RedirectResponse(url="/",status_code=303)
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login",status_code=303)
