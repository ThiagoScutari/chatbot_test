# Fluxo: Consultar Produtos

## Peso
20

## Objetivo
Perguntar sobre preços e características de produtos sem comprar. O cliente está pesquisando.

## Etapas esperadas
1. /start — bot saúda e pede nome
2. Fornecer nome
3. Perguntar preço de um produto — "quanto custa a polo?" / "qual valor do jaleco?"
4. Perguntar sobre outro produto — comparar
5. Perguntar sobre tecido/qualidade — "qual tecido?" / "é boa a qualidade?"
6. Encerrar sem comprar — "vou pensar" / "obrigado por enquanto"

## Critérios de sucesso
- Bot respondeu perguntas de preço corretamente
- Bot forneceu informações sobre tecido/qualidade
- Conversa encerrou naturalmente sem forçar venda

## Critérios de falha
- Bot não soube informar preço de algum produto
- Bot deu fallback em pergunta legítima sobre produto
- Bot forçou fluxo de orçamento quando cliente não queria

## Variações que o agente PODE fazer
- Perguntar sobre produto que não existe ("vocês fazem calça?")
- Comparar dois produtos ("polo ou básica, qual melhor pra uniforme?")
- Perguntar sobre tamanhos disponíveis

## Máximo de turnos
10
