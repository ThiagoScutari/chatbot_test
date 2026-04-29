# Fluxo: Solicitar Catálogo

## Peso
10

## Objetivo
Pedir para ver os produtos/catálogo da loja. Pode ser direto ou após breve conversa.

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome
3. Pedir catálogo — "quero ver o catálogo" / "tem fotos dos produtos?" / "me manda os modelos"
4. Receber catálogo ou resposta sobre catálogo
5. Opcionalmente perguntar algo sobre o catálogo
6. Encerrar — "vou dar uma olhada, obrigado"

## Critérios de sucesso
- Bot enviou catálogo ou direcionou corretamente
- Conversa foi curta e objetiva

## Critérios de falha
- Bot não entendeu pedido de catálogo
- Bot pediu nome de novo após já ter coletado
- Bot ignorou pedido e foi para outro fluxo

## Variações que o agente PODE fazer
- Pedir catálogo logo na primeira mensagem junto com o nome
- Usar termos alternativos: "fotos", "modelos", "o que vocês tem"
- Após ver catálogo, perguntar preço de algo específico

## Máximo de turnos
5
