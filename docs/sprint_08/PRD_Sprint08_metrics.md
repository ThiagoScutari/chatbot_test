# PRD — Sprint 08: Métricas, Avaliação e Dashboard
**Projeto:** Camisart AI  
**Branch:** `sprint/08-metrics`  
**Status:** Aprovação Pendente  
**Origem:** Necessidade de apresentação ao cliente + validação científica do bot  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S08-01 | `docs/evaluation/` | Dataset rotulado — 200 mensagens com ground truth | 🔴 |
| S08-02 | `scripts/` | `evaluate.py` — calcula todas as métricas quantitativas | 🔴 |
| S08-03 | `scripts/` | `dashboard.py` — gera relatório HTML com gráficos interativos | 🔴 |
| S08-04 | `scripts/` | `qualitative_eval.py` — avaliação qualitativa de amostras | 🟡 |
| S08-05 | `tests/` | Testes do pipeline de avaliação | 🟡 |
| S08-06 | `docs/` | Guia de interpretação das métricas para o cliente | 🟢 |

---

## Objetivo do Sprint

Produzir um **pacote de avaliação completo** — métricas quantitativas com gráficos profissionais — que responde objetivamente à pergunta do cliente: *"como eu sei que o bot está funcionando bem?"*

Ao final deste sprint você terá:
1. Um **score de avaliação** por camada (FAQ, LLM, RAG)
2. Uma **matriz de confusão** visual mostrando onde o bot acerta e erra
3. Um **dashboard HTML** exportável para apresentação em reunião
4. Um **relatório executivo** em português para o cliente não-técnico

---

## S08-01 — Dataset rotulado (ground truth)

### O que é e por que é crítico

O dataset é a **base de verdade** da avaliação. Cada linha tem:
- A mensagem do cliente (input)
- A intenção correta (o que um humano diria que o cliente quis dizer)
- A camada esperada para resolver (FAQ, LLM ou RAG)

Sem dataset rotulado, as métricas não têm sentido. É como fazer uma prova sem gabarito.

### Estrutura

```json
// docs/evaluation/dataset.json
{
  "version": "1.0",
  "description": "Dataset de avaliação do Camisart AI — 200 mensagens rotuladas",
  "created_at": "2026-04-23",
  "stats": {
    "total": 200,
    "by_intent": {},
    "by_layer": {"faq": 120, "llm": 50, "rag": 30}
  },
  "samples": [
    {
      "id": "S001",
      "message": "qual o preço da polo?",
      "expected_intent": "preco_polo",
      "expected_layer": "faq",
      "difficulty": "easy",
      "notes": "pergunta direta, deve ser resolvida por regex"
    },
    {
      "id": "S002",
      "message": "quanto custa aquela camisa com gola?",
      "expected_intent": "preco_polo",
      "expected_layer": "llm",
      "difficulty": "medium",
      "notes": "variação semântica — não tem regex exato"
    },
    {
      "id": "S003",
      "message": "qual tecido é melhor para jaleco de uso hospitalar?",
      "expected_intent": "rag_response",
      "expected_layer": "rag",
      "difficulty": "hard",
      "notes": "pergunta técnica — requer busca no catálogo"
    }
  ]
}
```

### Distribuição do dataset (200 mensagens)

| Intent | Fácil | Médio | Difícil | Total |
|--------|-------|-------|---------|-------|
| preco_polo | 8 | 6 | 4 | 18 |
| preco_jaleco | 6 | 4 | 3 | 13 |
| endereco | 6 | 3 | 2 | 11 |
| bordado_prazo | 6 | 4 | 2 | 12 |
| pedido_minimo | 5 | 3 | 2 | 10 |
| prazo_entrega | 5 | 3 | 2 | 10 |
| entrega_nacional | 5 | 4 | 3 | 12 |
| falar_humano | 5 | 4 | 3 | 12 |
| pagamento | 4 | 3 | 2 | 9 |
| feminino | 4 | 3 | 2 | 9 |
| desconto_quantidade | 4 | 3 | 2 | 9 |
| tamanhos_disponiveis | 4 | 3 | 2 | 9 |
| rag_response | 3 | 4 | 5 | 12 |
| none (fora do escopo) | 15 | 8 | 7 | 30 |
| outros intents | — | — | — | 24 |
| **Total** | **90** | **65** | **45** | **200** |

