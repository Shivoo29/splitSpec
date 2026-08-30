import pytest
from app.models import Registration
from sqlalchemy import select

@pytest.mark.asyncio
async def test_disappearing_registration_race(client, auth_headers, tokens, app):
    headers = auth_headers(tokens['bob'])
    
    # Register for event 2
    r1 = await client.post('/registrations', json={'event_id': 2}, headers=headers)
    assert r1.status_code == 201
    reg_id = r1.json()['id']
    
    # Immediately cancel, then register, then check.
    await client.delete(f'/registrations/{reg_id}', headers=headers)
    
    # Register again
    r2 = await client.post('/registrations', json={'event_id': 2}, headers=headers)
    assert r2.status_code == 201
    new_reg_id = r2.json()['id']
    
    # Check DB directly
    with app.state.sessionmaker() as db_session:
        db_reg = db_session.scalar(select(Registration).where(Registration.id == new_reg_id))
        assert db_reg is not None, 'Registration should exist in DB'
        assert db_reg.status == 'confirmed'
    
    # List through API
    mine = await client.get('/registrations', headers=headers)
    ids = [x['id'] for x in mine.json()]
    assert new_reg_id in ids, f'Registration {new_reg_id} not found in API response. Got: {ids}'