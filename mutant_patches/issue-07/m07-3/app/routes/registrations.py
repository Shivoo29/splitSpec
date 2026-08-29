"""Registration routes: register, cancel, list the caller's own."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.db import get_session
from app.models import Event, Registration, Ticket, User
from app.routes.events import EventOut, event_payload
from app.routes.tickets import TicketOut, ticket_payload
from app.timeutil import iso8601_utc

router = APIRouter(prefix="/registrations", tags=["registrations"])


class RegisterIn(BaseModel):
    event_id: int


class RegistrationOut(BaseModel):
    id: int
    user_id: int
    event_id: int
    status: str
    created_at: str
    event: EventOut
    ticket: TicketOut | None


def _ticket_code(event_id: int, user_id: int) -> str:
    return f"T{event_id:04d}-{user_id:04d}"


def registration_payload(reg: Registration) -> dict:
    return {
        "id": reg.id,
        "user_id": reg.user_id,
        "event_id": reg.event_id,
        "status": reg.status,
        "created_at": iso8601_utc(reg.created_at),
        "event": event_payload(reg.event),
        "ticket": ticket_payload(reg.ticket) if _ticket_is_live(reg) else None,
    }


def _ticket_is_live(reg: Registration) -> bool:
    return reg.ticket is not None and reg.status == "confirmed"


@router.post("", status_code=201, response_model=RegistrationOut)
def register(
    payload: RegisterIn,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    event = session.get(Event, payload.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    # Sequential-only fix: uses with_for_update() but SQLite doesn't support
    # SELECT FOR UPDATE properly in all modes, so this fails under real concurrency.
    existing = session.scalar(
        select(Registration).where(
            Registration.user_id == user.id,
            Registration.event_id == event.id,
        ).with_for_update()
    )
    if existing is not None and existing.status == "confirmed":
        raise HTTPException(status_code=409, detail="already registered for this event")

    confirmed = session.scalar(
        select(func.count()).select_from(Registration).where(
            Registration.event_id == event.id, Registration.status == "confirmed"
        )
    ) or 0
    if confirmed >= event.capacity:
        raise HTTPException(status_code=400, detail="event is full")

    now = request.app.state.clock.utcnow()
    if existing is not None:
        reg = existing
        reg.status = "confirmed"
        reg.created_at = now
    else:
        reg = Registration(
            user_id=user.id,
            event_id=event.id,
            status="confirmed",
            created_at=now,
        )
        session.add(reg)
        session.flush()

    ticket = reg.ticket
    if ticket is None:
        ticket = Ticket(
            registration_id=reg.id,
            user_id=user.id,
            event_id=event.id,
            code=_ticket_code(event.id, user.id),
            created_at=now,
        )
        session.add(ticket)
    else:
        ticket.created_at = now
    session.commit()
    request.app.state.cache.invalidate()
    return {
        "id": reg.id,
        "user_id": reg.user_id,
        "event_id": reg.event_id,
        "status": reg.status,
        "created_at": iso8601_utc(reg.created_at),
        "event": event_payload(event),
        "ticket": ticket_payload(ticket),
    }


@router.get("", response_model=list[RegistrationOut])
def list_mine(
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> list[dict]:
    rows = session.scalars(
        select(Registration)
        .where(Registration.user_id == user.id)
        .order_by(Registration.created_at.asc(), Registration.id.asc())
        .options(selectinload(Registration.event), selectinload(Registration.ticket))
    ).all()
    return [registration_payload(reg) for reg in rows]


@router.delete("/{registration_id}", response_model=RegistrationOut)
def cancel(
    registration_id: int,
    request: Request,
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    reg = session.get(Registration, registration_id)
    if reg is None:
        raise HTTPException(status_code=404, detail="registration not found")
    if reg.user_id != user.id:
        raise HTTPException(status_code=403, detail="cannot cancel another user's registration")
    if reg.status == "cancelled":
        raise HTTPException(status_code=400, detail="registration already cancelled")
    reg.status = "cancelled"
    session.commit()
    request.app.state.cache.invalidate()
    return registration_payload(reg)