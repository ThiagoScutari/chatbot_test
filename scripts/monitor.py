"""
Monitor de conversas em tempo real — Camisart AI.

Mostra conversas ativas de forma verbosa para acompanhamento
durante testes com clientes reais.

Uso:
    python scripts/monitor.py                    # conversas das últimas 2h
    python scripts/monitor.py --watch            # auto-refresh 5s
    python scripts/monitor.py --watch 10         # auto-refresh 10s
    python scripts/monitor.py --user 8510589598  # usuário específico
    python scripts/monitor.py --all              # tudo de hoje
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# UTF-8 for emojis on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings


def get_db():
    """Connect to PRODUCTION database (same one the bot uses)."""
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


def fetch_sessions(db, hours=2, user_filter=None, all_today=False):
    """Fetch active sessions within time window."""
    if user_filter:
        query = text("""
            SELECT id, channel_user_id, nome_cliente, current_state,
                   session_data, last_interaction_at, created_at
            FROM sessions
            WHERE channel_user_id = :user_id
              AND deleted_at IS NULL
            ORDER BY last_interaction_at DESC
            LIMIT 1
        """)
        rows = db.execute(query, {"user_id": user_filter}).fetchall()
    elif all_today:
        query = text("""
            SELECT id, channel_user_id, nome_cliente, current_state,
                   session_data, last_interaction_at, created_at
            FROM sessions
            WHERE last_interaction_at >= CURRENT_DATE
              AND deleted_at IS NULL
              AND channel_user_id NOT LIKE 'AUTOTEST_%'
              AND channel_user_id NOT LIKE 'flowtest_%'
              AND channel_user_id NOT LIKE 'TEST_%'
            ORDER BY last_interaction_at DESC
        """)
        rows = db.execute(query).fetchall()
    else:
        query = text("""
            SELECT id, channel_user_id, nome_cliente, current_state,
                   session_data, last_interaction_at, created_at
            FROM sessions
            WHERE last_interaction_at >= NOW() - make_interval(hours => :hours)
              AND deleted_at IS NULL
              AND channel_user_id NOT LIKE 'AUTOTEST_%%'
              AND channel_user_id NOT LIKE 'flowtest_%%'
              AND channel_user_id NOT LIKE 'TEST_%%'
            ORDER BY last_interaction_at DESC
        """)
        rows = db.execute(query, {"hours": hours}).fetchall()
    return rows


def fetch_messages(db, session_id):
    """Fetch all messages for a session, ordered chronologically."""
    query = text("""
        SELECT direction, content, matched_intent_id, created_at
        FROM messages
        WHERE session_id = :sid
        ORDER BY created_at ASC
    """)
    return db.execute(query, {"sid": str(session_id)}).fetchall()


def fetch_leads(db, session_id):
    """Fetch leads for a session."""
    query = text("""
        SELECT nome_cliente, segmento, produto, quantidade,
               personalizacao, prazo_desejado, status, created_at
        FROM leads
        WHERE session_id = :sid
        ORDER BY created_at DESC
    """)
    return db.execute(query, {"sid": str(session_id)}).fetchall()


def render_session(db, session_row):
    """Render one session block."""
    sid = session_row.id
    user_id = session_row.channel_user_id
    nome = session_row.nome_cliente or "(sem nome)"
    state = session_row.current_state
    data = session_row.session_data or {}
    last_at = session_row.last_interaction_at

    last_time = ""
    if last_at:
        if hasattr(last_at, "strftime"):
            last_time = last_at.strftime("%H:%M")
        else:
            last_time = str(last_at)

    header = f"── {nome} ({user_id}) "
    header += "─" * max(0, 64 - len(header))
    print(header)
    print(f"   Estado: {state} | Última msg: {last_time}")
    print()

    messages = fetch_messages(db, sid)
    if not messages:
        print("   (sem mensagens)")
    else:
        for msg in messages:
            direction = msg.direction
            content = msg.content or ""
            ts = msg.created_at
            time_str = ts.strftime("%H:%M") if hasattr(ts, "strftime") else ""

            icon = "👤" if direction == "in" else "🤖"

            lines = content.split("\n")
            first_line = lines[0][:120]
            if len(lines) > 1 or len(lines[0]) > 120:
                first_line += "..."

            print(f"   [{time_str}] {icon} {first_line}")

    print()

    funil_parts = []
    for campo in ["nome", "segmento", "produto", "quantidade", "personalizacao", "prazo"]:
        valor = data.get(campo)
        if valor:
            funil_parts.append(f"{campo}={valor}")

    if funil_parts:
        print(f"   📋 Funil: {' | '.join(funil_parts)}")
    else:
        print("   📋 Funil: (dados pendentes)")

    leads = fetch_leads(db, sid)
    if leads:
        for lead in leads:
            print(f"   ✅ Lead capturado (status: {lead.status})")

    print()


def render_all(db, hours=2, user_filter=None, all_today=False):
    """Render the full monitor view."""
    sessions = fetch_sessions(db, hours=hours, user_filter=user_filter, all_today=all_today)

    now = datetime.now()
    now_str = now.strftime("%d/%m/%Y %H:%M:%S")

    print("=" * 64)
    print("MONITOR DE CONVERSAS — Camisart AI")
    print(f"Atualizado: {now_str} | Sessões ativas: {len(sessions)}")
    print("=" * 64)
    print()

    if not sessions:
        window = "hoje" if all_today else f"últimas {hours}h"
        if user_filter:
            print(f"   Nenhuma sessão encontrada para {user_filter}")
        else:
            print(f"   Nenhuma conversa ativa nas {window}")
        print()
    else:
        for session_row in sessions:
            render_session(db, session_row)

    print("=" * 64)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor de conversas em tempo real — Camisart AI"
    )
    parser.add_argument(
        "--watch", nargs="?", const=5, type=int, metavar="SECONDS",
        help="Auto-refresh a cada N segundos (default: 5)",
    )
    parser.add_argument(
        "--user", type=str, default=None,
        help="Filtrar por channel_user_id específico",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Mostrar todas as conversas de hoje (não só últimas 2h)",
    )
    parser.add_argument(
        "--hours", type=int, default=2,
        help="Janela de tempo em horas (default: 2)",
    )
    args = parser.parse_args()

    db = get_db()

    try:
        if args.watch:
            interval = args.watch
            print(f"Modo watch ativo — refresh a cada {interval}s (Ctrl+C para sair)")
            time.sleep(1)
            while True:
                clear_screen()
                try:
                    render_all(db, hours=args.hours, user_filter=args.user, all_today=args.all)
                    print(f"\n🔄 Próxima atualização em {interval}s... (Ctrl+C para sair)")
                except Exception as exc:
                    print(f"\n❌ Erro: {exc}")
                time.sleep(interval)
        else:
            render_all(db, hours=args.hours, user_filter=args.user, all_today=args.all)
    except KeyboardInterrupt:
        print("\n\nMonitor encerrado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
