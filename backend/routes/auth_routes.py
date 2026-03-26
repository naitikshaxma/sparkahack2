from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import create_access_token, get_authenticated_user
from ..config import get_settings
from ..db import db_session_scope
from ..models.api_models import LoginRequest
from ..models.db_models import User
from .response_utils import standardized_success

router = APIRouter(tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest):
    settings = get_settings()
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    with db_session_scope() as db:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            fallback_name = email.split("@", 1)[0] if "@" in email else email
            user = User(name=(payload.name or fallback_name or "user").strip()[:255], email=email)
            db.add(user)
            db.flush()

        token = create_access_token(
            subject=str(user.id),
            email=user.email,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            expires_minutes=settings.jwt_expiration_minutes,
        )

        return standardized_success(
            {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                },
            }
        )


@router.get("/me")
def me(request: Request, user=Depends(get_authenticated_user)):
    return standardized_success(
        {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
            },
            "session_hint": {
                "request_user_id": str(getattr(request.state, "user_id", "") or ""),
            },
        }
    )
