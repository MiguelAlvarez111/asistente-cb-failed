import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from backend.app.core.config import Settings, get_settings

SESSION_COOKIE = "cbfa_session"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64(digest)


def create_session_token(settings: Settings) -> str:
    payload = _b64(json.dumps({"sub": "operator", "iat": int(time.time()), "nonce": secrets.token_urlsafe(16)}).encode())
    return f"{payload}.{_signature(payload, settings.session_secret)}"


def verify_session_token(token: str | None, settings: Settings) -> bool:
    if not token or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(payload, settings.session_secret)):
        return False
    try:
        data = json.loads(_unb64(payload))
    except Exception:
        return False
    return data.get("sub") == "operator"


def verify_login_secret(secret: str, settings: Settings) -> bool:
    valid_values = [value for value in [settings.app_password, settings.app_access_token] if value]
    if not valid_values and settings.app_env != "production":
        valid_values = ["local-dev-password"]
    return any(hmac.compare_digest(secret, value) for value in valid_values)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=60 * 60 * 12,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def require_auth(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    if not settings.auth_enabled and settings.app_env != "production":
        return
    bearer = request.headers.get("authorization", "")
    if bearer.startswith("Bearer ") and settings.app_access_token:
        token = bearer.removeprefix("Bearer ").strip()
        if hmac.compare_digest(token, settings.app_access_token):
            return
    if verify_session_token(request.cookies.get(SESSION_COOKIE), settings):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

