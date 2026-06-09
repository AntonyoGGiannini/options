# Etapa 5 — Otimizador

Notebook Python (PySpark + pandas/numpy) que, dado um cliente, sua carteira-alvo
(model portfolio), a posição atual e o caixa disponível, decide **quanto comprar
de cada categoria** e **quais produtos comprar**. É a etapa final que converte o
modelo numa ordem de compra executável.

## Parâmetros de entrada

```python
AvenueAccountId    = '...'              # cliente
ModelPortfolioName = 'AvenueExpandida'  # Agregada | Expandida | Personalizada
Rebalanceamento    = 0                  # flag (reservado)
CaixaAdicional     = 100000             # aporte a alocar além do caixa atual
```

## Insumos (queries Spark)

| Variável             | Fonte                                                        |
|----------------------|--------------------------------------------------------------|
| `posicao_atual`      | `fact_custody` × `dim_product` × `general.fact_product` (último `Date`, exclui `Balance US Banking`) |
| `posicao_atual_agg`  | `posicao_atual` agregada por `AvenueCategoryId` (exclui `Balance US Clearing`) |
| `caixa`              | soma de `TotalNetDol` em `Balance US Clearing`               |
| `model_portfolio`    | `vw_model_portfolio_actual` (conta + `ModelPortfolioName`)   |
| `produtos_disponiveis`| `vw_enabled_product_client_r4` (conta + `ModelPortfolioName`)|
| `produtos`           | catálogo (`general.fact_product` × `dim_product_categoria`) p/ enriquecer o resultado (taxas, setor, YTW, spread) |

## 1. `otimizador_caixa()` — alocação de caixa por categoria (water-filling)

Distribui o caixa total (`CaixaAdicional + caixa`) entre as categorias para
**maximizar a aderência** ao model portfolio, sem vender (compra apenas).

Passos:
1. **Merge** model portfolio × posição agregada (`outer`, preenchendo zeros).
2. **Patrimônio total** = `posição + caixa`; `peso_recomendado = Peso / ΣPeso`;
   `valor_recomendado = peso_recomendado × patrimônio`.
3. **Gap por categoria** = `max(valor_recomendado − valor_atual, 0)` (só
   subponderadas).
4. **Water-filling vetorizado:**
   - se `Σgap ≤ caixa` → cobre todos os gaps integralmente;
   - senão → calcula o **nível residual** `L*` (ordenando gaps desc,
     `L_k = (cumsum − caixa)/k`, achando o `k*` em que `L_k ≥` próximo gap) e
     aloca `compra = max(gap − L*, 0)`. Equipara as categorias mais
     subponderadas até o caixa acabar.
5. **Derivadas** pós-alocação: `valor_depois`, pesos antes/depois, aderência
   antes/depois (`min(valor, recomendado)/patrimônio`).
6. **Tabela final** com linhas especiais `Caixa` (mostra caixa usado/residual)
   e `TOTAL`.

Saída: `categorias_gap` = categorias com `CompraVenda > 0`.

> Restrição-chave: o otimizador **nunca vende** — só preenche gaps positivos.
> Sobras de caixa após cobrir todos os gaps ficam como `caixa_residual`.

## 2. `alocar_produtos()` — distribuição do delta entre produtos

Dado o `CompraVenda` por categoria, distribui o valor entre os produtos
elegíveis da categoria, na ordem de `PrioridadeFinal`, respeitando
**aplicação mínima** e **teto de concentração** (`Limite × patrimônio`),
descontando a **posição atual** do cliente em cada símbolo.

Regras:
- Para cada produto: `espaco = max(Limite×total − posição_atual, 0)`. Pula se
  `espaco ≤ 0`, se `espaco < aplicacao_minima`, ou se o restante a alocar
  `< aplicacao_minima`. Aloca `min(restante, espaco)`.
- **Categoria de sobra `AV1010`:** qualquer resíduo que não couber na categoria
  de origem é redirecionado para `AV1010`, processada por último com verba
  própria + sobras acumuladas.
- **Alocação forçada:** se, mesmo em `AV1010`, sobrar valor, força no produto de
  maior prioridade da `AV1010` **ignorando o teto** (consolida em linha
  existente se houver). Status `ALOCADO_FORCADO`.
- Sem produtos na categoria → linha de rastreio `SOBRA_CATEGORIA`.

Status possíveis: `ALOCADO`, `ALOCADO_FORCADO`, `SOBRA_CATEGORIA`.

Saída: `Categoria, Product_N3, Symbol, PrioridadeFinal, ValorAlocado,
PesoPortfolio, Status`.

## Resultado final

`resultado` (saída de `alocar_produtos`) é cruzado com o catálogo `produtos`
por `Symbol` para anexar `NomeCategoria`, níveis de categoria, `ProductName`,
`Taxas`, `Setor`, `YTW` e `SpreadBonds` — a ordem de compra final, enriquecida
para apresentação.
