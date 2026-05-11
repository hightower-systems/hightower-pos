"""Admin user management: create / list / soft-delete / reset password.

No role gating in v1 -- any authenticated cashier can manage users
(per Mike: 'no need for roles, all same permission level'). The
auth layer already requires a valid session cookie, and a few
self-protective rules prevent the obvious footguns:

- You cannot deactivate yourself (would log you out of the current
  session; recoverable only by another cashier).
- You cannot deactivate the last active user (would lock the
  entire system out).
- You cannot reset your own password from this surface -- use the
  self-service /api/auth/change-password flow which requires the
  current password.

Soft delete only: POSSession FKs reference pos_users.username, so a
hard delete would either violate the FK or orphan session rows
(both bad). is_active=false is the canonical retired state and
get_auth refuses the user on every subsequent request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pos_service import auth as auth_service
from pos_service.db import get_db
from pos_service.models import POSUser
from pos_service.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    UsersListResponse,
    UserSummary,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


def _row_to_summary(row: POSUser) -> UserSummary:
    return UserSummary(
        username=row.username,
        display_name=row.display_name,
        is_active=row.is_active,
        must_change_password=row.must_change_password,
        created_at=row.created_at,
    )


@router.get("", response_model=UsersListResponse)
def list_users(
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> UsersListResponse:
    """All users, active or not. Sorted by username for deterministic
    rendering in the settings UI."""
    _ = ctx
    stmt = select(POSUser).order_by(POSUser.username.asc())
    rows = list(db.execute(stmt).scalars())
    return UsersListResponse(users=[_row_to_summary(r) for r in rows])


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> UserSummary:
    """Create a new cashier. Initial password is forced-change on
    first login so the admin can hand the cashier a temp password
    without it remaining the long-term credential.

    Username collision (including with a soft-deleted row) returns
    409. The CLI already has a create-user command; this endpoint
    is its HTTP equivalent for the settings UI.
    """
    _ = ctx
    existing = db.get(POSUser, body.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "username_exists"},
        )
    user = POSUser(
        username=body.username,
        password_hash=auth_service.hash_password(body.initial_password),
        display_name=body.display_name,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _row_to_summary(user)


@router.delete("/{username}", response_model=UserSummary)
def deactivate_user(
    username: str,
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> UserSummary:
    """Soft delete: set is_active=false. The user can no longer log
    in and existing sessions are invalidated on next request (the
    get_auth dependency rechecks is_active each call).

    Guards:
    - Refuse self-deactivation (would log out the current session
      with no way back).
    - Refuse deactivating the last active user (would lock everyone
      out; the admin must add another active cashier first).
    """
    if username == ctx.user.username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "cannot_deactivate_self"},
        )
    user = db.get(POSUser, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found"},
        )
    if not user.is_active:
        # Already deactivated; idempotent no-op for client safety.
        return _row_to_summary(user)
    active_count = db.execute(
        select(func.count(POSUser.username)).where(POSUser.is_active.is_(True))
    ).scalar_one()
    if active_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "last_active_user"},
        )
    user.is_active = False
    db.commit()
    db.refresh(user)
    return _row_to_summary(user)


@router.post("/{username}/reset-password", response_model=UserSummary)
def reset_password(
    username: str,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> UserSummary:
    """Admin-issued password reset for another cashier. Sets
    must_change_password=true so the cashier is forced into the
    change-password flow on next login. Self-reset is refused --
    use /api/auth/change-password (which requires the current
    password) for that.
    """
    if username == ctx.user.username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "cannot_reset_own_password_here"},
        )
    user = db.get(POSUser, username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found"},
        )
    user.password_hash = auth_service.hash_password(body.new_password)
    user.must_change_password = True
    db.commit()
    db.refresh(user)
    return _row_to_summary(user)
