from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from pos_service import auth as auth_service
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSUser
from pos_service.schemas import ChangePasswordRequest, LoginRequest, UserInfo

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_info(user: POSUser, expires_at) -> UserInfo:
    return UserInfo(
        username=user.username,
        display_name=user.display_name,
        expires_at=expires_at,
        must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=UserInfo)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserInfo:
    user = db.get(POSUser, body.username)
    if user is None or not user.is_active or not auth_service.verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    sess = auth_service.create_session(db, user.username, settings.session_ttl_hours)
    response.set_cookie(
        key=auth_service.SESSION_COOKIE,
        value=sess.session_token,
        httponly=True,
        samesite="strict",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return _user_info(user, sess.expires_at)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    token = request.cookies.get(auth_service.SESSION_COOKIE)
    if token:
        auth_service.revoke_session(db, token)
    response.delete_cookie(auth_service.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
def me(ctx: auth_service.AuthContext = Depends(auth_service.get_auth)) -> UserInfo:
    return _user_info(ctx.user, ctx.session.expires_at)


@router.post("/change-password", response_model=UserInfo)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> UserInfo:
    if not auth_service.verify_password(body.current_password, ctx.user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "new_password_must_differ"},
        )
    auth_service.change_password(db, ctx.user, body.new_password)
    return _user_info(ctx.user, ctx.session.expires_at)
