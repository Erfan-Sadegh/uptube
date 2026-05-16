import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import TokenCipher
from app.db import get_db
from app.models import Job, User, YoutubeAccount
from app.services.youtube import YOUTUBE_SCOPES

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.post("/start")
def start_google_oauth(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")
    state = secrets.token_urlsafe(24)
    response.set_cookie(
        settings.oauth_state_cookie_name,
        state,
        httponly=True,
        samesite="lax",
        max_age=10 * 60,
    )
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.youtube_redirect_uri,
        "response_type": "code",
        "scope": " ".join(["openid", "email", *YOUTUBE_SCOPES]),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return {"url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}", "state": state}


@router.get("/callback")
def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    stored_state: str | None = Cookie(default=None, alias=get_settings().oauth_state_cookie_name),
    current_user_id: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Google OAuth state is invalid")

    token_data = _exchange_code_for_token(code, settings)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=400, detail="Google did not return the required tokens")

    userinfo = _get_userinfo(access_token)
    email = userinfo.get("email")
    google_sub = userinfo.get("sub")
    if not email or not google_sub:
        raise HTTPException(status_code=400, detail="Google userinfo response is incomplete")

    user = _resolve_oauth_user(db, current_user_id, email)
    db.add(user)
    db.flush()

    cipher = TokenCipher(settings.token_encryption_key)
    account = user.youtube_account or YoutubeAccount(
        user_id=user.id,
        google_sub=google_sub,
        encrypted_refresh_token="",
        scopes=token_data.get("scope", ""),
    )
    account.google_sub = google_sub
    account.encrypted_refresh_token = cipher.encrypt(refresh_token)
    account.scopes = token_data.get("scope", "")
    db.add(account)
    db.commit()

    redirect = RedirectResponse(f"{settings.frontend_base_url}?connected=1")
    redirect.set_cookie(
        settings.session_cookie_name,
        user.id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    redirect.delete_cookie(settings.oauth_state_cookie_name)
    return redirect


def _resolve_oauth_user(db: Session, current_user_id: str | None, email: str) -> User:
    current_user = db.scalar(select(User).where(User.id == current_user_id)) if current_user_id else None
    email_user = db.scalar(select(User).where(User.email == email))

    if current_user and email_user and current_user.id != email_user.id:
        db.query(Job).filter(Job.user_id == current_user.id).update({Job.user_id: email_user.id})
        return email_user

    if current_user:
        current_user.email = email
        return current_user

    if email_user:
        return email_user

    return User(email=email)


def _exchange_code_for_token(code: str, settings: Settings) -> dict:
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.youtube_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_userinfo(access_token: str) -> dict:
    response = httpx.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
