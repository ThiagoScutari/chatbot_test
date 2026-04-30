# Camisart AI — Chatbot de Televendas

Chatbot inteligente de pré-vendas para a **Camisart Belém** (uniformes profissionais).
Atende clientes via WhatsApp e Telegram, responde sobre produtos, preços, prazos
e coleta orçamentos para que o consultor humano feche a venda.

**Motor:** Claude Haiku (LLM-first) com fallback regex offline.

---

## Pré-requisitos

- Python 3.12+
- PostgreSQL 15+ (via Docker)
- Conta na Anthropic (API key do Claude)
- Bot do Telegram (token do BotFather)

### Instalar dependências

```bash
pip install -r requirements.txt
```

### Configurar variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

Variáveis obrigatórias para rodar o bot:

| Variável | Descrição |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:dev@localhost:5435/camisart_db` |
| `ANTHROPIC_API_KEY` | Chave da API Anthropic (Claude Haiku) |
| `TELEGRAM_BOT_TOKEN` | Token do BotFather |

### Banco de dados

Iniciar o container PostgreSQL:

```bash
docker start camisart-pg
```

O bot cria as tabelas automaticamente na primeira execução.

---

## Rodar o Bot (Telegram)

### 1. Iniciar o bot

```powershell
cd C:\workspace\chatbot
python scripts/telegram_polling.py
```

O terminal mostra logs de cada mensagem processada. Mantenha aberto.

### 2. Testar no Telegram

1. Abra o Telegram e procure seu bot
2. Envie `/start`
3. Converse normalmente

### 3. Monitorar conversas (segundo terminal)

Abra **outro terminal** e rode:

```powershell
cd C:\workspace\chatbot

# Ver todas as conversas das últimas 2 horas
python scripts/monitor.py

# Modo watch — atualiza a cada 5 segundos
python scripts/monitor.py --watch

# Atualizar a cada 10 segundos
python scripts/monitor.py --watch 10

# Ver conversa de um usuário específico
python scripts/monitor.py --user 8510589598

# Ver todas as conversas de hoje
python scripts/monitor.py --all
```

### 4. Inspecionar sessão específica

```powershell
# Por user_id do Telegram
python scripts/inspect_session.py 8510589598

# Última sessão ativa
python scripts/inspect_session.py --last

# Listar leads capturados
python scripts/inspect_session.py --leads
```

### 5. Parar o bot

`Ctrl+C` no terminal do polling.

---

## Testes Automatizados

### Banco de teste

Os testes usam `camisart_test_db` (nunca o banco de produção).
O container precisa estar rodando:

```bash
docker start camisart-pg
```

### Rodar todos os testes

```powershell
pytest tests/ -v
```

### Rodar testes específicos

```powershell
# Por arquivo
pytest tests/test_haiku_engine.py -v
pytest tests/test_conversation_flows.py -v
pytest tests/test_response_validator.py -v

# Por nome
pytest tests/ -k "test_C12" -v

# Com cobertura
pytest tests/ -v --cov=app --cov-report=term-missing
```

### Lint

```powershell
ruff check app/
```

---

## Testes com IA (Autotest)

Testa o bot com frases reais contra o pipeline direto (sem Telegram).

```powershell
# Todas as suites (FAQ, LLM, Context, Orçamento, Edge cases)
python scripts/autotest.py

# Suite específica
python scripts/autotest.py --suite faq
python scripts/autotest.py --suite orcamento
python scripts/autotest.py --suite context

# Modo offline (apenas regex, sem chamar API)
python scripts/autotest.py --mock-llm

# Gerar relatório HTML
python scripts/autotest.py --export

# Relatório standalone (funciona sem internet)
python scripts/autotest.py --export --standalone
```

Relatório gerado em: `docs/evaluation/reports/YYYY-MM-DD_autotest.html`

---

## Teste de Fluxo com Personas IA (Flowtest)

5 personas simuladas por Claude Haiku testam conversas completas multi-turn.

```powershell
# Configurar banco de teste
$env:DATABASE_URL = "postgresql://postgres:test@localhost:5435/camisart_test_db"

# Rodar 25 interações (5 por persona)
python -m scripts.flowtest --rounds 25 --export --seed 42

# Rodar 5 interações (smoke test rápido)
python -m scripts.flowtest --rounds 5 --export --seed 42

# Filtrar por persona
python -m scripts.flowtest --persona jessica --export

# Filtrar por fluxo
python -m scripts.flowtest --flow compra --export
```

Relatório gerado em: `docs/evaluation/reports/YYYY-MM-DD_flowtest.html`

**Importante:** Após rodar o flowtest, limpe a variável de ambiente para
não contaminar o bot de produção:

```powershell
Remove-Item Env:DATABASE_URL
```

---

## Avaliação e Dashboard

### Avaliar contra dataset rotulado (200 amostras)

```powershell
# Avaliação completa (Camadas 1+2+3)
python scripts/evaluate.py --export

