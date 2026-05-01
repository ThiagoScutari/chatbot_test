"""
generate_nps_mock.py
--------------------
Gera 20 interações simuladas de NPS para demonstração do dashboard.
Persiste em data/nps_results.json (dashboard) e na tabela nps_responses (PostgreSQL).

Uso:
    python scripts/generate_nps_mock.py

Pré-requisito: migration aplicada → python app/migrations/migrate_sprint_nps.py
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

# Reconfigure stdout for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sqlalchemy import text
from app.database import engine

# ── Data ──────────────────────────────────────────────────────────────────────

PERFIS = [
    {
        "tipo": "promotor_entusiasmado",
        "quantidade": 6,
        "notas_range": {
            "logistica":              (8, 10),
            "produto_qualidade":      (9, 10),
            "produto_expectativa":    (8, 10),
            "atendimento":            (9, 10),
            "indicacao":              (9, 10),
        },
        "comentarios": [
            "Produto chegou antes do prazo, excelente qualidade!",
            "Atendimento incrível, vou indicar para minha empresa.",
            "Jaleco ficou perfeito, todo mundo da clínica adorou.",
            "Bordado caprichado, superou as expectativas.",
            "Super satisfeita, entrega rápida e produto igual ao da foto.",
            "",
        ],
    },
    {
        "tipo": "promotor_fiel",
        "quantidade": 5,
        "notas_range": {
            "logistica":              (7, 9),
            "produto_qualidade":      (8, 10),
            "produto_expectativa":    (8, 10),
            "atendimento":            (8, 10),
            "indicacao":              (9, 10),
        },
        "comentarios": [
            "Produto muito bom, entrega um pouco demorada mas compensou.",
            "Qualidade do tecido surpreendeu positivamente!",
            "Bom atendimento e produto de qualidade.",
            "",
            "",
        ],
    },
    {
        "tipo": "neutro_satisfeito",
        "quantidade": 4,
        "notas_range": {
            "logistica":              (6, 8),
            "produto_qualidade":      (7, 8),
            "produto_expectativa":    (6, 8),
            "atendimento":            (7, 9),
            "indicacao":              (7, 8),
        },
        "comentarios": [
            "No geral foi ok. A entrega atrasou um dia.",
            "Produto bom, mas esperava mais variedade de cores.",
            "Atendimento poderia ser mais ágil.",
            "",
        ],
    },
    {
        "tipo": "detrator_logistica",
        "quantidade": 2,
        "notas_range": {
            "logistica":              (2, 5),
            "produto_qualidade":      (7, 9),
            "produto_expectativa":    (6, 8),
            "atendimento":            (5, 7),
            "indicacao":              (3, 6),
        },
        "comentarios": [
            "Pedido atrasou 5 dias, precisava para evento corporativo.",
            "Entrega muito demorada. O produto em si é bom.",
        ],
    },
    {
        "tipo": "detrator_atendimento",
        "quantidade": 2,
        "notas_range": {
            "logistica":              (6, 8),
            "produto_qualidade":      (6, 8),
            "produto_expectativa":    (5, 7),
            "atendimento":            (2, 5),
            "indicacao":              (3, 6),
        },
        "comentarios": [
            "Demorei muito para ser atendido, fiquei sem resposta por 3 dias.",
            "Atendimento deixou muito a desejar. Produto razoável.",
        ],
    },
    {
        "tipo": "detrator_geral",
        "quantidade": 1,
        "notas_range": {
            "logistica":              (1, 4),
            "produto_qualidade":      (2, 5),
            "produto_expectativa":    (1, 4),
            "atendimento":            (2, 5),
            "indicacao":              (0, 4),
        },
        "comentarios": [
            "Produto veio com defeito no bordado e a entrega atrasou muito.",
        ],
    },
]

NOMES = [
    "Raimunda", "João Batista", "Maria das Graças", "Carlos Alberto",
    "Benedita", "Francisco", "Natália", "Sebastião", "Ana Paula",
    "Marcos", "Lúcia", "José Eduardo", "Sandra", "Antônio",
    "Cláudia", "Wilson", "Rosa", "Manoel", "Priscila", "Aldenir",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def classificar_nps(nota: int) -> str:
    if nota >= 9: return "promotor"
    if nota >= 7: return "neutro"
    return "detrator"

def gerar_timestamp(dias_atras_max: int = 30) -> datetime:
    dias   = random.randint(0, dias_atras_max)
    hora   = random.randint(8, 17)
    minuto = random.randint(0, 59)
    return (datetime.now() - timedelta(days=dias)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0
    )

# ── Generation ────────────────────────────────────────────────────────────────

def gerar_interacoes() -> list[dict]:
    random.seed(42)
    interacoes = []
    nomes_pool = NOMES.copy()
    random.shuffle(nomes_pool)
    idx = 0

    for perfil in PERFIS:
        for _ in range(perfil["quantidade"]):
            nome = nomes_pool[idx % len(nomes_pool)]
            idx += 1

            respostas = {}
            for cat, (lo, hi) in perfil["notas_range"].items():
                nota = random.randint(lo, hi)
                respostas[cat] = {"nota": nota, "classificacao": classificar_nps(nota)}

            comentario     = random.choice(perfil["comentarios"])
            notas          = [v["nota"] for v in respostas.values()]
            media_geral    = round(sum(notas) / len(notas), 1)
            nota_indicacao = respostas["indicacao"]["nota"]
            ts             = gerar_timestamp()

            interacoes.append({
                "user_id":           10000000 + idx,
                "nome":              nome,
                "perfil":            perfil["tipo"],
                "inicio":            ts.isoformat(),
                "fim":               ts.isoformat(),
                "respostas":         respostas,
                "comentario":        comentario,
                "media_geral":       media_geral,
                "nps_classificacao": classificar_nps(nota_indicacao),
            })

    interacoes.sort(key=lambda x: x["inicio"])
    return interacoes

# ── Persistence ───────────────────────────────────────────────────────────────

def salvar_json(interacoes: list[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    with open("data/nps_results.json", "w", encoding="utf-8") as f:
        json.dump(interacoes, f, ensure_ascii=False, indent=2)

def salvar_postgres(interacoes: list[dict]) -> int:
    """Insert all mock records into nps_responses. Returns count inserted."""
    inserted = 0
    with engine.connect() as conn:
        # Clear previous mock data to stay idempotent on re-runs
        conn.execute(text(
            "DELETE FROM nps_responses WHERE telegram_user_id BETWEEN 10000001 AND 10000099"
        ))
        for r in interacoes:
            res = r["respostas"]
            conn.execute(text("""
                INSERT INTO nps_responses (
                    telegram_user_id, nome,
                    nota_logistica, nota_produto_qualidade, nota_produto_expectativa,
                    nota_atendimento, nota_indicacao,
                    comentario, media_geral, nps_classificacao, raw_data, created_at
                ) VALUES (
                    :uid, :nome,
                    :log, :pq, :pe, :at, :ind,
                    :comentario, :media, :class, CAST(:raw AS jsonb), CAST(:ts AS timestamptz)
                )
            """), {
                "uid":        r["user_id"],
                "nome":       r["nome"],
                "log":        res["logistica"]["nota"],
                "pq":         res["produto_qualidade"]["nota"],
                "pe":         res["produto_expectativa"]["nota"],
                "at":         res["atendimento"]["nota"],
                "ind":        res["indicacao"]["nota"],
                "comentario": r["comentario"] or None,
                "media":      r["media_geral"],
                "class":      r["nps_classificacao"],
                "raw":        json.dumps(r, ensure_ascii=False),
                "ts":         r["inicio"],
            })
            inserted += 1
        conn.commit()
    return inserted

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\nGerando 20 interações NPS mock...\n")
    interacoes = gerar_interacoes()

    # 1. JSON (para dashboard)
    salvar_json(interacoes)
    print("  ✅ JSON salvo → data/nps_results.json")

    # 2. PostgreSQL
    try:
        n = salvar_postgres(interacoes)
        print(f"  ✅ PostgreSQL → {n} registros inseridos em nps_responses")
    except Exception as e:
        print(f"  ⚠️  PostgreSQL falhou ({e}) — apenas JSON foi salvo")

    # Summary
    promotores = sum(1 for i in interacoes if i["nps_classificacao"] == "promotor")
    neutros    = sum(1 for i in interacoes if i["nps_classificacao"] == "neutro")
    detratores = sum(1 for i in interacoes if i["nps_classificacao"] == "detrator")
    nps        = round((promotores - detratores) / len(interacoes) * 100)

    print(f"\n  Promotores: {promotores}  ({promotores * 5}%)")
    print(f"  Neutros:    {neutros}  ({neutros * 5}%)")
    print(f"  Detratores: {detratores}  ({detratores * 5}%)")
    print(f"  NPS Score:  {nps:+d}")
    print(f"\n  Dashboard → docs/evaluation/reports/nps_dashboard.html\n")

if __name__ == "__main__":
    main()
