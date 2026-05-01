# PRD — Sprint NPS: Bot de Pesquisa e Dashboard

**Status:** Aprovado para implementação
**Branch:** `sprint/nps-01`
**Origem:** Feature — demonstração para cliente (reunião Matheus)
**Dependência:** `scripts/telegram_polling.py` (referência de padrão)
**Decisão arquitetural:** Docker + PostgreSQL estará rodando durante a demo.
Persistência primária em banco; JSON como secundário para o dashboard.

---

## Contexto

O projeto Camisart AI já possui um bot de vendas (`scripts/telegram_polling.py`)
com pipeline completo de LLM, FAQ e coleta de leads. Para a reunião com o cliente
Matheus, precisamos demonstrar também a **camada de NPS** — o que pode ser colhido
de informações ricas quando um cliente responde uma pesquisa de satisfação bem
estruturada.

Os três entregáveis devem poder ser demonstrados ao vivo: o arquiteto mostra o bot
de vendas rodando, depois inicia o bot de NPS, e por último abre o dashboard no
browser para explicar o valor dos dados coletados.

---

## Entregáveis do Sprint

| ID | Arquivo | Descrição | Esforço |
|---|---|---|---|
| NPS-00 | `app/migrations/migrate_sprint_nps.py` | Migration tabela `nps_responses` + índices | Pequeno |
| NPS-00 | `app/migrations/rollback_sprint_nps.py` | Rollback correspondente | Pequeno |
| NPS-02 | `scripts/generate_nps_mock.py` | Gerador de 20 interações simuladas — dual-write DB + JSON | Pequeno |
| NPS-01 | `scripts/telegram_nps.py` | Bot de NPS com 5 perguntas — dual-write DB + JSON | Médio |
| NPS-03 | `docs/evaluation/reports/nps_dashboard.html` | Dashboard didático e detalhado de NPS | Grande |

---

## NPS-00 — Migration `app/migrations/migrate_sprint_nps.py`

### Motivação
O bot e o gerador de mock precisam da tabela `nps_responses` no banco antes de
qualquer escrita. Esta migration deve ser executada uma única vez antes dos demais
itens do sprint.

### Schema da tabela

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | `UUID PK DEFAULT gen_random_uuid()` | Chave primária |
| `telegram_user_id` | `BIGINT NOT NULL` | chat_id do Telegram |
| `nome` | `TEXT NOT NULL` | Nome informado pelo respondente |
| `nota_logistica` | `INTEGER CHECK (0-10)` | Nota da pergunta 1 |
| `nota_produto_qualidade` | `INTEGER CHECK (0-10)` | Nota da pergunta 2 |
| `nota_produto_expectativa` | `INTEGER CHECK (0-10)` | Nota da pergunta 3 |
| `nota_atendimento` | `INTEGER CHECK (0-10)` | Nota da pergunta 4 |
| `nota_indicacao` | `INTEGER CHECK (0-10)` | Nota da pergunta 5 (NPS clássico) |
| `comentario` | `TEXT` | Resposta aberta (nullable) |
| `media_geral` | `NUMERIC(4,2)` | Média das 5 notas |
| `nps_classificacao` | `TEXT CHECK IN (promotor, neutro, detrator)` | Baseado em nota_indicacao |
| `raw_data` | `JSONB NOT NULL DEFAULT '{}'` | Registro completo — auditoria e dashboard |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Timestamp de gravação |

### Índices

```sql
CREATE INDEX idx_nps_classificacao ON nps_responses (nps_classificacao);
CREATE INDEX idx_nps_created_at    ON nps_responses (created_at DESC);
```

### Regras obrigatórias (padrão Camisart)

- Migration **idempotente** — `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`
- Rollback correspondente em `app/migrations/rollback_sprint_nps.py`
- Executar antes de qualquer outro item: `python app/migrations/migrate_sprint_nps.py`

---

## NPS-01 — `scripts/telegram_nps.py`

### Motivação
O bot de vendas já existe. Precisamos de um bot irmão que, ao invés de vender,
colete feedback estruturado via NPS. O arquiteto deve poder rodar os dois em
terminais separados durante a demonstração.

### As 5 Perguntas (linguagem natural, nota 0-10)