### Categorias de dificuldade

**Fácil:** a mensagem usa as palavras exatas que o FAQ espera  
`"qual o preço da polo?"` → regex casa diretamente

**Médio:** variação linguística que o LLM deve resolver  
`"quanto fica a camisa com gola?"` → sem regex, LLM classifica

**Difícil:** pergunta técnica aberta ou com múltipla interpretação  
`"qual tecido aguenta mais lavagem?"` → RAG necessário

---

## S08-02 — evaluate.py — métricas quantitativas

### O que calcula

```python
# scripts/evaluate.py
"""
Avalia o desempenho do Camisart AI contra o dataset rotulado.

Métricas calculadas:
  - Accuracy global e por camada
  - Precision, Recall, F1 por intent
  - Matriz de confusão
  - Fallback rate (% que virou None quando não devia)
  - Latência média por camada

Uso:
    python scripts/evaluate.py                    # avalia tudo
    python scripts/evaluate.py --layer faq        # só Camada 1
    python scripts/evaluate.py --difficulty hard  # só casos difíceis
    python scripts/evaluate.py --export           # salva JSON para dashboard
"""
```

### Saída no terminal

```
====================================================================
CAMISART AI — AVALIAÇÃO DE DESEMPENHO
Data: 2026-04-23 | Dataset: 200 amostras | Versão: 1.0
====================================================================

RESUMO EXECUTIVO
────────────────────────────────────────────────────────────────────
  Accuracy global:        94.5%  ████████████████████░  Excelente
  F1 macro:               93.1%  ███████████████████░░  Excelente
  Fallback indevido:       3.5%  █░░░░░░░░░░░░░░░░░░░░  Ótimo
  Latência média (FAQ):    0.8ms ██░░░░░░░░░░░░░░░░░░░  Excelente
  Latência média (LLM):  1842ms  ████████████████░░░░░  Bom
  Latência média (RAG):  2340ms  ██████████████████░░░  Bom

POR CAMADA
────────────────────────────────────────────────────────────────────
  Camada 1 (FAQ regex):   Accuracy 97.5% | 120 amostras | 0.8ms
  Camada 2 (LLM Router):  Accuracy 91.0% |  50 amostras | 1842ms
  Camada 3 (RAG):         Accuracy 86.7% |  30 amostras | 2340ms

POR DIFICULDADE
────────────────────────────────────────────────────────────────────
  Fácil  (90 amostras):   Accuracy 99.0%
  Médio  (65 amostras):   Accuracy 93.8%
  Difícil(45 amostras):   Accuracy 86.7%

POR INTENT (F1 Score)
────────────────────────────────────────────────────────────────────
  preco_polo          ████████████████████ 97.4%
  preco_jaleco        ███████████████████░ 95.1%
  endereco            ████████████████████ 96.6%
  bordado_prazo       ██████████████████░░ 92.3%
  pedido_minimo       ██████████████████░░ 91.7%
  entrega_nacional    ████████████████████ 96.0%
  falar_humano        ████████████████░░░░ 85.7%
  pagamento           ██████████████████░░ 91.3%
  rag_response        ████████████████░░░░ 86.7%
  none (fora escopo)  ████████████████████ 97.3%

ERROS MAIS FREQUENTES
────────────────────────────────────────────────────────────────────
  1. [12x] falar_humano → none  "não consigo entender os valores"
  2. [ 4x] preco_polo   → none  "camisa branca de trabalho"
  3. [ 3x] rag_response → falar_humano  "tecido resistente"

====================================================================
Relatório salvo em: docs/evaluation/reports/2026-04-23_report.json
Para gerar o dashboard: python scripts/dashboard.py
====================================================================
```

### Implementação das métricas

