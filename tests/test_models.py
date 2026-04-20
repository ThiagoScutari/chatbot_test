import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.lead import Lead
from app.models.session import Session as SessionModel


def test_session_create(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591999990001"
    )
    db.add(s)
    db.flush()
    assert isinstance(s.id, uuid.UUID)
    assert s.current_state == "inicio"
    assert s.session_data == {}


def test_session_unique_constraint(db):
    s1 = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591999990002"
    )
    s2 = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591999990002"
    )
    db.add(s1)
    db.flush()
    db.add(s2)
    with pytest.raises(IntegrityError):
        db.flush()


def test_lead_defaults(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591999990003"
    )
    db.add(s)
    db.flush()
    lead = Lead(session_id=s.id, nome_cliente="TEST_Cliente")
    db.add(lead)
    db.flush()
    assert lead.status == "novo"
    assert lead.is_archived is False
    assert lead.sync_metadata == {}
    assert lead.synced_to_kommo_at is None
    assert lead.external_crm_id is None


def test_audit_log_immutable_no_updated_at(db):
    columns = [c.name for c in AuditLog.__table__.columns]
    assert "updated_at" not in columns
    assert "created_at" in columns