| # | Categoria | Texto da pergunta |
|---|---|---|
| 1 | Logística | "📦 *Logística* — De **0 a 10**, como você avalia a entrega do seu pedido? Chegou no prazo e em boas condições?" |
| 2 | Produto (qualidade) | "🧵 *Qualidade do Produto* — De **0 a 10**, como você avalia a qualidade do produto que recebeu? O acabamento e os materiais atenderam o que você esperava?" |
| 3 | Produto (expectativa) | "🎯 *Produto × Expectativa* — De **0 a 10**, o produto correspondeu ao que foi apresentado? Variedade, cores e opções estavam de acordo com a oferta?" |
| 4 | Atendimento | "🤝 *Atendimento* — De **0 a 10**, como você avalia o atendimento que recebeu? A equipe foi ágil, atenciosa e resolveu suas dúvidas?" |
| 5 | Indicação | "💬 *Indicação* — De **0 a 10**, qual a probabilidade de você recomendar nossa empresa para um amigo ou familiar?" |

### Fluxo da conversa

```
/start  →  Saudação personalizada (pede nome)
         ↓
     Usuário informa nome
         ↓
  Pergunta 1 (Logística) + teclado numérico 0-10
         ↓
  Pergunta 2 (Produto - Qualidade) + teclado
         ↓
  Pergunta 3 (Produto - Expectativa) + teclado
         ↓
  Pergunta 4 (Atendimento) + teclado
         ↓
  Pergunta 5 (Indicação / NPS clássico) + teclado
         ↓
  Pergunta aberta: "Tem algum comentário ou sugestão?" (pode pular)
         ↓
  Agradecimento + nota média calculada
         ↓
  Dual-write: PostgreSQL (primário) + data/nps_results.json (secundário)
```

### Estados da máquina de estados

```python
AGUARDA_NOME = 0
LOGISTICA = 1
PRODUTO_QUALIDADE = 2
PRODUTO_EXPECTATIVA = 3
ATENDIMENTO = 4
INDICACAO = 5
COMENTARIO = 6
```

### Classificação NPS (pela pergunta 5 — Indicação)

| Nota | Classificação |
|---|---|
| 0-6 | Detrator |
| 7-8 | Neutro |
| 9-10 | Promotor |

### Estrutura de dados salva em `data/nps_results.json`

```json
[
  {
    "user_id": 123456789,
    "nome": "Raimunda",
    "inicio": "2026-05-01T14:32:00",
    "fim": "2026-05-01T14:35:22",
    "respostas": {
      "logistica":            { "nota": 9, "classificacao": "promotor" },
      "produto_qualidade":    { "nota": 8, "classificacao": "neutro" },
      "produto_expectativa":  { "nota": 9, "classificacao": "promotor" },
      "atendimento":          { "nota": 10, "classificacao": "promotor" },
      "indicacao":            { "nota": 9, "classificacao": "promotor" }
    },
    "comentario": "Adorei o produto, chegou antes do prazo!",
    "media_geral": 9.0,
    "nps_classificacao": "promotor"
  }
]
```

### Persistência (dual-write)

**Primário — PostgreSQL (`nps_responses`)**
Cada resposta completa é inserida na tabela `nps_responses` com as 5 notas em
colunas dedicadas, `media_geral`, `nps_classificacao` e o registro completo em
`raw_data JSONB`. A gravação usa `engine.connect()` + `text()`, mesmo padrão das
migrations existentes.

**Secundário — `data/nps_results.json`**
Arquivo acumulativo. Sempre gravado mesmo que o PostgreSQL falhe, garantindo que
o dashboard funcione durante a demo. Estratégia: lê o arquivo existente, appenda
o novo registro, regrava.

**Ordem de gravação:**
```python
def salvar_resultado(registro):
    try:
        salvar_postgres(registro)   # primário — falha silenciosamente com log
    except Exception:
        logger.exception("Falha PostgreSQL — salvando apenas JSON")
    salvar_json(registro)           # secundário — sempre executado
```

### Implementação — padrões obrigatórios

- Usar raw `httpx.AsyncClient` (mesma abordagem de `telegram_polling.py`, **não** usar `python-telegram-bot`)
- `get_updates(offset)` com long-polling igual ao polling.py
- `sys.path.insert(0, ...)` para importar `app.*`
- `load_dotenv()` no topo
- `TELEGRAM_BOT_TOKEN` via `settings.TELEGRAM_BOT_TOKEN`
- `from app.database import engine` + `from sqlalchemy import text` para escrita no banco
- `os.makedirs("data", exist_ok=True)` antes de salvar JSON
- Teclado inline como `ReplyKeyboardMarkup` montado manualmente via `sendMessage` com parâmetro `reply_markup`
- Validação de nota: deve ser inteiro entre 0 e 10; mensagem de erro se inválido
- `/cancelar` a qualquer momento finaliza sem salvar
- Logging igual ao polling.py: `logging.basicConfig(level="INFO")`
- `asyncio.run(main())` no `if __name__ == "__main__":`

### Variáveis de ambiente necessárias (já existentes no `.env`)

```
TELEGRAM_BOT_TOKEN=  (já existe)
```

