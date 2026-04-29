# Fluxo: Compra

## Peso
40

## Objetivo
Completar o fluxo de orçamento: desde a saudação até a confirmação do lead com todos os campos preenchidos (segmento, produto, quantidade, personalização, prazo).

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome — bot confirma e pergunta como pode ajudar
3. Expressar intenção de compra — "quero comprar uniformes" / "preciso de polo pro meu pessoal"
4. Responder segmento — quando bot perguntar (corporativo/saúde/educação/etc)
5. Escolher produto — quando bot perguntar qual produto
6. Informar quantidade — quando bot perguntar quantas peças
7. Escolher personalização — bordado/serigrafia/sem
8. Informar prazo — quando bot perguntar quando precisa
9. Confirmar orçamento — quando bot mostrar resumo

## Critérios de sucesso
- Bot capturou lead com todos os campos
- Conversa fluiu sem fallback ou resposta genérica
- Cliente não ficou preso em loop

## Critérios de falha
- Bot entrou em loop pedindo mesma informação
- Bot deu fallback (não entendi) em mais de 1 turno
- Bot não iniciou fluxo de orçamento após intenção de compra
- Conversa atingiu max_turns sem completar

## Variações que o agente PODE fazer (escolher aleatoriamente)
- Perguntar preço ANTES de entrar no fluxo de orçamento
- Pedir desconto por quantidade
- Mudar de produto no meio ("ah, na verdade quero jaleco")
- Perguntar sobre bordado durante a coleta

## Máximo de turnos
15
