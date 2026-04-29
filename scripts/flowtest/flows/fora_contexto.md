# Fluxo: Fora de Contexto

## Peso
5

## Objetivo
Mandar mensagens irrelevantes ou confusas. Bot deve recusar educadamente e redirecionar.

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome
3. Mensagem fora de contexto — assunto que nada tem a ver com uniformes
4. Bot recusa educadamente e redireciona
5. Opcionalmente insistir ou mudar para assunto relevante

## Critérios de sucesso
- Bot não respondeu como se fosse assunto válido
- Bot redirecionou para o menu/produtos
- Bot não ficou confuso nem travou

## Critérios de falha
- Bot tentou responder pergunta irrelevante
- Bot travou ou deu erro
- Bot iniciou fluxo de orçamento com assunto irrelevante

## Mensagens que o agente pode usar (escolher aleatoriamente)
- "qual o placar do jogo de ontem?"
- "me indica um restaurante bom"
- "oi sumida kkk"
- "to entediado"
- "quanto ta o dolar?"
- "me conta uma piada"
- "vc é um robo?"
- "qual teu nome?"

## Variações que o agente PODE fazer
- Insistir no assunto irrelevante por 2 turnos
- Depois de recusado, mudar para pergunta legítima ("ta bom, me fala o preco da polo")

## Máximo de turnos
5
