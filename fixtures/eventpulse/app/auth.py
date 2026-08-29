"""Header-token authentication. Deliberately simple and observable."""
from __future__ import annotations

from fastapi import Header, HTTPException, Request
from sqlalchemy import select

from app.models import User


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),  # noqa: B008
) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="expected 'Bearer <token>'")
    token = token.strip()
    sm = request.app.state.sessionmaker
    with sm() as session:
        user = session.scalar(select(User).where(User.token == token))
    if user is None:
        raise HTTPException(status_code=401, detail="unknown token")
    return user