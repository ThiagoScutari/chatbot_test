# Guia de Construção — Chatbot Baseado em Regras

> Este guia explica como o projeto foi construído, os conceitos utilizados e como executar cada etapa.
> É voltado para quem está aprendendo sobre chatbots baseados em regras com Python.

---

## Sumário

1. [Decisões de Design](#decisões-de-design)
2. [Conceitos Fundamentais](#conceitos-fundamentais)
   - [Máquina de Estados](#máquina-de-estados)
   - [SQLite](#sqlite)
   - [Flask](#flask)
   - [python-telegram-bot](#python-telegram-bot)
3. [Como Executar](#como-executar)
4. [Como Rodar os Testes](#como-rodar-os-testes)
5. [Estrutura do Projeto](#estrutura-do-projeto)

---

## Decisões de Design

Todas as decisões de arquitetura — por que escolhemos Python, SQLite, máquina de estados e as 3 etapas progressivas de interface — estão registradas no spec do projeto:

📄 [`docs/superpowers/specs/2026-04-19-chatbot-regras-design.md`](superpowers/specs/2026-04-19-chatbot-regras-design.md)

O resumo das decisões principais:

| Decisão | Escolha | Motivo |
|---|---|---|
| Linguagem | Python | Simplicidade e curva de aprendizado suave |
| Lógica do chatbot | Máquina de estados | Padrão clássico para chatbots baseados em regras; explícito e fácil de debugar |
| Banco de dados | SQLite | Banco relacional local sem servidor, permite aprender SQL no contexto do projeto |
| Interfaces | 3 etapas progressivas | Cada etapa reutiliza o núcleo (`core/`), evoluindo de terminal → web → Telegram |

---

## Conceitos Fundamentais

### Máquina de Estados

Uma **máquina de estados** é um modelo onde o sistema pode estar em um número finito de estados. A cada mensagem recebida, o sistema avança de um estado para outro com base em regras definidas.

Este é o padrão clássico para chatbots baseados em regras: a lógica é explícita, fácil de ler e debugar.

#### Os estados deste projeto

Definidos em [`core/states.py`](../core/states.py):

```python
INICIO         = "inicio"
AGUARDA_NOME   = "aguarda_nome"
MENU           = "menu"
AGUARDA_PEDIDO = "aguarda_pedido"
FIM            = "fim"
```

Cada constante é uma simples string. Usar constantes (em vez de strings literais espalhadas pelo código) evita erros de digitação e facilita refatorações.

#### Diagrama de fluxo

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
   início      ┌────▼────┐      ┌──────────────┐                 │
  automático   │  INICIO  │─────▶│ AGUARDA_NOME │                 │
               └─────────┘      └──────┬───────┘                 │
                                       │ nome digitado            │
                                       ▼                          │
                                  ┌─────────┐                     │
                                  │  MENU   │◀────────────────────┘
                                  └────┬────┘    opção inválida
                                       │
                      ┌────────────────┴────────────────┐
                      │ opção "1"                        │ opção "2"
                      ▼                                  ▼
              ┌───────────────┐               ┌──────────────────────┐
              │ AGUARDA_PEDIDO│               │ FIM                  │
              └───────┬───────┘               │ acao="enviar_catalog"│
                      │ pedido encontrado      └──────────────────────┘
                      ▼
               ┌─────────────┐
               │     FIM     │
               └─────────────┘
```

#### O contrato da função `handle()`

Toda a lógica de transição está em [`core/handlers.py`](../core/handlers.py). A função `handle()` recebe a mensagem do usuário e o estado atual da sessão, e retorna uma tupla com três valores:

```python
def handle(mensagem: str, sessao: dict) -> tuple[str, str, str | None]:
    # Retorna: (resposta, proximo_estado, acao)
    # acao: None | "enviar_catalogo"
```

- **`resposta`** — o texto que o bot deve enviar ao usuário
- **`proximo_estado`** — o estado para o qual a sessão deve avançar
- **`acao`** — `None` na maioria dos casos; `"enviar_catalogo"` quando o usuário escolhe o catálogo

A **sessão** é um dicionário simples que persiste o estado atual e o nome do usuário durante a conversa:

```python
sessao = {
    "nome": None,
    "estado": INICIO
}
```

Cada interface (terminal, web, Telegram) é responsável por armazenar e passar essa sessão para `handle()`. O núcleo (`core/`) não sabe nada sobre a interface — isso é o **desacoplamento** que permite reutilizar a lógica nas 3 etapas.

#### Como a máquina de estados é implementada

Em `core/handlers.py`, a lógica é uma sequência de `if/elif` verificando `sessao["estado"]`:

```python
if estado == INICIO:
    sessao["estado"] = AGUARDA_NOME
    return ("Olá! Bem-vindo...", AGUARDA_NOME, None)

if estado == AGUARDA_NOME:
    if not mensagem:
        return ("Por favor, digite o seu nome.", AGUARDA_NOME, None)
    sessao["nome"] = mensagem
    sessao["estado"] = MENU
    return (f"Prazer, {mensagem}! ...", MENU, None)

# ... e assim por diante para MENU, AGUARDA_PEDIDO e FIM
```

Cada bloco cuida de um estado: valida a entrada, atualiza a sessão e retorna a resposta com o próximo estado.

---

### SQLite

**SQLite** é um banco de dados relacional que armazena tudo em um único arquivo `.db` no disco. Não precisa de servidor — é uma biblioteca que faz parte da biblioteca padrão do Python (`import sqlite3`).

#### Por que SQLite aqui?

Para este projeto de aprendizado, SQLite é ideal: zero configuração, funciona em qualquer máquina, e permite praticar SQL básico.

#### O schema da tabela de pedidos

Definido em [`core/database.py`](../core/database.py):

```sql
CREATE TABLE IF NOT EXISTS pedidos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    numero      TEXT UNIQUE,
    cliente     TEXT,
    produto     TEXT,
    quantidade  INTEGER,
    status      TEXT,
    data_pedido TEXT
)
```

Pontos importantes:
- `INTEGER PRIMARY KEY AUTOINCREMENT` — chave primária gerada automaticamente a cada inserção
- `TEXT UNIQUE` no campo `numero` — garante que dois pedidos não tenham o mesmo número
- `CREATE TABLE IF NOT EXISTS` — a instrução não falha se a tabela já existir

#### Como o banco é usado no código

Há duas funções principais em `core/database.py`:

**`inicializar_banco()`** — chamada uma vez ao iniciar cada interface. Cria a tabela (se não existir) e insere os 5 pedidos fictícios (se o banco estiver vazio):

```python
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS pedidos (...)")
cursor.execute("SELECT COUNT(*) FROM pedidos")
if cursor.fetchone()[0] == 0:
    cursor.executemany("INSERT INTO pedidos ...", _PEDIDOS_INICIAIS)
conn.commit()
conn.close()
```

**`buscar_pedido(numero)`** — busca um pedido pelo número. Usa `row_factory` para retornar um dicionário em vez de uma tupla, facilitando o acesso por nome de coluna:

```python
conn.row_factory = sqlite3.Row  # permite: row["cliente"] em vez de row[2]
cursor.execute("SELECT * FROM pedidos WHERE numero = ?", (numero,))
row = cursor.fetchone()
```

O `?` é um **parâmetro de substituição seguro** — protege contra SQL Injection ao separar o comando SQL dos dados do usuário.

#### Dados fictícios disponíveis para teste

| Número | Cliente | Produto | Status |
|---|---|---|---|
| 1001 | Ana Silva | Cadeira Gamer | Entregue |
| 1002 | João Costa | Mesa de Escritório | Enviado |
| 1003 | Maria Souza | Monitor 27" | Em separação |
| 1004 | Carlos Lima | Teclado Mecânico | Entregue |
| 1005 | Beatriz Alves | Headset Gamer | Enviado |

---

### Flask

**Flask** é um microframework web para Python. Com poucas linhas de código, você cria um servidor HTTP que responde a rotas (URLs).

#### Conceitos usados neste projeto

**Rotas** — cada função Python decorada com `@app.route(...)` responde a uma URL:

```python
@app.route("/")           # GET http://127.0.0.1:5000/
@app.route("/mensagem", methods=["POST"])   # POST com JSON
@app.route("/catalogo")   # GET — serve o PDF
```

**Sessão do Flask** — o objeto `session` do Flask armazena dados entre requisições usando um **cookie criptografado** no navegador. Isso é como o estado da conversa persiste entre as mensagens enviadas pelo usuário:

```python
app.secret_key = "chatbot-dev-secret-2026"  # chave para criptografar o cookie

session["chatbot"] = sessao_chatbot  # salva estado na sessão HTTP
sessao_chatbot = session.get("chatbot", ...)  # recupera na próxima requisição
```

**JSON** — a rota `/mensagem` recebe e retorna JSON, permitindo que o frontend JavaScript se comunique com o servidor sem recarregar a página:

```python
dados = request.get_json()       # lê JSON do corpo da requisição POST
return jsonify({                 # converte dict Python em resposta JSON
    "resposta": resposta,
    "fim": novo_estado == FIM,
    "acao": acao,
})
```

**`send_file()`** — a rota `/catalogo` usa essa função do Flask para servir o arquivo PDF como download:

```python
return send_file(CATALOGO_PATH, as_attachment=True, download_name="Catalogo.pdf")
```

#### Rotas do projeto ([`etapa2_web/app.py`](../etapa2_web/app.py))

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Renderiza `index.html` com a mensagem inicial do bot |
| `POST` | `/mensagem` | Recebe `{"texto": "..."}`, retorna `{"resposta": "...", "fim": bool, "acao": ...}` |
| `GET` | `/catalogo` | Serve `Catalogo.pdf` como download |

---

### python-telegram-bot

**python-telegram-bot** (versão 20+) é a biblioteca Python para criar bots no Telegram. A versão 20+ usa **asyncio** — todas as funções de handler são `async def`.

#### Conceitos usados neste projeto

**`Application`** — o objeto central que gerencia o bot. Criado com o token do bot obtido no BotFather:

```python
app = Application.builder().token(token).build()
```

**Handlers** — funções que respondem a eventos específicos. Neste projeto, dois tipos são usados:

```python
app.add_handler(CommandHandler("start", cmd_start))
# registra cmd_start() para responder ao comando /start

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
# registra responder() para qualquer mensagem de texto que não seja um comando
```

**`context.user_data`** — dicionário persistente por usuário, mantido em memória enquanto o bot estiver rodando. É onde a sessão da conversa fica armazenada, equivalente ao `flask.session` da etapa 2:

```python
context.user_data["chatbot"] = {"nome": None, "estado": INICIO}
sessao = context.user_data["chatbot"]
```

**`reply_document()`** — envia um arquivo na conversa. Usado para enviar o PDF do catálogo:

```python
with open(CATALOGO_PATH, "rb") as f:
    await update.message.reply_document(document=f, filename="Catalogo.pdf")
```

**`run_polling()`** — faz o bot ficar "escutando" atualizações do Telegram em loop, processando cada mensagem recebida.

#### Fluxo no Telegram ([`etapa3_telegram/bot.py`](../etapa3_telegram/bot.py))

1. Usuário envia `/start` → `cmd_start()` reinicia a sessão e envia boas-vindas
2. Usuário envia qualquer texto → `responder()` passa para `handle()` do `core/`
3. Se `acao == "enviar_catalogo"` → bot envia o PDF via `reply_document()`
4. Se conversa chegou ao `FIM` → bot orienta o usuário a enviar `/start` para recomeçar

---

## Como Executar

### Pré-requisitos

```bash
pip install -r requirements.txt
```

### Etapa 1 — Terminal

Não requer dependências externas além do Python padrão.

```bash
python etapa1_terminal/main.py
```

Exemplo de conversa:

```
Bot: Olá! Bem-vindo ao nosso atendimento. 😊
     Qual é o seu nome?

Você: Ana
Bot: Prazer, Ana! Como posso te ajudar?
     1 - Consultar pedido
     2 - Receber catálogo de produtos

Você: 1
Bot: Por favor, informe o número do pedido (ex: 1001):

Você: 1001
Bot: 📦 Pedido #1001
     Cliente:    Ana Silva
     ...
```

### Etapa 2 — Web

```bash
python etapa2_web/app.py
```

Abra o navegador em: **http://127.0.0.1:5000**

O servidor Flask inicia em modo `debug=True`, o que significa que reinicia automaticamente ao salvar alterações no código.

### Etapa 3 — Telegram

Você precisa de um token de bot do Telegram (obtenha no [@BotFather](https://t.me/BotFather)).

**Windows:**
```bash
set TELEGRAM_BOT_TOKEN=seu_token_aqui
python etapa3_telegram/bot.py
```

**Linux/macOS:**
```bash
export TELEGRAM_BOT_TOKEN=seu_token_aqui
python etapa3_telegram/bot.py
```

Com o bot rodando, abra o Telegram e envie `/start` para o seu bot.

---

## Como Rodar os Testes

O projeto usa **pytest** para testes automatizados.

```bash
pytest -v
```

Os testes estão em [`tests/`](../tests/) e cobrem:

- **`tests/test_handlers.py`** — testa cada transição da máquina de estados: estado inicial, captura de nome, menu, consulta de pedido, catálogo e estado terminal
- **`tests/test_database.py`** — testa a inicialização do banco e a busca de pedidos (pedido existente e número inexistente)

Os testes usam um banco SQLite **em memória** (via `monkeypatch`), então não alteram o banco real em `data/pedidos.db`.

Resultado esperado: **19 testes passando**.

---

## Estrutura do Projeto

```
chatbot/
├── core/                        ← núcleo compartilhado entre as 3 etapas
│   ├── __init__.py
│   ├── states.py                ← constantes dos estados da máquina
│   ├── handlers.py              ← lógica de cada estado (função handle())
│   └── database.py              ← acesso ao SQLite (inicializar, buscar)
│
├── etapa1_terminal/
│   └── main.py                  ← loop de input/output no terminal
│
├── etapa2_web/
│   ├── app.py                   ← servidor Flask (3 rotas)
│   └── templates/
│       └── index.html           ← interface web do chat
│
├── etapa3_telegram/
│   └── bot.py                   ← bot Telegram com python-telegram-bot v20+
│
├── tests/
│   ├── test_handlers.py         ← testes da máquina de estados
│   └── test_database.py         ← testes do banco de dados
│
├── data/                        ← criado automaticamente na primeira execução
│   └── pedidos.db               ← banco SQLite com os pedidos fictícios
│
├── docs/
│   ├── Catalogo.pdf             ← catálogo de produtos (enviado/aberto pelo bot)
│   ├── guia.md                  ← este guia
│   └── superpowers/
│       └── specs/
│           └── 2026-04-19-chatbot-regras-design.md   ← spec e decisões de design
│
├── pyrightconfig.json           ← configuração do type checker
├── pytest.ini                   ← configuração dos testes
└── requirements.txt             ← dependências do projeto
```

### Fluxo de dependências

```
etapa1_terminal/main.py ─────┐
etapa2_web/app.py ───────────┼──▶ core/handlers.py ──▶ core/states.py
etapa3_telegram/bot.py ──────┘         │
                                        └──────────────▶ core/database.py
```

O `core/` não importa nada das etapas — ele é independente de interface. As etapas importam o `core/`, mas nunca importam umas às outras.
