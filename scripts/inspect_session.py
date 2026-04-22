"""Inspeciona sessão, mensagens e leads de um usuário pelo channel_user_id.

Uso:
    python scripts/inspect_session.py 5591999990001
    python scripts/inspect_session.py --last   # última sessão criada
    python scripts/inspect_session.py --leads  # todos os leads novos
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.lead import Lead
from app.models.message import Message
from app.models.session import Session as SessionModel


def inspect_user(db: Session, channel_user_id: str):
    session = (
        db.query(SessionModel)
        .filter_by(channel_user_id=channel_user_id)
        .order_by(SessionModel.created_at.desc())
        .first()
    )

    if not session:
        print(f"[--] Nenhuma sessao encontrada para {channel_user_id}")
        return

    print(f"\n{'=' * 60}")
    print(f"SESSAO: {session.id}")
    print(f"  Canal: {session.channel_id}")
    print(f"  User ID: {session.channel_user_id}")
    print(f"  Nome: {session.nome_cliente}")
    print(f"  Estado atual: {session.current_state}")
    print(f"  Ultima interacao: {session.last_interaction_at}")
    print(f"  session_data: {session.session_data}")

    msgs = (
        db.query(Message)
        .filter_by(session_id=session.id)
        .order_by(Message.created_at)
        .all()
    )
    print(f"\nMENSAGENS ({len(msgs)}):")
    for m in msgs[-10:]:  # últimas 10
        arrow = "->" if m.direction == "in" else "<-"
        intent = f" [{m.matched_intent_id}]" if m.matched_intent_id else ""
        print(f"  {arrow} {m.content[:60]}{intent}")

    leads = db.query(Lead).filter_by(session_id=session.id).all()
    if leads:
        print(f"\nLEADS ({len(leads)}):")
        for l in leads:
            print(
                f"  - {l.nome_cliente} | {l.segmento} | {l.produto} "
                f"| {l.quantidade}x | {l.personalizacao} "
                f"| prazo: {l.prazo_desejado} | status: {l.status}"
            )

    print(f"{'=' * 60}\n")


def list_new_leads(db: Session):
    leads = (
        db.query(Lead)
        .filter_by(status="novo")
        .order_by(Lead.created_at.desc())
        .limit(10)
        .all()
    )
    print(f"\n{'=' * 60}")
    print(f"LEADS NOVOS (ultimos {len(leads)}):")
    for l in leads:
        print(
            f"  - [{l.created_at.strftime('%H:%M')}] {l.nome_cliente} "
            f"| {l.segmento} | {l.produto} | {l.quantidade}x"
        )
    print(f"{'=' * 60}\n")


def main():
    db = SessionLocal()
    try:
        args = sys.argv[1:]
        if not args:
            print("Uso: python scripts/inspect_session.py <channel_user_id>")
            print("     python scripts/inspect_session.py --last")
            print("     python scripts/inspect_session.py --leads")
            return
        if args[0] == "--leads":
            list_new_leads(db)
        elif args[0] == "--last":
            s = (
                db.query(SessionModel)
                .order_by(SessionModel.last_interaction_at.desc())
                .first()
            )
            if s:
                inspect_user(db, s.channel_user_id)
            else:
                print("[--] Nenhuma sessao encontrada.")
        else:
            inspect_user(db, args[0])
    finally:
        db.close()


if __name__ == "__main__":
    main()
