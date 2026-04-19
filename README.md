# Chatbot Baseado em Regras

Chatbot simples baseado em máquina de estados para consulta de pedidos e envio de catálogo de produtos.

## Etapas

| Etapa | Interface | Como executar |
|---|---|---|
| 1 | Terminal | `python etapa1_terminal/main.py` |
| 2 | Web (Flask) | `python etapa2_web/app.py` → http://127.0.0.1:5000 |
| 3 | Telegram | `set TELEGRAM_BOT_TOKEN=xxx && python etapa3_telegram/bot.py` |

## Pré-requisitos

```bash
pip install -r requirements.txt
```

## Testes

```bash
pytest -v
```

## Documentação

- [Guia de construção](docs/guia.md)
- [Design spec](docs/superpowers/specs/2026-04-19-chatbot-regras-design.md)
