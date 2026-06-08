from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import clear_session_cookie, create_session_token, set_session_cookie, verify_login_secret, verify_session_token
from backend.app.schemas.auth import LoginRequest, SessionResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response, settings: Settings = Depends(get_settings)) -> SessionResponse:
    if not verify_login_secret(payload.secret, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")
    set_session_cookie(response, create_session_token(settings), settings)
    return SessionResponse(authenticated=True)


@router.post("/logout", response_model=SessionResponse)
def logout(response: Response) -> SessionResponse:
    clear_session_cookie(response)
    return SessionResponse(authenticated=False)


@router.get("/session", response_model=SessionResponse)
def session(request: Request, settings: Settings = Depends(get_settings)) -> SessionResponse:
    if not settings.auth_enabled and settings.app_env != "production":
        return SessionResponse(authenticated=True)
    return SessionResponse(authenticated=verify_session_token(request.cookies.get("cbfa_session"), settings))

