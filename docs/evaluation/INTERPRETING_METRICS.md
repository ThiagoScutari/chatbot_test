# Como interpretar o relatório de desempenho do Camisart AI

> **Público-alvo:** cliente, stakeholder não-técnico, gestor de operação.
> **Pré-requisito:** nenhum conhecimento de IA ou estatística.
> **Objetivo:** entender o que cada número do dashboard significa, quando se preocupar e o que fazer quando uma métrica fica abaixo da meta.

---

## 1. Accuracy — a métrica mais simples

### O que é
Percentual de perguntas em que o bot entendeu corretamente o que o cliente quis dizer.

### Exemplo real do projeto
Nossa última avaliação rodou em **200 mensagens** reais de clientes. Se o bot acerta 189 delas:

```
Accuracy = 189 / 200 = 94,5%
```

### Como comparar
| Tipo de atendente | Accuracy típica |
|---|---|
| Atendente humano treinado | ~97% |
| Bot com LLM de ponta + FAQ curado (nosso caso) | **94-96%** |
| Chatbot comercial genérico | 75-85% |
| Bot só com palavras-chave | 60-70% |

### Quando se preocupar
- Accuracy **abaixo de 85%** → algo está estruturalmente errado
- Accuracy entre **85-95%** → bom, dentro da faixa profissional
- Accuracy **acima de 95%** → excepcional

### Limitação importante
Accuracy sozinha pode ser enganosa. Um bot que sempre responde "não entendi" teria accuracy alta em mensagens fora do escopo — mas seria inútil. Por isso lemos **F1 junto**.

---

## 2. F1 Score — a métrica que não engana

### O que é
Média harmônica entre **precisão** e **recall**. Penaliza tanto quando o bot erra ao responder (falso positivo) quanto quando ele deixa de responder algo que devia (falso negativo).

### Intuição
- **Precisão alta, recall baixo:** o bot só responde quando tem muita certeza, mas deixa muita gente sem resposta.
- **Recall alto, precisão baixa:** o bot responde tudo, mas frequentemente erra.
- **F1 alto:** equilíbrio — responde a maioria das perguntas e acerta a maioria das respostas.

### Interpretação prática
| F1 | Leitura |
|---|---|
| ≥ 93% | Excelente — cliente percebe o bot como competente |
| 85-92% | Bom — falhas pontuais, aceitável |
| 75-84% | Regular — reforçar FAQ nos intents fracos |
| < 75% | Insatisfatório — revisão estrutural |

---

## 3. Matriz de Confusão — o mapa dos erros

### Como ler
Cada linha da matriz é **o que o cliente realmente quis dizer**.
Cada coluna é **o que o bot achou que ele quis dizer**.
A **diagonal** (canto superior esquerdo até inferior direito) são os acertos.
Tudo **fora da diagonal** são os erros — e o gráfico mostra exatamente onde melhorar.

### Exemplo
Se na linha `bordado_prazo` aparece `4x` na coluna `prazo_entrega`, isso significa:

> "Em 4 ocasiões o cliente perguntou sobre prazo do bordado, e o bot entendeu como prazo geral de entrega."

→ A ação corretiva é adicionar padrões de regex ou exemplos ao intent `bordado_prazo` para diferenciar melhor das perguntas sobre prazo de entrega normal.

---

## 4. Accuracy por Camada — qual parte da arquitetura acerta mais

O Camisart AI opera em **três camadas** em ordem:

1. **FAQ (regex)** — Camada 1, ~1ms. Resolve as perguntas diretas ("preço da polo?").
2. **LLM Router** — Camada 2, ~1500-2500ms. Lida com variações linguísticas.
3. **RAG** — Camada 3, ~2000-3000ms. Responde perguntas técnicas abertas sobre o catálogo.

Se a accuracy da Camada 1 está em 97% mas a Camada 2 em 70%, o problema está na classificação do LLM Router — provavelmente os thresholds estão mal calibrados.

---

## 5. Fallback indevido — o bot "desistiu" sem motivo

### O que é
Percentual de vezes em que o bot respondeu "não entendi" quando deveria ter entendido.

### Por que é crítica
É a métrica que mais machuca a percepção do cliente. Ele sabe que pediu algo legítimo e o bot falhou — cada ocorrência é uma possível perda de venda.

### Meta
- **< 5%** → excelente
- **5-10%** → aceitável
- **> 10%** → investigar urgentemente

---

## 6. Latência — o bot responde rápido?

| Camada | Meta | Realidade |
|---|---|---|
| FAQ | < 5ms | Normalmente < 1ms |
| LLM Router | < 3000ms | ~1500-2500ms |
| RAG | < 5000ms | ~2000-3500ms |

