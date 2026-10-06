"""Account administration cannot impersonate confidential-content owners."""
import uuid

import pytest

from app.models.application import Application
from app.models.user import User
from app.services.access import initialize_access
from app.services.audit import log_action
from app.services.auth import create_access_token, hash_password


def auth(user):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': str(user.id)})}


@pytest.fixture
async def confidential_owner(db_session, default_jurisdiction):
    admin = User(email='accounts@example.test', full_name='Account administrator', role='admin', password_hash=hash_password('Original account pass'))
    owner = User(email='licensing@example.test', full_name='Licensing owner', role='manager', password_hash=hash_password('Original licensing pass'))
    db_session.add_all([admin, owner])
    await db_session.flush()
    application = Application(id=uuid.uuid4(), jurisdiction_id=default_jurisdiction.id,
        name='Secret acquisition licence', scope='licence', created_by=owner.id)
    db_session.add(application)
    await db_session.flush()
    await initialize_access(db_session, 'application', application.id, owner)
    await log_action(db_session, owner, 'create', 'application', str(application.id), new_value={'name': application.name})
    await db_session.commit()
    return admin, owner, application


@pytest.mark.parametrize('changes', [{'password': 'Replacement account pass'}, {'email': 'takeover@example.com'}])
async def test_account_admin_cannot_take_over_confidential_identity(client, confidential_owner, changes):
    admin, owner, _ = confidential_owner
    response = await client.put(f'/api/v1/users/{owner.id}', headers=auth(admin), json=changes)
    assert response.status_code == 403
    profile = await client.get(f'/api/v1/users/{owner.id}', headers=auth(admin))
    assert profile.json()['email'] == 'licensing@example.test'
    # Account administration remains available without content authority.
    deactivated = await client.put(f'/api/v1/users/{owner.id}', headers=auth(admin), json={'active': False})
    assert deactivated.status_code == 200
    assert deactivated.json()['active'] is False
    # Deactivation cannot be used to sidestep identity protection.
    response = await client.put(f'/api/v1/users/{owner.id}', headers=auth(admin), json=changes)
    assert response.status_code == 403


async def test_account_audit_does_not_reveal_confidential_work(client, confidential_owner):
    admin, owner, application = confidential_owner
    response = await client.get(f'/api/v1/users/{owner.id}/audit', headers=auth(admin))
    assert response.status_code == 200
    assert response.json() == {'items': [], 'total': 0}
