"""App factory sanity: importable, callable, and serving the documented routes."""
from __future__ import annotations

import app.main as main


def test_app_factory_is_importable_and_callable():
    assert callable(main.create_app)


def test_openapi_lists_all_endpoints(app):
    paths = app.openapi()["paths"]
    for expected in (
        "/events",
        "/events/{event_id}",
        "/registrations",
        "/registrations/{registration_id}",
        "/tickets/{ticket_id}",
        "/payments",
    ):
        assert expected in paths