```python
# scripts/evaluate.py — core das métricas

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_recall_fscore_support,
)

class Evaluator:
    def __init__(self, dataset_path: Path):
        self.dataset = json.loads(dataset_path.read_text())
        self.results = []  # preenchido após run()

    async def run(self, pipeline: MessagePipeline, db: Session) -> EvalReport:
        """Executa cada amostra do dataset e coleta resultados."""
        for sample in self.dataset["samples"]:
            start = time.perf_counter()
            predicted = await self._predict(sample["message"], pipeline, db)
            latency_ms = (time.perf_counter() - start) * 1000

            self.results.append(EvalResult(
                sample_id=sample["id"],
                message=sample["message"],
                expected=sample["expected_intent"],
                predicted=predicted.intent_id,
                layer=predicted.layer,  # "faq" | "llm" | "rag"
                correct=predicted.intent_id == sample["expected_intent"],
                latency_ms=latency_ms,
                difficulty=sample.get("difficulty", "medium"),
            ))

        return self._compute_report()

    def _compute_report(self) -> EvalReport:
        y_true = [r.expected for r in self.results]
        y_pred = [r.predicted for r in self.results]

        # Métricas globais
        accuracy = accuracy_score(y_true, y_pred)

        # Métricas por intent
        precision, recall, f1, support = precision_recall_fscore_support(
            y_true, y_pred,
            average=None,
            labels=sorted(set(y_true)),
            zero_division=0,
        )

        # Matriz de confusão
        labels = sorted(set(y_true + y_pred))
        cm = confusion_matrix(y_true, y_pred, labels=labels)

        return EvalReport(
            accuracy=accuracy,
            precision_per_intent=dict(zip(labels, precision)),
            recall_per_intent=dict(zip(labels, recall)),
            f1_per_intent=dict(zip(labels, f1)),
            support_per_intent=dict(zip(labels, support)),
            confusion_matrix=cm.tolist(),
            confusion_labels=labels,
            results=self.results,
            timestamp=datetime.now().isoformat(),
        )
```

---

## S08-03 — dashboard.py — relatório HTML com gráficos

### O que gera

Um arquivo HTML standalone (sem servidor, sem dependências externas) com:

1. **Cards de resumo executivo** — accuracy, F1, latência, fallback rate
2. **Matriz de confusão** — heatmap interativo
3. **F1 por intent** — gráfico de barras horizontais
4. **Precision vs Recall** — gráfico de dispersão por intent
5. **Distribuição por camada** — pizza (FAQ vs LLM vs RAG)
6. **Curva de acurácia por dificuldade** — barras agrupadas
7. **Top erros** — tabela com as mensagens que o bot errou
8. **Seção executiva** — interpretação em português para o cliente

### Preview do dashboard

```
┌─────────────────────────────────────────────────────────┐
│  CAMISART AI — DESEMPENHO DO CHATBOT                     │
│  Avaliação em 200 mensagens reais | 2026-04-23           │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ ACCURACY │    F1    │ LATÊNCIA │ FALLBACK │  MENSAGENS  │
│  94.5%   │  93.1%   │  0.8ms   │   3.5%   │    200      │
│    ✅    │    ✅    │   FAQ    │    ✅    │  avaliadas  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  MATRIZ DE CONFUSÃO          F1 POR INTENÇÃO            │
│  [heatmap interativo]        [barras horizontais]        │
│                                                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  DISTRIBUIÇÃO POR CAMADA     ACURÁCIA POR DIFICULDADE   │
│  FAQ: 60% ████████           Fácil:  99% ██████████     │
│  LLM: 25% █████              Médio:  94% █████████      │
│  RAG: 15% ███                Difícil: 87% ████████      │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  ANÁLISE EXECUTIVA                                       │
│  O chatbot da Camisart respondeu corretamente 94.5% das  │
│  perguntas testadas. Das 200 mensagens avaliadas,        │
│  apenas 11 tiveram resposta incorreta. Os erros          │
│  concentram-se em perguntas técnicas complexas (camada   │
│  RAG), que podem ser melhoradas expandindo o catálogo.   │
└─────────────────────────────────────────────────────────┘
```

