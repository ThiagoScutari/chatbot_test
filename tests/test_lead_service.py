from app.models.audit_log import AuditLog
from app.models.session import Session as SessionModel
from app.services.lead_service import capture, write_audit_log


def test_capture_creates_lead_with_audit(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591333330001"
    )
    db.add(s)
    db.flush()

    lead = capture(
        db, s,
        nome_cliente="TEST_Cliente",
        telefone="5591999990001",
        segmento="corporativo",
        produto="polo_piquet",
        quantidade=50,
        personalizacao="bordado",
        prazo_desejado="30 dias",
        observacao=None,
    )
    db.commit()
    assert lead.status == "novo"

    log = (
        db.query(AuditLog)
        .filter(
            AuditLog.action_type == "lead.captured",
            AuditLog.resource_id == lead.id,
        )
        .first()
    )
    assert log is not None
    assert log.resource_type == "lead"
    assert log.actor == "bot"


def test_capture_sync_fields_null(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591333330002"
    )
    db.add(s)
    db.flush()

    lead = capture(db, s, nome_cliente="TEST_X")
    db.commit()
    assert lead.synced_to_kommo_at is None
    assert lead.synced_to_rdstation_at is None
    assert lead.external_crm_id is None
    assert lead.sync_metadata == {}


def test_write_audit_log_standalone(db):
    import uuid as _uuid
    log = write_audit_log(
        db,
        action_type="session.created",
        resource_type="session",
        resource_id=_uuid.uuid4(),
        actor="bot",
        metadata={"foo": "bar"},
    )
    db.commit()
    assert log.id is not None
    assert log.meta == {"foo": "bar"}


def test_capture_minimal_args(db):
    s = SessionModel(
        channel_id="whatsapp_cloud", channel_user_id="5591333330003"
    )
    db.add(s)
    db.flush()

    lead = capture(db, s, nome_cliente="Only Name")
    db.commit()
    assert lead.nome_cliente == "Only Name"
    assert lead.status == "novo"
    assert lead.segmento is None
