"""
DEPRECATED — Sprint 09 (ADR-003)

Este script indexava o catálogo no pgvector para busca semântica (RAG).
Foi substituído pelo ContextEngine que injeta o catálogo completo no contexto
do LLM — mais simples e mais preciso para catálogos pequenos.

Para reabilitar: ver ADR-002 e ADR-003 em docs/decisions/ADRs.md.
Condição: catálogo > 200 produtos (~50.000 tokens).
"""
import sys

print("DEPRECATED: index_knowledge.py não é mais necessário.")
print("Ver ADR-003: app/engines/context_engine.py")
sys.exit(0)