# Apenas Camada 1 (mais rápido, sem API)
python scripts/evaluate.py --no-llm --export

# Filtrar por camada
python scripts/evaluate.py --layer faq --export
python scripts/evaluate.py --layer llm --export

# Filtrar por dificuldade
python scripts/evaluate.py --difficulty hard --export
```

### Gerar dashboard visual

```powershell
# Dashboard com Chart.js (precisa de internet)
python scripts/dashboard.py

# Dashboard standalone (funciona offline)
python scripts/dashboard.py --standalone
```

Dashboards gerados em: `docs/evaluation/reports/YYYY-MM-DD_dashboard.html`

---

## Consultar o Banco de Dados

### Queries úteis via Docker

```powershell
# Listar sessões ativas
docker exec -it camisart-pg psql -U postgres -d camisart_db -c "
SELECT nome_cliente, channel_user_id, current_state, last_interaction_at
FROM sessions WHERE deleted_at IS NULL
ORDER BY last_interaction_at DESC;
"

# Ver mensagens de um usuário
docker exec -it camisart-pg psql -U postgres -d camisart_db -c "
SELECT direction, content, created_at
FROM messages m JOIN sessions s ON m.session_id = s.id
WHERE s.channel_user_id = '8510589598'
ORDER BY m.created_at;
"

# Ver dados do funil
docker exec -it camisart-pg psql -U postgres -d camisart_db -c "
SELECT nome_cliente,
  session_data->>'nome' as nome,
  session_data->>'segmento' as segmento,
  session_data->>'produto' as produto,
  session_data->>'quantidade' as qtd,
  session_data->>'personalizacao' as personalizacao
FROM sessions WHERE deleted_at IS NULL;
"

# Ver leads capturados
docker exec -it camisart-pg psql -U postgres -d camisart_db -c "
SELECT nome_cliente, segmento, produto, quantidade, status, created_at
FROM leads ORDER BY created_at DESC LIMIT 10;
"
```

### Containers Docker

| Container | Porta | Uso |
|---|---|---|
| `camisart-pg` | 5435 | **Produção** — bot escreve aqui |

---

## Estrutura do Projeto

```
chatbot/
├── app/
│   ├── adapters/          # WhatsApp Cloud + Telegram
│   ├── api/               # Health + Admin endpoints
│   ├── engines/           # HaikuEngine, FAQEngine, ResponseValidator
│   ├── knowledge/         # Prompts, catálogo, FAQ, knowledge base
│   ├── models/            # SQLAlchemy (Session, Message, Lead)
│   ├── pipeline/          # MessagePipeline (LLM-first + regex fallback)
│   └── services/          # Session, Lead, Message, Audio
├── scripts/
│   ├── telegram_polling.py   # Rodar o bot localmente
│   ├── monitor.py            # Monitor de conversas em tempo real
│   ├── autotest.py           # Testes automáticos com IA
│   ├── evaluate.py           # Avaliação contra dataset
│   ├── dashboard.py          # Dashboard visual
│   ├── inspect_session.py    # Inspecionar sessão no banco
│   └── flowtest/             # Testes multi-turn com personas IA
├── tests/                    # 427 testes automatizados
├── docs/
│   ├── evaluation/           # Dataset + relatórios
│   ├── decisions/            # ADRs (decisões arquiteturais)
│   └── sprint_*/             # PRDs por sprint
└── test/                     # Protótipo antigo (terminal/web/telegram)
```

---

## Apêndice — Protótipo (legado)

Esta seção descreve o **protótipo de aprendizado** que vive em `test/` —
um chatbot baseado em máquina de estados para consulta de pedidos e envio
de catálogo de produtos (dados fictícios de móveis, **não** Camisart).
É runnable e serve apenas como demo histórica.

> Atenção: apesar do nome `test/`, esta pasta **não** é o diretório de testes.
> Os testes unitários reais ficam em `test/tests/` e em `tests/` na raiz.

### Etapas do protótipo

| Etapa | Interface | Como executar |
|---|---|---|
| 1 | Terminal | `python etapa1_terminal/main.py` |
| 2 | Web (Flask) | `python etapa2_web/app.py` → http://127.0.0.1:5000 |
| 3 | Telegram | `set TELEGRAM_BOT_TOKEN=xxx && python etapa3_telegram/bot.py` |

Todos os comandos acima devem ser rodados **de dentro de `test/`** —
os caminhos internos resolvem relativo a essa pasta:

```bash
cd test
python etapa1_terminal/main.py
```

### Testes do protótipo

```bash
cd test
python -m pytest tests/ -v
```

19 testes, configurados via `test/pytest.ini`. Usam `monkeypatch` para
trocar `core.database.DB_PATH` por uma SQLite temporária — nunca tocam
em `test/data/pedidos.db`.
