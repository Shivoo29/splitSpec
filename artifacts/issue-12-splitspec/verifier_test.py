
import pytest
from app.models import Event
from datetime import datetime

# The app fixture handles the database setup and seeding.
# I will add more events to the app's database.

@pytest.mark.asyncio
async def test_event_list_total_count_invariant(app, client):
    # Setup: Create additional events in the database to reach 6 total.
    # The `app` fixture already seeds some events, we need to be careful.
    # Let's count them first.
    with app.state.sessionmaker() as session:
        initial_count = session.query(Event).count()
        # Add events to make it 6 total.
        for i in range(6 - initial_count):
            e = Event(
                title=f"New Event {i}",
                starts_at=datetime(2026, 2, 1),
                capacity=100,
                price=10.0,
                currency="USD",
                created_by=1,
                created_at=datetime(2026, 1, 1),
            )
            session.add(e)
        session.commit()
        # Invalidate cache if necessary, though it might be easier just to make sure
        # we don't hit cache for new data if the test makes unique queries
        app.state.cache.invalidate()

    # Request with limit=2, offset=0
    # Expected: total=6, items length=2
    response = await client.get("/events?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    
    # This assertion is expected to fail on the buggy code
    assert data["total"] == 6, f"Expected total=6, but got {data['total']}"
    assert len(data["items"]) == 2

    # Request with limit=1, offset=2
    # Expected: total=6, items length=1
    response = await client.get("/events?limit=1&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 6, f"Expected total=6, but got {data['total']}"
    assert len(data["items"]) == 1
