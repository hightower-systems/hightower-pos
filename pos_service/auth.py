import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSSession, POSUser

SESSION_COOKIE = "pos_session"


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_session(db: Session, username: str, ttl_hours: int) -> POSSession:
    token = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(hours=ttl_hours)
    sess = POSSession(session_token=token, username=username, expires_at=expires)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def revoke_session(db: Session, token: str) -> None:
    sess = db.get(POSSession, token)
    if sess is not None:
        db.delete(sess)
        db.commit()


def peek_session(db: Session, token: str) -> POSSession | None:
    """Return the session row for a token without revoking it.

    Used by the logout handler to look up the cashier so it can
    check for an open till before clearing the cookie -- read-only,
    so it doesn't need its own commit."""
    return db.get(POSSession, token)


@dataclass
class AuthContext:
    user: POSUser
    session: POSSession


def get_auth(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "not_authenticated"},
        )
    sess = db.get(POSSession, token)
    if sess is None or sess.expires_at < now_utc():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "session_expired"},
        )
    user = db.get(POSUser, sess.username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user_inactive"},
        )
    return AuthContext(user=user, session=sess)


def get_current_user(auth: AuthContext = Depends(get_auth)) -> POSUser:
    if auth.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "password_change_required"},
        )
    return auth.user


def change_password(db: Session, user: POSUser, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
