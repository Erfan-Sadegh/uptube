from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.models import User, uuid
from app.schemas import MeOut

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
def get_me(
    response: Response,
    user_id: str | None = Cookie(default=None, alias=get_settings().session_cookie_name),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    user = db.scalar(select(User).where(User.id == user_id)) if user_id else None
    if not user:
        local_id = uuid()
        user = User(id=local_id, email=f"local-{local_id}@uptube.local")
        db.add(user)
        db.commit()
        db.refresh(user)
        response.set_cookie(
            settings.session_cookie_name,
            user.id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
    db.refresh(user, attribute_names=["youtube_account"])
    account = user.youtube_account
    return MeOut(
        id=user.id,
        email=user.email,
        youtubeConnected=account is not None,
        channelTitle=account.channel_title if account else None,
    )
