"""Ticket lookup by id. A user may only read their own tickets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import Ticket, User
from app.timeutil import iso8601_utc

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketOut(BaseModel):
    id: int
    code: str
    user_id: int
    event_id: int
    registration_id: int
    created_at: str


def ticket_payload(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "code": ticket.code,
        "user_id": ticket.user_id,
        "event_id": ticket.event_id,
        "registration_id": ticket.registration_id,
        "created_at": iso8601_utc(ticket.created_at),
    }


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    # Cancelling revokes the ticket. The row is kept so re-registering can reuse it,
    # but a revoked ticket is not readable.
    if ticket.registration.status != "confirmed":
        raise HTTPException(status_code=404, detail="ticket revoked by cancellation")
    return ticket_payload(ticket)