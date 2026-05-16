from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import User


def get_current_user(
    db: Session = Depends(get_db),
    user_id: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
) -> User:
    if not user_id:
        raise HTTPException(status_code=401, detail="Session is required")
    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=401, detail="Session is invalid")
    return user
