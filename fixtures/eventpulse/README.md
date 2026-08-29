# EventPulse — fixture application

A small, real event-registration API used as the evaluation repository for SplitSpec.
This is the **correct, bug-free reference implementation**; seeded defects are introduced
by later modules, never here.

- FastAPI + SQLAlchemy 2.0 + SQLite (URL is swappable for PostgreSQL).
- `create_app(db_url)` is the app factory; the DB URL defaults to `EVENTPULSE_DB_URL`
  (`sqlite:///./eventpulse.db`).
- Deterministic: no randomness, an injectable clock, UTC instants stored as naive UTC and
  serialized as ISO-8601 with an explicit `+00:00` offset.
- Money is `Decimal` end to end and always returned as a string quantized to the currency's
  cash unit (`USD`/`EUR`/`GBP`/`CHF`/`CAD`: 2 places, `JPY`: 0 places). Never float.
- Auth: `Authorization: Bearer <token>` in the request header resolves to a user. Missing or
  unknown tokens are `401`; touching another user's records is `403`.

## Endpoints

| Method | Path                     | Auth       | Status codes |
|--------|--------------------------|------------|--------------|
| POST   | `/events`                | Bearer     | 201, 401, 422 |
| GET    | `/events?limit&offset`   | public     | 200 |
| GET    | `/events/{event_id}`     | public     | 200, 404 |
| POST   | `/registrations`         | Bearer     | 201, 400 (event full), 401, 404, 409 (duplicate), 422 |
| GET    | `/registrations`         | Bearer     | 200 (caller's own), 401 |
| DELETE | `/registrations/{id}`    | Bearer     | 200, 400 (already cancelled), 401, 403 (not owner), 404 |
| GET    | `/tickets/{ticket_id}`   | Bearer     | 200, 401, 403 (not owner), 404 (missing or revoked) |
| POST   | `/payments`              | Bearer     | 201, 200 (idempotent replay), 400 (currency), 401, 404, 409 (key already owned by another user), 422 (missing key) |

## Behavioral semantics

- **Registration uniqueness is enforced by a DB-level unique constraint on
  `(user_id, event_id)`** and surfaces as HTTP 409. A user registers for an event at most
  once; a registration is permanent (`cancelled` only flips its status). Registering also
  issues a ticket for the user/event pair.
- **Payments are idempotent via the `Idempotency-Key` header** (required; missing key is
  `422`). Replaying the same key returns the original payment with `200` — a retry never
  creates a second charge. The key must belong to the same user, otherwise `409`.
- Charge currency must match the event's currency (`400` otherwise); the amount is the
  event price, never client-supplied.
- **Cache:** event list/get reads go through an in-process cache that is explicitly
  invalidated on every write (event create, registration create/cancel), so reads always
  reflect the latest writes.
- Events are listed newest-first by `starts_at` (then id), which keeps every run
  deterministic.

## Running

```bash
# serve
EVENTPULSE_DB_URL=sqlite:///./eventpulse.db uvicorn app.main:create_app --factory --port 8000

# seed fixed data (users, events, registrations, tickets, payments)
EVENTPULSE_DB_URL=sqlite:///./eventpulse.db python -m seed

# tests
pytest -q
```

Seed credentials (`python -m seed`): tokens are `alice-token-0001`, `bob-token-0002`,
`carol-token-0003`, `dana-token-0004` for alice/bob/carol/dana, ids 1..4.
## Registration lifecycle

There is at most one registration row per `(user_id, event_id)` for the lifetime of that
pair, enforced by a database unique constraint.

- Registering while a **confirmed** registration exists returns **409**.
- Cancelling sets the row's status to `cancelled`; the row is kept.
- Registering again after cancelling **reactivates the same row** and returns **201** with
  the same registration id. It does not insert a second row.
- Cancelling **revokes the ticket**: the registration payload reports `ticket: null`, and
  `GET /tickets/{id}` returns **404** for it. Ownership is checked first, so another user
  reading that ticket still gets **403**. Re-registering makes the ticket readable again
  under its original id and code.
