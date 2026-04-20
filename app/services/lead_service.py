"""LeadService — captura de orçamentos com audit log obrigatório.

`write_audit_log` DEVE ser chamado antes de `db.commit()` em qualquer
rota ou service que mute dados de negócio (ADR interno do Camisart AI).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.lead import Lead
from app.models.session import Session as SessionModel


def write_audit_log(
    db: Session,
    action_type: str,
    resource_type: str,
    resource_id: uuid.UUID,
    actor: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Registra evento de auditoria. Deve ser chamado ANTES de db.commit()."""
    log = AuditLog(
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor=actor,
        meta=metadata,
    )
    db.add(log)
    db.flush()
    return log


def capture(
    db: Session,
    session: SessionModel,
    nome_cliente: str,
    telefone: str | None = None,
    segmento: str | None = None,
    produto: str | None = None,
    quantidade: int | None = None,
    personalizacao: str | None = None,
    prazo_desejado: str | None = None,
    observacao: str | None = None,
) -> Lead:
    """Cria um Lead com status='novo' e grava audit_log 'lead.captured'."""
    lead = Lead(
        session_id=session.id,
        nome_cliente=nome_cliente,
        telefone=telefone,
        segmento=segmento,
        produto=produto,
        quantidade=quantidade,
        personalizacao=personalizacao,
        prazo_desejado=prazo_desejado,
        observacao=observacao,
        status="novo",
    )
    db.add(lead)
    db.flush()

    write_audit_log(
        db,
        action_type="lead.captured",
        resource_type="lead",
        resource_id=lead.id,
        actor="bot",
        metadata={
            "session_id": str(session.id),
            "segmento": segmento,
            "produto": produto,
            "quantidade": quantidade,
        },
    )
    return lead