Nenhuma variável nova necessária.

---

## NPS-02 — `scripts/generate_nps_mock.py`

### Motivação
Para demonstrar o dashboard sem precisar coletar respostas reais, geramos 20
interações simuladas com perfis realistas. O script escreve em **PostgreSQL**
(tabela `nps_responses`) e em `data/nps_results.json`. Registros mock são
identificados por `telegram_user_id` no range `10000001–10000099` — podem ser
deletados e reinseridos a cada execução (idempotente).

### Perfis de cliente (distribuição realista)

| Perfil | % | Comportamento |
|---|---|---|
| Promotor entusiasmado | 30% (6 de 20) | Notas 8-10 em tudo, comentário positivo |
| Promotor fiel | 25% (5 de 20) | Notas 7-9, sem comentário ou breve |
| Neutro satisfeito | 20% (4 de 20) | Notas 6-8, observação leve |
| Detrator por logística | 10% (2 de 20) | Nota 2-5 em logística, resto ok |
| Detrator de atendimento | 10% (2 de 20) | Nota 2-5 em atendimento, resto ok |
| Detrator geral | 5% (1 de 20) | Notas baixas em tudo |

Total: 20 interações.

### Nomes paraenses (autenticidade para a demo)

Usar nomes típicos: Raimunda, João Batista, Maria das Graças, Carlos Alberto,
Benedita, Francisco, Natália, Sebastião, Ana Paula, Marcos, Lúcia, José Eduardo,
Sandra, Antônio, Cláudia, Wilson, Rosa, Manoel, Priscila, Aldenir.

### Timestamps

Distribuir os 20 resultados ao longo dos últimos 30 dias. Horários comerciais
(08h-18h). `datetime.now() - timedelta(days=random.randint(0, 30))`.

### Comentários por perfil (pool de frases — escolher aleatoriamente)

**Promotores:**
- "Produto chegou antes do prazo, excelente qualidade!"
- "Atendimento incrível, vou indicar para minha empresa."
- "Jaleco ficou perfeito, todo mundo da clínica adorou."
- "Bordado caprichado, superou as expectativas."
- "" (sem comentário — 30% dos promotores)

**Neutros:**
- "Produto bom mas a entrega atrasou um dia."
- "Atendimento poderia ser mais ágil."
- "Gostei, mas esperava mais opções de cor."
- "" (sem comentário)

**Detratores:**
- "Pedido chegou com 5 dias de atraso, precisava para evento."
- "Bordado ficou diferente do que pedi."
- "Demorei muito para ser atendido."
- "Produto veio com defeito no acabamento."

### Execução

```bash
python app/migrations/migrate_sprint_nps.py   # obrigatório antes da 1ª execução
python scripts/generate_nps_mock.py
# → PostgreSQL: 20 registros inseridos em nps_responses
# → JSON: data/nps_results.json criado/sobrescrito
# → Imprime resumo: X promotores, Y neutros, Z detratores, NPS Score
```

---

## NPS-03 — `docs/evaluation/reports/nps_dashboard.html`

### Motivação
Este é o principal entregável da reunião. Um arquivo HTML standalone (sem servidor)
que abre no browser e demonstra ao cliente Matheus o **poder dos dados de NPS**.

### Filosofia do dashboard

Não é apenas um gráfico de notas. É um **instrumento de negócio**. Cada seção
explica ao cliente leigo o que aquela métrica significa e que ação ela recomenda.
Didático, mas visualmente sofisticado.

### Sections do Dashboard (em ordem de apresentação)

#### Seção 0 — Header
- Título: "Camisart Belém — Análise de Satisfação"
- Subtítulo: período coberto + total de respondentes
- Badge com NPS Score calculado

#### Seção 1 — NPS Score (hero card)
**Cálculo:** `NPS = % Promotores − % Detratores`
- Gauge visual grande (SVG ou canvas) com escala -100 a +100
- Faixas coloridas: vermelho (-100 a -1), amarelo (0 a 49), verde (50 a 100)
- Explicação didática: "O que é NPS e por que importa"
- Distribuição promotores/neutros/detratores (barras horizontais)

#### Seção 2 — Radar por Dimensão
Gráfico radar com as 5 categorias: Logística, Qualidade, Expectativa, Atendimento, Indicação
- Notas médias por dimensão
- Linha tracejada na meta (8.0)
- Legenda explicando cada dimensão
- Insight automático: "Sua maior força é X. Atenção com Y."

#### Seção 3 — Distribuição das Notas (por categoria)
Para cada uma das 5 categorias, um mini histograma horizontal (0-10)
- Barras coloridas: vermelho (0-6), amarelo (7-8), verde (9-10)
- Percentual de cada faixa
- Nota média da categoria