### Tecnologia dos gráficos

Usar **Chart.js** via CDN — biblioteca JavaScript leve, sem servidor, gráficos bonitos e interativos. O HTML gerado é um arquivo único que pode ser aberto em qualquer browser ou enviado por e-mail.

```python
# scripts/dashboard.py

CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4"

def generate_dashboard(report: EvalReport, output_path: Path) -> None:
    """
    Gera relatório HTML standalone com gráficos interativos.
    O arquivo pode ser aberto em qualquer browser sem servidor.
    """
    html = HTML_TEMPLATE.format(
        report_date=report.timestamp[:10],
        accuracy=f"{report.accuracy * 100:.1f}",
        f1_macro=f"{report.f1_macro * 100:.1f}",
        # ... dados para cada gráfico
    )
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ Dashboard salvo em: {output_path}")
    print(f"   Abrir no browser: {output_path.resolve()}")
```

---

## S08-04 — qualitative_eval.py — avaliação qualitativa

Métricas numéricas dizem *quanto* o bot erra. A avaliação qualitativa diz *como* ele erra — e se o erro seria percebido negativamente pelo cliente.

```python
# scripts/qualitative_eval.py
"""
Avaliação qualitativa de uma amostra de conversas.
Gera um formulário HTML onde o avaliador humano classifica
cada resposta em: Excelente / Boa / Aceitável / Ruim

Uso:
    python scripts/qualitative_eval.py --sample 30
    # Abre formulário com 30 conversas aleatórias para classificar
    # Salva resultado em docs/evaluation/qualitative/YYYY-MM-DD.json
"""
```

### Dimensões de avaliação qualitativa

| Dimensão | Pergunta | Escala |
|----------|---------|--------|
| **Precisão** | A resposta está correta? | 1-5 |
| **Completude** | A resposta cobre tudo que o cliente precisava? | 1-5 |
| **Tom** | O tom é apropriado para uma loja de uniformes? | 1-5 |
| **Clareza** | A resposta é fácil de entender? | 1-5 |
| **Ação** | O cliente saberia o que fazer depois? | 1-5 |

### Score qualitativo final

```
Score qualitativo = média das 5 dimensões × 20
                  = de 0 a 100
```

Um score qualitativo de 85+ significa que o cliente percebe o bot como um assistente competente — mesmo que a accuracy técnica seja 94%.

---

## S08-05 — Testes do pipeline de avaliação

```python
# tests/test_evaluation.py

def test_dataset_valido():
    """Dataset tem estrutura correta e todos os intents são válidos."""
    data = json.loads(Path("docs/evaluation/dataset.json").read_text())
    known_intents = set(...)  # lista de intents do faq.json
    for sample in data["samples"]:
        assert "message" in sample
        assert "expected_intent" in sample
        assert sample["expected_intent"] in known_intents \
            or sample["expected_intent"] in ("none", "rag_response")

def test_evaluator_calcula_metricas():
    """Evaluator com resultados mockados calcula métricas corretamente."""
    # 90% accuracy em 10 amostras
    results = [EvalResult(expected="polo", predicted="polo", ...) for _ in range(9)]
    results.append(EvalResult(expected="polo", predicted="none", ...))
    report = Evaluator._compute_from_results(results)
    assert abs(report.accuracy - 0.9) < 0.01

def test_confusion_matrix_shape():
    """Matriz de confusão tem shape correto para N intents."""
    ...

def test_dashboard_gera_html_valido():
    """dashboard.py gera HTML com as seções esperadas."""
    ...

def test_dataset_distribuicao_balanceada():
    """Nenhum intent tem menos de 9 amostras (evita métricas instáveis)."""
    ...
```

---

## S08-06 — Guia de interpretação para o cliente

Criar `docs/evaluation/INTERPRETING_METRICS.md`:

