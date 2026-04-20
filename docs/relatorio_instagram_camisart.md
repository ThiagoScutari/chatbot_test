# Relatório de Análise Instagram @camisart_belem
## Oportunidades de Evolução do Chatbot

**Data:** 2026-04-19  
**Fonte:** 190 posts extraídos (2020–2026) + 427 comentários de 180 posts  
**Perfil:** [@camisart_belem](https://www.instagram.com/camisart_belem/) — Malharia e uniformes, Belém–PA

---

## 1. Perfil do Negócio

A partir das legendas e comentários, foi possível mapear completamente o negócio:

| Dado | Valor |
|---|---|
| Endereço | Av. Magalhães Barata, 445 — nos altos da Só Modas |
| WhatsApp | (91) 99180-0637 |
| Entrega | Nacional (📦 Entregamos para todo o Brasil) |
| Prazo bordado | 5 dias úteis |
| Pedido mínimo bordado | Nenhum |
| Pedido mínimo serigrafia | 40 unidades |

---

## 2. Catálogo de Produtos Identificados

| Produto | Tecido | Preço aprox. | Observações |
|---|---|---|---|
| Camisa Polo | Malha Piquet | R$ 42–50/un | Atacado (12+): R$ 42 |
| Camisa Básica Algodão | 100% Algodão | A partir de R$ 29 | P, M, G |
| Camisa Básica PV | Poliéster + Viscose | — | Recomendada para sublimação |
| Regata | 100% Algodão | R$ 20 | Masculina e feminina |
| Jaleco Tradicional | Gabardine | R$ 120 | Saúde (odonto, medicina, estética) |
| Jaleco Premium | Gabardine | R$ 145 | Amarração em laço + botões |
| Uniforme Doméstica | UniOffice Camisaria | R$ 120 | Babás, faxineiras, cuidadoras |
| Blusa COP30 / Pará | 100% Algodão | R$ 40 | Edição especial |
| Ecobag Pará | — | R$ 40–45 | |
| Polo do Brasil | Malha Piquet | R$ 50 | Bordado premium |
| Bordado de Logo | — | Variável | Sem pedido mínimo |
| Serigrafia | — | — | Mín. 40 unidades |
| Sublimação | Malha PV | — | Necessita camisa PV |

**Segmentos atendidos:** uniformes corporativos, saúde (jaleco), domésticas, varejo, indústria, agronegócio, educação, gastronomia, esportes amadores, igrejas/grupos religiosos, edições temáticas (Círio, COP30, Copa do Mundo).

---

## 3. O Que os Comentários Revelam

**Total analisado:** 427 comentários em 180 posts

| Categoria | Comentários | % |
|---|---|---|
| **Perguntas de preço** | 164 | **38,4%** |
| Elogios | 32 | 7,5% |
| Bordado / logo | 30 | 7,0% |
| Cores disponíveis | 20 | 4,7% |
| Disponibilidade / estoque | 16 | 3,7% |
| Contato / WhatsApp | 16 | 3,7% |
| Tamanhos | 11 | 2,6% |
| Entrega | 8 | 1,9% |
| Pedido mínimo | 6 | 1,4% |
| Infantil | 5 | 1,2% |
| Orçamento | 3 | 0,7% |
| Reclamações | 3 | 0,7% |
| Atacado | 2 | 0,5% |

### Insight Principal

**Mais de 1 em cada 3 comentários é uma pergunta de preço** — e essa pergunta raramente é respondida publicamente. O cliente pergunta, a loja não responde no Instagram, e o potencial comprador some. Um chatbot com tabela de preços resolve isso instantaneamente.

### Reclamações (pequenas mas relevantes)

Três clientes reclamaram especificamente do canal WhatsApp:
- *"O que acontece com o atendimento pelo WhatsApp é desrespeitoso! Ficamos horas esperando um atendimento"*
- *"Só falta melhorar o atendimento no WhatsApp! Demora demais pra retornar."*
- *"QUE HOUVE COM NÚMERO DO WHATSAPP? TELEFONE SÓ DÁ CAIXA POSTAL. Ninguém responde msg no Instagram. Meu pedido está..."*

**Conclusão:** O gargalo atual é o atendimento humano. O chatbot não é um "extra" — é uma necessidade operacional.

---

## 4. Oportunidades de Evolução do Chatbot

### 4.1 FAQ Automático de Preços (Prioridade: CRÍTICA)

**Problema:** 38,4% das interações são perguntas de preço repetitivas.  
**Solução:** Módulo de consulta de preços por produto, com respostas instantâneas.

Exemplos de perguntas que o chatbot responderia automaticamente:

- "Quanto custa uma polo?" → R$ 45 (varejo) / R$ 42 (atacado, 12+ peças)
- "Qual o valor do jaleco?" → Jaleco Tradicional R$ 120 / Premium R$ 145
- "Qual o preço das básicas de algodão?" → A partir de R$ 29 (P, M, G)
- "Quanto custa o bordado?" → Variável conforme a logo; sem pedido mínimo

**Fluxo sugerido:**
```
CONSULTA_PRECOS
├── Polo
├── Básica Algodão / PV
├── Jaleco
├── Regata
├── Uniforme Doméstica
├── Bordado
└── Serigrafia
```

---

### 4.2 Catálogo Interativo por Segmento (Prioridade: ALTA)

Os posts mostram segmentos claramente distintos — e pesquisa de mercado aponta setores de alto potencial ainda pouco explorados. Em vez de um catálogo PDF genérico, o chatbot pode apresentar catálogos por nicho:

| Segmento | Produtos-chave | Potencial |
|---|---|---|
| Empresa / Uniforme Corporativo | Polo + bordado da logo | Alto |
| Saúde (odonto, medicina, estética) | Jaleco Tradicional, Jaleco Premium | Alto |
| Doméstica / Cuidadora | Uniforme UniOffice | Médio |
| Atacado / Revenda | Básicas algodão, polo (preço especial 12+ peças) | Alto |
| Varejo / Pessoal | Polo, básicas, edições especiais | Médio |
| **Indústria** | Polo e básica PV (sublimação), bordado de logo corporativo | **Muito Alto** |
| **Agronegócio** | Polo durável, básica algodão, personalização de cooperativas | **Muito Alto** |
| Educação | Polo e básica para uniformes escolares (início de ano letivo) | Alto |
| Gastronomia / Food Service | Polo com logo, básica para cozinha, delivery | Médio |
| Igrejas e grupos religiosos | Camisetas de retiro, coral, grupos de jovens (lotes) | Médio |
| Esportes amadores | Polo/básica para times de futebol society, academias | Médio |

> **Indústria:** Segmento de volume elevado e pedidos recorrentes. Fábricas, logística e construção civil demandam uniformes em larga escala com bordado ou serigrafia da logo corporativa. Ticket médio alto, ciclos de renovação previsíveis.

> **Agronegócio:** O Agro representa ~25% do PIB brasileiro. Cooperativas, fazendas e empresas do setor compram uniformes para equipes de campo e escritório. Alta concentração no PA/Norte e Centro-Oeste. Oportunidade de vendas via WhatsApp e entrega nacional.

**Fluxo sugerido:**
```
MENU
├── "Quero uniforme para minha empresa"   → catálogo_corporativo.pdf
├── "Sou da indústria / logística"        → catálogo_industria.pdf
├── "Sou do agronegócio"                  → catálogo_agro.pdf
├── "Sou profissional de saúde"           → catálogo_saude.pdf
├── "É para escola / educação"            → catálogo_educacao.pdf
├── "Restaurante / food service"          → catálogo_gastronomia.pdf
├── "Grupo / igreja / esporte"            → catálogo_grupos.pdf
├── "Preciso para uso pessoal"            → catálogo_varejo.pdf
└── "Quero comprar no atacado"            → informações_atacado
```

---

### 4.3 Consultor de Bordado (Prioridade: ALTA)

O bordado é o segundo tema mais questionado (7% dos comentários). As dúvidas são sempre as mesmas:

- Faz bordado em peça que não comprei aqui?
- Qual o valor do bordado?
- Qual o prazo?
- Tem pedido mínimo?

**Respostas padronizadas que o chatbot pode fornecer:**
- Prazo: 5 dias úteis
- Pedido mínimo bordado: nenhum
- Preço: depende da logo (encaminhar para orçamento via WhatsApp)
- Aceita peças de terceiros: verificar com atendente

**Fluxo sugerido:**
```
BORDADO
├── "Quero bordar peça comprada aqui"     → prazo + redirecionar WhatsApp
├── "Tenho peça de outro lugar"           → informar política
└── "Quero saber o valor"                 → solicitar foto da logo via WhatsApp
```

---

### 4.4 Consulta de Disponibilidade por Cor e Tamanho (Prioridade: MÉDIA)

Comentários como *"Tem a cor verde?"*, *"Tem tamanho PP?"*, *"Ainda tem esse modelo?"* são frequentes. Com um estoque integrado ou um cardápio fixo de cores por produto, o chatbot pode responder:

- Cores disponíveis por produto (paleta fixa que raramente muda)
- Tamanhos disponíveis (PP ao GG, infantil)
- Se o produto é "pronta entrega" ou sob encomenda

---

### 4.5 Geração de Orçamento Estruturado (Prioridade: MÉDIA)

Vários clientes pedem orçamento para lotes. O chatbot pode coletar os dados e gerar um resumo para o atendente humano:

```
ORCAMENTO
├── Tipo de peça
├── Quantidade
├── Personalização (bordado / serigrafia / nenhuma)
├── Prazo desejado
└── → "Obrigado! Enviando para nosso time. Responderemos em até 2h no WhatsApp."
```

Isso substitui o atendente na fase de coleta de dados, agilizando o atendimento.

---

### 4.6 Triagem de Atendimento (Prioridade: MÉDIA)

Dado o gargalo atual no WhatsApp, o chatbot pode triagens antes de escalar para humano:

```
TRIAGEM
├── Perguntas de preço               → resposta automática
├── Disponibilidade de produto       → resposta automática
├── Orçamento de uniformes           → coleta dados → fila humano
├── Reclamação / problema de pedido  → prioridade humano
└── Bordado / serigrafia             → coleta briefing → fila humano
```

---

### 4.7 Catálogo Sazonal — Copa do Mundo (Prioridade: ALTA)

Estamos em ano de Copa do Mundo — um dos maiores eventos de consumo de vestuário do Brasil. A Camisart tem histórico com edições especiais (já lançou "Polo do Brasil" e "Blusa COP30") e pode capitalizar com:

- **Catálogo Copa**: polo do Brasil, camisetas personalizáveis com número e nome, verde-amarelo
- **Uniforme para bares e restaurantes**: estabelecimentos que vão transmitir jogos compram uniformes para equipe — intersecção Copa + Gastronomia
- **Times de amigos / grupos**: pedidos de 10–30 peças com bordado ou serigrafia de nome do grupo
- **Cooperativas e empresas do Agro**: presentes institucionais Copa para colaboradores

> Janela de oportunidade: **maio–julho 2026**. Um fluxo dedicado no chatbot ("Quero algo da Copa") com catálogo específico pode capturar demanda que hoje se perde sem resposta.

**Fluxo sugerido:**
```
COPA_2026
├── "Camisa do Brasil personalizada"     → catálogo_copa.pdf + orçamento
├── "Uniforme para bar/restaurante"      → catálogo_gastronomia_copa.pdf
├── "Camisas para meu grupo de amigos"  → fluxo_orçamento (qtd + personalização)
└── "Presente institucional"             → contato comercial WhatsApp
```

---

### 4.8 Notificações de Lançamentos e Promoções (Prioridade: BAIXA)

Os posts mostram lançamentos sazonais frequentes: Círio de Nazaré, COP30, Copa do Mundo, promoções. Um chatbot no Telegram/WhatsApp pode:

- Enviar notificação quando chegam novos produtos
- Avisar sobre promoções de atacado
- Comunicar feriados/fechamentos (como o post do Tiradentes)

---

## 5. Base de Conhecimento Sugerida

A partir dos dados extraídos, esta é a estrutura de knowledge base recomendada para o chatbot:

```
base_conhecimento/
├── produtos/
│   ├── polo.json          (preços, tecidos, tamanhos, cores)
│   ├── basicas.json       (algodão, PV, preços)
│   ├── jaleco.json        (tradicional, premium, preços)
│   ├── uniforme_domestica.json
│   └── edicoes_especiais.json (Círio, COP30, Copa)
├── servicos/
│   ├── bordado.json       (prazo, pedido min, como solicitar)
│   └── serigrafia.json    (pedido min 40 un, como solicitar)
├── faq/
│   ├── precos.json
│   ├── tamanhos.json
│   ├── entrega.json
│   └── atacado.json
└── loja/
    └── info.json          (endereço, WhatsApp, horários)
```

---

## 6. Roadmap Proposto

| Fase | Feature | Impacto | Esforço |
|---|---|---|---|
| 1 | FAQ de preços por produto | Crítico | Baixo |
| 1 | Info da loja (endereço, horário, WhatsApp) | Alto | Baixo |
| 2 | Catálogo por segmento: corporativo, saúde, doméstica, varejo | Alto | Médio |
| 2 | **Catálogo Indústria e Agronegócio** | **Muito Alto** | Médio |
| 2 | **Catálogo Copa do Mundo 2026** (janela mai–jul) | **Alto** | Baixo |
| 2 | Consultor de bordado (FAQ + briefing) | Alto | Médio |
| 3 | Catálogos: Educação, Gastronomia, Grupos/Igrejas/Esportes | Médio | Médio |
| 3 | Gerador de orçamento estruturado | Médio | Médio |
| 3 | Consulta de cores e tamanhos disponíveis | Médio | Médio |
| 4 | Triagem inteligente → fila humano | Médio | Alto |
| 4 | Notificações de lançamentos e promoções sazonais | Baixo | Alto |

---

## 7. Próximo Passo: `project_specs.md`

Com base neste relatório, o `project_specs.md` deve definir:

1. **FAQ Engine** — estrutura JSON de perguntas/respostas + matching por intenção
2. **Produto DB** — lista de produtos com preços, tecidos, tamanhos, cores
3. **Fluxo de Orçamento** — coleta de dados estruturados para uniformes corporativos
4. **Integração WhatsApp Business API** — para substituir/complementar o Telegram
5. **Catálogos PDF por segmento** — usando as imagens já baixadas dos posts

---

*Relatório gerado automaticamente a partir de 190 posts e 427 comentários extraídos via `extrair_perfil.py` e `extrair_comentarios.py`.*
