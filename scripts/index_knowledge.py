"""
Indexa a base de conhecimento da Camisart no pgvector.

Uso:
    python scripts/index_knowledge.py              # indexa tudo
    python scripts/index_knowledge.py --clear      # limpa e re-indexa
    python scripts/index_knowledge.py --status     # mostra chunks indexados

Quando re-indexar:
    - Após atualizar camisart_knowledge_base.md
    - Após atualizar products.json com novos produtos
    - Após qualquer mudança de preço ou informação no catálogo
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import SessionLocal


def make_session():
    return SessionLocal()


async def main():
    parser = argparse.ArgumentParser(
        description="Indexa knowledge base no pgvector"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Limpa e re-indexa tudo"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Mostra estatísticas dos chunks indexados",
    )
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY nao configurada. Adicione ao .env")
        return

    import openai

    from app.engines.rag_engine import (
        RAGEngine,
        chunk_markdown,
        chunk_products_json,
    )

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    engine = RAGEngine(db_session_factory=make_session, openai_client=client)

    if args.status:
        count = await engine.count_chunks()
        print(f"\n{'=' * 50}")
        print(f"Chunks indexados: {count}")
        print(f"{'=' * 50}\n")
        return

    if args.clear:
        await engine.clear_source("knowledge_base")
        await engine.clear_source("products")
        print("Chunks anteriores removidos.")

    kb_path = settings.KNOWLEDGE_BASE_PATH
    if kb_path.exists():
        print(f"Indexando {kb_path.name}...")
        md_text = kb_path.read_text(encoding="utf-8")
        chunks = chunk_markdown(md_text, "knowledge_base")
        n = await engine.index_document("knowledge_base", chunks)
        print(f"   OK {n} chunks indexados de {kb_path.name}")
    else:
        print(f"{kb_path} nao encontrado - pulando")

    products_path = Path("app/knowledge/products.json")
    if products_path.exists():
        print(f"Indexando {products_path.name}...")
        products_data = json.loads(products_path.read_text(encoding="utf-8"))
        chunks = chunk_products_json(products_data, "products")
        n = await engine.index_document("products", chunks)
        print(f"   OK {n} chunks indexados de {products_path.name}")
    else:
        print(f"{products_path} nao encontrado - pulando")

    total = await engine.count_chunks()
    print(f"\n{'=' * 50}")
    print(f"Indexacao completa - {total} chunks no banco")
    print("Custo estimado: < R$ 0,01 (text-embedding-3-small)")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    asyncio.run(main())