```markdown
# Como interpretar o relatório de desempenho do Camisart AI

## O que significa Accuracy de 94.5%?

Em 200 perguntas reais de clientes, o bot respondeu
corretamente 189. Apenas 11 precisariam de intervenção humana.

Para comparação:
- Um atendente humano treinado: ~97%
- Chatbot simples por palavras-chave: ~60-70%
- Nosso bot: 94.5% ← posicionamento premium

## O que é F1 Score e por que importa mais que Accuracy?

Accuracy pode ser enganosa. Um bot que sempre diz "não sei"
teria 50% de accuracy se metade das perguntas fossem
desconhecidas — mas seria inútil.

O F1 Score penaliza tanto os erros de comissão (responder
errado) quanto os de omissão (não responder quando devia).
F1 de 93% é um resultado profissional.

## O que é a Matriz de Confusão?

É um mapa dos erros. Cada linha é o que o cliente realmente
quis dizer. Cada coluna é o que o bot entendeu. A diagonal
são os acertos. Tudo fora da diagonal são erros — e o gráfico
mostra exatamente onde melhorar.

## O que fazer com esses números?

- F1 abaixo de 80% em um intent → adicionar variações no FAQ
- Fallback rate acima de 20% → expandir base de conhecimento
- Latência acima de 5s → revisar thresholds do LLM Router
```

---

## Ordem de Execução

```
S08-01 → S08-02 → S08-03 → S08-04 → S08-05 → S08-06
```

O dataset (S08-01) é a fundação — tudo depende dele.  
O evaluator (S08-02) precisa do dataset.  
O dashboard (S08-03) precisa do relatório do evaluator.  
A avaliação qualitativa (S08-04) é independente.  
Os testes (S08-05) acompanham cada item.  
O guia (S08-06) fecha o sprint.

---

## Dependências Python

```
# Adicionar ao requirements.txt
scikit-learn>=1.4    # métricas: precision, recall, F1, matriz de confusão
matplotlib>=3.8      # gráficos estáticos (fallback se Chart.js não disponível)
```

---

## Commits Atômicos Esperados

```
feat(evaluation): dataset.json rotulado 200 amostras [S08-01]
feat(scripts): evaluate.py — accuracy, F1, confusion matrix, latência [S08-02]
feat(scripts): dashboard.py — relatório HTML com gráficos Chart.js [S08-03]
feat(scripts): qualitative_eval.py — avaliação qualitativa 5 dimensões [S08-04]
test(evaluation): testes do pipeline de avaliação [S08-05]
docs(evaluation): guia de interpretação das métricas para o cliente [S08-06]
```

---

## Critérios de Aceite

- [ ] Dataset com 200 amostras cobrindo todos os intents
- [ ] Nenhum intent com menos de 9 amostras
- [ ] `evaluate.py` calcula accuracy, F1, precision, recall e matriz de confusão
- [ ] `evaluate.py --layer faq` filtra apenas amostras da Camada 1
- [ ] `evaluate.py --difficulty hard` filtra apenas casos difíceis
- [ ] `dashboard.py` gera HTML standalone abrível sem servidor
- [ ] Dashboard contém: cards de resumo, matriz de confusão, F1 por intent, distribuição por camada
- [ ] Relatório tem seção executiva em português para o cliente não-técnico
- [ ] `qualitative_eval.py` avalia 5 dimensões e gera score 0-100
- [ ] Guia de interpretação explica cada métrica sem jargão técnico
- [ ] 0 testes falhando
- [ ] CI verde na branch `sprint/08-metrics`
- [ ] `camisart-sprint-review` aprovado antes do merge

---

## Nota sobre os números esperados

Os valores do dataset são construídos para testar o bot em condições reais. Espera-se:

| Métrica | Meta mínima | Meta ideal |
|---------|------------|------------|
| Accuracy global | 85% | 95% |
| F1 macro | 82% | 93% |
| Fallback indevido | < 15% | < 5% |
| Latência FAQ | < 5ms | < 1ms |
| Score qualitativo | 75+ | 85+ |

Se alguma métrica ficar abaixo da meta mínima, o próprio relatório indica o caminho de melhoria — quais intents precisam de mais variações no FAQ, quais precisam de mais chunks no RAG.
