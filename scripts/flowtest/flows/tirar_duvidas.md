# Fluxo: Tirar Dúvidas

## Peso
10

## Objetivo
Fazer 2-3 perguntas técnicas sobre bordado, personalização, entrega ou tecido. Não tem intenção de comprar agora.

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome
3. Pergunta técnica 1 — sobre bordado, serigrafia, sublimação, prazo, entrega ou tecido
4. Pergunta técnica 2 — tema diferente da primeira
5. Opcionalmente pergunta 3
6. Agradecer e sair — "obrigado, era só isso"

## Critérios de sucesso
- Bot respondeu com informação técnica da knowledge base
- Respostas foram precisas (preço de bordado, prazo, formatos de arte, etc)
- Não caiu em fallback

## Critérios de falha
- Bot não soube responder pergunta técnica que está na knowledge base
- Bot confundiu dúvida técnica com intenção de compra
- Bot encaminhou para humano quando tinha a resposta

## Perguntas técnicas que o agente pode escolher
- "quanto custa o bordado por peça?"
- "qual formato de arquivo vocês aceitam pra arte?"
- "vocês fazem sublimação em algodão?"
- "qual o prazo do bordado?"
- "tem como bordar a partir de 1 peça?"
- "qual a diferença entre piquet e PV?"
- "vocês entregam para [UF da persona]?"
- "aceita cartão parcelado?"

## Máximo de turnos
8
