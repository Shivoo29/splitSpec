"""Registration endpoints: register, cancel, list mine."""
from __future__ import annotations


async def test_register_201_issues_ticket(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 1}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["user_id"] == 4
    assert body["event_id"] == 1
    assert body["event"]["title"] == "PyConf 2026"
    assert body["ticket"]["code"] == "T0001-0004"
    assert body["ticket"]["user_id"] == 4


async def test_duplicate_registration_is_409(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["alice"]), json={"event_id": 1}
    )
    assert r.status_code == 409


async def test_register_unknown_event_is_404(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 999}
    )
    assert r.status_code == 404


async def test_register_full_event_is_400(client, auth_headers, tokens):
    for who in ("alice", "bob", "carol"):
        r = await client.post(
            "/registrations", headers=auth_headers(tokens[who]), json={"event_id": 2}
        )
        assert r.status_code == 201, who
    r = await client.post(
        "/registrations", headers=auth_headers(tokens["dana"]), json={"event_id": 2}
    )
    assert r.status_code == 400


async def test_register_requires_auth(client):
    r = await client.post("/registrations", json={"event_id": 1})
    assert r.status_code == 401


async def test_list_mine_only_own(client, auth_headers, tokens):
    r = await client.get("/registrations", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body] == [1, 3]
    assert all(x["user_id"] == 1 for x in body)

    bob = await client.get("/registrations", headers=auth_headers(tokens["bob"]))
    assert [x["id"] for x in bob.json()] == [2]
    assert bob.json()[0]["status"] == "cancelled"


async def test_cancel_own_registration_is_200(client, auth_headers, tokens):
    r = await client.delete("/registrations/3", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["user_id"] == 1


async def test_cancel_other_users_registration_is_403(client, auth_headers, tokens):
    r = await client.delete("/registrations/2", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 403


async def test_cancel_missing_registration_is_404(client, auth_headers, tokens):
    r = await client.delete("/registrations/999", headers=auth_headers(tokens["alice"]))
    assert r.status_code == 404


async def test_cancel_already_cancelled_is_400(client, auth_headers, tokens):
    r = await client.delete("/registrations/2", headers=auth_headers(tokens["bob"]))
    assert r.status_code == 400

async def test_cancel_then_register_again_is_201(client, auth_headers, tokens):
    """Cancelling must not lock the user out: the unique (user, event) row is reused."""
    alice = auth_headers(tokens["alice"])
    assert (await client.delete("/registrations/3", headers=alice)).status_code == 200

    again = await client.post("/registrations", json={"event_id": 3}, headers=alice)
    assert again.status_code == 201
    body = again.json()
    assert body["id"] == 3, "reactivates the existing row rather than inserting a second"
    assert body["status"] == "confirmed"
    assert body["ticket"] is not None

    mine = (await client.get("/registrations", headers=alice)).json()
    for_event_3 = [r for r in mine if r["event_id"] == 3]
    assert len(for_event_3) == 1


async def test_register_while_confirmed_is_still_409(client, auth_headers, tokens):
    r = await client.post(
        "/registrations", json={"event_id": 3}, headers=auth_headers(tokens["alice"])
    )
    assert r.status_code == 409


async def test_cancel_register_cancel_cycles(client, auth_headers, tokens):
    alice = auth_headers(tokens["alice"])
    for _ in range(3):
        assert (await client.delete("/registrations/3", headers=alice)).status_code == 200
        r = await client.post("/registrations", json={"event_id": 3}, headers=alice)
        assert r.status_code == 201
    assert (await client.delete("/registrations/3", headers=alice)).status_code == 200


async def test_cancelled_registration_ticket_is_revoked(client, auth_headers, tokens):
    alice = auth_headers(tokens["alice"])
    assert (await client.get("/tickets/3", headers=alice)).status_code == 200

    cancelled = await client.delete("/registrations/3", headers=alice)
    assert cancelled.json()["ticket"] is None
    assert (await client.get("/tickets/3", headers=alice)).status_code == 404

    await client.post("/registrations", json={"event_id": 3}, headers=alice)
    assert (await client.get("/tickets/3", headers=alice)).status_code == 200
