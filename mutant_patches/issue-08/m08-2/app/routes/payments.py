"""Payment routes: charge an event with an Idempotency-Key header."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import money
from app.auth import get_current_user
from app.db import get_session
from app.models import Event, Payment, User
from app.timeutil import iso8601_utc

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentIn(BaseModel):
    event_id: int
    currency: str | None = None


class PaymentOut(BaseModel):
    id: int
    user_id: int
    event_id: int
    amount: str
    currency: str
    status: str
    idempotency_key: str
    created_at: str


def payment_payload(payment: Payment) -> dict:
    return {
        "id": payment.id,
        "user_id": payment.user_id,
        "event_id": payment.event_id,
        "amount": money.render(payment.amount, payment.currency),
        "currency": payment.currency,
        "status": payment.status,
        "idempotency_key": payment.idempotency_key,
        "created_at": iso8601_utc(payment.created_at),
    }


@router.post("", response_model=PaymentOut)
def charge(
    payload: PaymentIn,
    response: Response,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),  # noqa: B008
    user: User = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
) -> dict:
    event = session.get(Event, payload.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    currency = (payload.currency or event.currency).strip().upper()
    if currency not in money.SUPPORTED:
        raise HTTPException(status_code=400, detail=f"unsupported currency {currency!r}")
    if currency != event.currency:
        raise HTTPException(status_code=400, detail="charge currency must match the event currency")

    # Obvious-path-only fix: checks for existing key BEFORE creating payment.
    # BUG: Only checks for keys owned by the SAME user, allowing cross-user
    # duplicate key usage to create a new payment.
    existing = session.scalar(
        select(Payment).where(
            Payment.idempotency_key == idempotency_key,
            Payment.user_id == user.id,
        )
    )
    if existing is not None:
        response.status_code = 200
        return payment_payload(existing)

    payment = Payment(
        user_id=user.id,
        event_id=event.id,
        amount=money.quantize(event.price, currency),
        currency=currency,
        idempotency_key=idempotency_key,
        status="succeeded",
        created_at=request.app.state.clock.utcnow(),
    )
    session.add(payment)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(Payment).where(
                Payment.idempotency_key == idempotency_key,
                Payment.user_id == user.id,
            )
        )
        if existing is not None:
            response.status_code = 200
            return payment_payload(existing)
        raise HTTPException(status_code=409, detail="idempotency key already in use") from None

    response.status_code = 201
    return payment_payload(payment)