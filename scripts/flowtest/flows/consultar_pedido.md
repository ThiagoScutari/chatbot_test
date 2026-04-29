# Fluxo: Consultar Pedido

## Peso
10

## Objetivo
Perguntar sobre status de pedido existente. O bot não tem tracking — sucesso é encaminhar para humano corretamente.

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome
3. Perguntar sobre pedido — "meu pedido tá pronto?" / "fiz um pedido semana passada" / "quero saber do meu bordado"
4. Bot encaminha para humano ou informa que não tem tracking
5. Reagir à resposta do bot

## Critérios de sucesso
- Bot reconheceu que é sobre pedido existente
- Bot encaminhou para atendente humano (handoff correto)
- Tom empático/profissional

## Critérios de falha
- Bot tentou iniciar orçamento novo
- Bot deu fallback sem direcionar
- Bot fingiu ter informação de tracking que não tem

## Variações que o agente PODE fazer
- Informar número de pedido inventado ("pedido 4532")
- Perguntar prazo de entrega do pedido
- Ficar insatisfeito se bot não souber informar

## Máximo de turnos
6