#### Seção 4 — Análise de Sentimento nos Comentários
- Total de comentários recebidos vs total de respondentes (% de engajamento)
- Nuvem de palavras simplificada (SVG com font-size proporcional à frequência)
- Lista dos comentários completos, com avatar colorido pela classificação

#### Seção 5 — Mapa de Calor Temporal
- Heatmap dos últimos 30 dias (dias da semana × semanas)
- Cores pelo NPS médio do dia
- "Quando seus clientes mais respondem?"

#### Seção 6 — Ações Recomendadas (o mais importante para a reunião)
Cards de ação ordenados por impacto:
- Para cada dimensão com média < 8: card de ação específica
- Ex: "Logística 6.2 → Renegociar SLA com transportadora / Adicionar rastreamento"
- Ex: "Atendimento 7.1 → Treinamento de resposta em até 2h / Script de boas-vindas"
- Badge de prioridade: 🔴 Crítico / 🟡 Importante / 🟢 Melhorar

#### Seção 7 — Comparativo de Promotores vs Detratores
Tabela comparativa: nota média de cada categoria para promotores vs detratores
- "O que diferencia quem indica de quem não indica?"

### Especificações técnicas do HTML

- **Standalone**: todos os assets inline (Chart.js via CDN, sem servidor necessário)
- **Dados embutidos**: lê `data/nps_results.json` via `fetch('./../../data/nps_results.json')`
  com fallback para dados hardcoded (para funcionar sem servidor local)
- **Responsivo**: funciona em tela cheia de notebook (1440px) e tablet (768px)
- **Tema**: dark elegante — fundo `#0f0f13`, cards `#1a1a24`, accent teal `#1D9E75`
  (mesma cor teal do sistema Camisart)
- **Tipografia**: `'Segoe UI', system-ui, sans-serif` — sem dependências de fonte externa
- **Charts**: Chart.js 4.x via CDN `cdn.jsdelivr.net`
- **Animações**: entrada suave dos cards (CSS transitions), sem heavy JS
- **Fallback de dados**: se fetch falhar (arquivo aberto diretamente), usa os 20
  registros mock hardcoded no próprio HTML para que a demo sempre funcione

### NPS Score — fórmula

```javascript
const promotores = respostas.filter(r => r.respostas.indicacao.nota >= 9).length;
const detratores = respostas.filter(r => r.respostas.indicacao.nota <= 6).length;
const total = respostas.length;
const nps = Math.round((promotores / total - detratores / total) * 100);
```

---

## Ordem de Execução para o Claude Code

```
1. NPS-00 — migration (cria tabela nps_responses antes de qualquer escrita)
2. NPS-02 — generate_nps_mock.py (semeia banco + JSON)
3. NPS-01 — telegram_nps.py (dual-write em tempo real)
4. NPS-03 — nps_dashboard.html (lê JSON, fallback embutido)
```

---

## Commits Atômicos Esperados

```bash
feat(migrations): tabela nps_responses com índices para análise [NPS-00]
feat(scripts): gerador mock NPS com dual-write PostgreSQL + JSON [NPS-02]
feat(scripts): bot Telegram NPS com persistência em banco [NPS-01]
feat(dashboard): dashboard NPS standalone com 7 seções didáticas [NPS-03]
```

---

## Critérios de Aceite

- [ ] `python app/migrations/migrate_sprint_nps.py` cria tabela sem erro, idempotente
- [ ] Segunda execução da migration não levanta erro (IF NOT EXISTS funciona)
- [ ] `python scripts/generate_nps_mock.py` gera `data/nps_results.json` com 20 registros
- [ ] `SELECT COUNT(*) FROM nps_responses` retorna 20 após o mock
- [ ] `python scripts/telegram_nps.py` inicia sem erro e responde `/start` no Telegram
- [ ] Bot NPS aplica validação: nota fora de 0-10 → mensagem de erro + repergunta
- [ ] `/cancelar` a qualquer momento encerra sem salvar parcialmente
- [ ] Resposta completa no bot: nova linha aparece em `nps_responses` no banco
- [ ] `data/nps_results.json` acumula resultados (não sobrescreve a cada resposta)
- [ ] Se PostgreSQL falhar, JSON ainda é salvo (fallback silencioso com log)
- [ ] `nps_dashboard.html` abre no browser sem servidor e exibe todas as 7 seções
- [ ] Dashboard funciona com dados hardcoded (fallback) quando fetch falha
- [ ] NPS Score calculado e exibido corretamente no gauge
- [ ] Seção de Ações Recomendadas exibe cards apenas para dimensões com média < 8
- [ ] Comentários listados com classificação (promotor/neutro/detrator)