Latência acima das metas não significa erro, mas pode irritar o cliente em conversas rápidas por WhatsApp. Se LLM passar de 5s, revisar tamanho do prompt.

---

## 7. Score Qualitativo — a "nota do cliente"

Enquanto Accuracy/F1 medem correção técnica, o score qualitativo mede **percepção**. Um avaliador humano pontua cada resposta em 5 dimensões (1-5):

- **Precisão** — a resposta está correta?
- **Completude** — cobre tudo que o cliente precisava?
- **Tom** — adequado para uma loja de uniformes?
- **Clareza** — fácil de entender?
- **Ação** — o cliente saberia o que fazer depois?

O score final (0-100) indica se o cliente percebe o bot como um assistente competente. Um bot com 94% accuracy técnica mas score qualitativo 60 provavelmente soa robótico ou incompleto.

---

## 8. O que fazer quando uma métrica está baixa

| Métrica baixa | Causa provável | Ação corretiva |
|---|---|---|
| Accuracy global < 85% | Dataset desbalanceado ou FAQ com gaps | Revisar distribuição do dataset e rodar `faq_coverage_check.py` |
| F1 macro < 80% | Um ou mais intents com poucas variações | Adicionar padrões ao `faq.json` nos intents fracos |
| F1 de um intent < 70% | Regex restrita demais ou conflito com outro intent | Ampliar regex, ajustar `priority`, adicionar exemplos no LLM |
| Fallback > 15% | Base de conhecimento/FAQ incompletos | Ampliar `faq.json` e `camisart_knowledge_base.md` |
| Accuracy FAQ < 90% | Regex com bugs ou priority incorreta | Auditar priorities e patterns |
| Accuracy LLM < 80% | Thresholds altos demais ou prompt fraco | Reduzir threshold medium de 0.60 para 0.50 ou ajustar system prompt |
| Accuracy RAG < 80% | Chunks ausentes ou embedding ruim | Reindexar conhecimento, revisar chunking |
| Latência FAQ > 5ms | Regex patológico (catastrophic backtracking) | Revisar regex complexas, testar com timeout |
| Latência LLM > 3s | Prompt longo demais ou modelo errado | Encurtar prompt, usar Haiku em vez de Sonnet |
| Score qualitativo < 75 | Respostas tecnicamente corretas mas frias | Revisar tom das respostas no `faq.json` |

---

## 9. Glossário — termos em linguagem simples

| Termo técnico | Tradução |
|---|---|
| **Accuracy** | "Quantas perguntas o bot acertou?" |
| **Precision** | "Quando ele decide responder, está certo?" |
| **Recall** | "Ele responde tudo que deveria?" |
| **F1 Score** | "Uma nota única que considera os dois acima" |
| **Matriz de Confusão** | "Tabela dos erros: o que o cliente quis × o que o bot entendeu" |
| **Intent** | "A intenção do cliente — ex: perguntar preço, pedir endereço" |
| **Fallback** | "Quando o bot responde 'não entendi'" |
| **Camada 1 / FAQ** | "Regras diretas baseadas em palavras-chave" |
| **Camada 2 / LLM** | "Inteligência artificial (Claude Haiku) classificando a mensagem" |
| **Camada 3 / RAG** | "Busca no catálogo + IA para perguntas técnicas abertas" |
| **Latência** | "Tempo que o bot leva pra responder" |
| **Ground truth** | "A resposta correta conhecida, rotulada por humanos" |
| **Dataset** | "Planilha com as 200 perguntas rotuladas usadas para avaliar" |
| **Thresholds** | "Limites de confiança para o bot aceitar a classificação do LLM" |

---

## 10. Como executar uma nova avaliação

```bash
# 1. Rodar a avaliação completa e gerar relatório JSON
python scripts/evaluate.py --export

# 2. Gerar o dashboard HTML
python scripts/dashboard.py

# 3. Abrir no browser (o arquivo é standalone, não precisa servidor)
# Caminho: docs/evaluation/reports/YYYY-MM-DD_dashboard.html

# Filtros úteis
python scripts/evaluate.py --layer faq          # só Camada 1
python scripts/evaluate.py --difficulty hard    # só casos difíceis
python scripts/evaluate.py --no-llm             # pula Camada 2 (mais rápido)
```

---

## 11. Metas do projeto (Sprint 08)

| Métrica | Meta mínima | Meta ideal |
|---|---|---|
| Accuracy global | 85% | 95% |
| F1 macro | 82% | 93% |
| Fallback indevido | < 15% | < 5% |
| Latência FAQ | < 5ms | < 1ms |
| Latência LLM | < 3000ms | < 2000ms |
| Score qualitativo | 75+ | 85+ |

Se qualquer métrica ficar abaixo da meta mínima, o próprio dashboard (seção "Erros mais frequentes") aponta os primeiros intents a corrigir.
