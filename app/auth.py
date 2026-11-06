"""Admin sign-in: a login page that sets a signed cookie, instead of the browser's password pop-up."""
import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, List, Optional
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.templating import templates

COOKIE = "admin_session"
SESSION_SECONDS = 12 * 60 * 60
MAX_FAILURES = 5
LOCKOUT_SECONDS = 10 * 60

_failures: Dict[str, List[float]] = {}


def configured() -> bool:
    return bool(settings.admin_user and settings.admin_pass)


def _secret() -> bytes:
    # SECRET_KEY wins if set; otherwise derive one from the admin login, so changing the password signs everyone out.
    explicit = os.getenv("SECRET_KEY", "")
    material = explicit or f"admin-session:{settings.admin_user}:{settings.admin_pass}"
    return hashlib.sha256(material.encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_session(now: Optional[float] = None) -> str:
    payload = f"{settings.admin_user}|{int((now or time.time()) + SESSION_SECONDS)}"
    return f"{payload}|{_sign(payload)}"


def valid_session(token: str, now: Optional[float] = None) -> bool:
    try:
        user, expires, signature = token.rsplit("|", 2)
    except ValueError:
        return False
    payload = f"{user}|{expires}"
    return (
        configured()
        and hmac.compare_digest(signature, _sign(payload))
        and secrets.compare_digest(user.encode(), settings.admin_user.encode())
        and expires.isdigit()
        and int(expires) > (now or time.time())
    )


def credentials_ok(username: str, password: str) -> bool:
    return (
        configured()
        and secrets.compare_digest(username.encode(), settings.admin_user.encode())
        and secrets.compare_digest(password.encode(), settings.admin_pass.encode())
    )


def _basic_auth_ok(request: Request) -> bool:
    """Scripts and tests may still send a username and password with the request (HTTP Basic)."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        username, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return credentials_ok(username, password)


def is_signed_in(request: Request) -> bool:
    return valid_session(request.cookies.get(COOKIE, "")) or _basic_auth_ok(request)


def _same_site(request: Request) -> bool:
    origin = request.headers.get("origin")
    return not origin or urlsplit(origin).netloc == request.headers.get("host")


def safe_next(target: str) -> str:
    """Only send people back to admin pages on this site after signing in."""
    if target.startswith("/admin") and not target.startswith("//") and "\\" not in target and not target.startswith("/admin/login"):
        return target
    return "/admin"


def require_admin(request: Request) -> None:
    if not is_signed_in(request):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if request.method != "GET":  # a form posted after the session ran out: come back to the page it was on
            target = urlsplit(request.headers.get("referer", "")).path or "/admin"
        raise HTTPException(status_code=303, headers={"Location": f"/admin/login?next={quote(safe_next(target))}"})
    # Browsers send the session cookie automatically, so refuse form posts that come from another site.
    if request.method == "POST" and not _same_site(request):
        raise HTTPException(status_code=403, detail="Cross-site request refused")


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _locked_out(client: str, now: float) -> bool:
    recent = [t for t in _failures.get(client, []) if now - t < LOCKOUT_SECONDS]
    _failures[client] = recent
    return len(recent) >= MAX_FAILURES


router = APIRouter(prefix="/admin")


def render_login(request: Request, next_url: str, error: str = "", username: str = "", status_code: int = 200, signed_out: bool = False):
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"next_url": next_url, "error": error, "username": username, "configured": configured(), "signed_out": signed_out},
        status_code=status_code,
    )


@router.get("/login")
def login_page(request: Request, next: str = "/admin", signed_out: str = ""):
    if is_signed_in(request):
        return RedirectResponse(safe_next(next), status_code=303)
    return render_login(request, safe_next(next), signed_out=bool(signed_out))


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/admin")):
    next_url = safe_next(next)
    if not _same_site(request):
        raise HTTPException(status_code=403, detail="Cross-site request refused")
    now = time.time()
    client = _client(request)
    if _locked_out(client, now):
        return render_login(request, next_url, "Too many wrong attempts. Wait 10 minutes and try again.", username, 429)
    if not credentials_ok(username.strip(), password):
        _failures.setdefault(client, []).append(now)
        time.sleep(0.4)  # slows down guessing
        return render_login(request, next_url, "That username or password is wrong.", username, 400)
    _failures.pop(client, None)
    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        COOKIE, make_session(now), max_age=SESSION_SECONDS, path="/admin",
        httponly=True, samesite="lax", secure=request.url.scheme == "https",
    )
    return response


@router.post("/logout")
def logout(request: Request):
    if not _same_site(request):
        raise HTTPException(status_code=403, detail="Cross-site request refused")
    response = RedirectResponse("/admin/login?signed_out=1", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response
