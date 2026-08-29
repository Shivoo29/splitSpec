"""Event routes: create, paginated list, single get."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import money
from app.auth import get_current_user
from app.db import get_session
from app.models import Event, User
from app.timeutil import iso8601_utc, to_utc_naive

router = APIRouter(prefix="/events", tags=["events"])


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    starts_at: datetime
    capacity: int = Field(default=100, ge=1, le=100_000)
    price: Decimal = Field(ge=0)
    currency: str = "USD"

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in money.SUPPORTED:
            raise ValueError(f"unsupported currency {value!r}")
        return value


class EventOut(BaseModel):
    id: int
    title: str
    description: str | None
    starts_at: str
    capacity: int
    price: str
    currency: str
    created_by: int
    created_at: str


class EventListOut(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


def event_payload(event: Event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "starts_at": iso8601_utc(event.starts_at),
        "capacity": event.capacity,
        "price": money.render(event.price, event.currency),
        "currency": event.currency,
        "created_by": event.created_by,
        "created_at": iso8601_utc(event.created_at),
    }


@router.post("", status_code=201, response_model=EventOut)
def create_event(
    payload: EventCreate,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    event = Event(
        title=payload.title,
        description=payload.description,
        starts_at=to_utc_naive(payload.starts_at),
        capacity=payload.capacity,
        price=money.quantize(payload.price, payload.currency),
        currency=payload.currency,
        created_by=user.id,
        created_at=request.app.state.clock.utcnow(),
    )
    session.add(event)
    session.commit()
    request.app.state.cache.invalidate()
    return event_payload(event)


@router.get("", response_model=EventListOut)
def list_events(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    key = f"events:{limit}:{offset}"
    cached = request.app.state.cache.get(key)
    if cached is not None:
        return cached
    total = session.scalar(select(func.count()).select_from(Event)) or 0
    rows = session.scalars(
        select(Event).order_by(Event.starts_at.asc(), Event.id.asc()).limit(limit).offset(offset)
    ).all()
    payload = {
        "items": [event_payload(event) for event in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
    request.app.state.cache.set(key, payload)
    return payload


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    request: Request,
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    key = f"event:{event_id}"
    cached = request.app.state.cache.get(key)
    if cached is not None:
        return cached
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    payload = event_payload(event)
    request.app.state.cache.set(key, payload)
    return payload