# Etapa 1 — Definição de Produtos Recomendados

Define, **por mês**, quais produtos podem ser recomendados para as carteiras dos
clientes. Consolida as seleções de research de cada classe de ativo e anexa os
atributos do produto.

## A. `fact_produtos_recomendados`

Tabela final que une as recomendações de **Bonds, ETFs, Fundos, Stocks e UCITS**.

> Observação: no `INSERT` final, `STOCKS_RECOMENDADOS` está **comentado**
> intencionalmente — o modelo de alocação **não indica ações individuais**, então
> a tabela é populada apenas com Bonds, ETFs, Fundos e UCITS. A view de Stocks é
> mantida pronta caso essa decisão mude.

### Fonte por classe

Cada classe tem uma view temporária `*_RECOMENDADOS` construída a partir de
`avenue_intelligence_allocation.research.selecao_<classe>`:

| Classe  | Tabela de seleção        | Chave do produto | Join de atributos                          |
|---------|--------------------------|------------------|--------------------------------------------|
| Bonds   | `selecao_bonds`          | `ISIN`           | `dim_product.ISIN`                         |
| ETFs    | `selecao_etfs`           | `Ticker`         | `dim_product.Symbol`                       |
| Fundos  | `selecao_fundos`         | `ISIN`           | `dim_product.ISIN`                         |
| Stocks  | `selecao_stocks`         | `Ticker`         | — (sem join, sem `Product_N3`)             |
| UCITS   | `selecao_ucits`          | `ISIN`           | `dim_product.ISIN`                         |

### Lógica comum (idêntica em todas as classes)

1. **`CTE_DATA_CONSIDERADA`** — pega o último `DataFim <= CURRENT_DATE()` das
   seleções; é o ciclo de recomendação vigente.
2. **`CTE_DADOS`** — seleciona os produtos cuja janela `[DataInicio, DataFim]`
   contém a data considerada. `RefDate = D-1`. Faz `LEFT JOIN` em
   `dim_product` (`DimActiveFlag = 1`) para obter `Product_N3` (classe).
3. **Separação por período de classificação:**
   - `CTE_PONTUAL` — `ClassificacaoPeriodo = 'Campanha'` (recomendações pontuais).
   - `CTE_MENSAL` — `ClassificacaoPeriodo = 'Mensal'`, **excluindo** símbolos que
     já estão em campanha (campanha tem precedência sobre o mesmo símbolo).
4. **Repriorização mensal (`CTE_MENSAL_REPRIORIZADO`):** para cada produto
   mensal, conta quantas campanhas da mesma `ClassificacaoLista` têm
   `Prioridade <= ` à dele e soma esse total à prioridade. Isso **empurra os
   produtos mensais para baixo na fila**, abrindo espaço para as campanhas
   ocuparem suas posições sem colidir.
   ```
   PrioridadeFinal_mensal = Prioridade + COUNT(campanhas com prioridade <= a dele)
   ```
5. **União final:** mensais repriorizados `UNION ALL` campanhas (campanhas
   mantêm a `Prioridade` original intacta), ordenados por
   `ClassificacaoLista, Prioridade`.

### Carga da tabela

```sql
-- idempotente por dia:
DELETE FROM ...fact_produtos_recomendados WHERE Date = DATE_ADD(CURRENT_DATE(), -1);
INSERT INTO ...fact_produtos_recomendados
  SELECT ... FROM (BONDS UNION ALL ETFS UNION ALL FUNDOS UNION ALL UCITS);
```

### Schema de `fact_produtos_recomendados`

| Coluna             | Tipo   | Descrição                                   |
|--------------------|--------|---------------------------------------------|
| `Date`             | DATE   | Data de referência (D-1)                    |
| `DimTimeSK`        | STRING | Data de referência (yyyyMMdd)               |
| `Symbol`           | STRING | ISIN/Ticker do produto                      |
| `Product_N3`       | STRING | Classe do produto                           |
| `AvenueCategoryId` | STRING | Categoria do produto (era `Categoria`)      |
| `Prioridade`       | INT    | Ordem de prioridade dentro da lista         |
| `Descricao`        | STRING | Descrição (atualmente `NULL`)               |
| `SellingPoints`    | STRING | Selling points (atualmente `NULL`)          |
| `ClassificacaoLista`| STRING| Classificação da lista de recomendação      |
| `FlagCarteira`     | INT    | Flag de inclusão na carteira automática     |

## B. `vw_produtos_recomendados_atributos`

View que enriquece `fact_produtos_recomendados` (último `DimTimeSK`) com
atributos de produto vindos de `general.fact_product` (último `DimTimeSK`).

Join por `fact_product.Symbol = Symbol` **ou** `fact_product.bonds_isin = Symbol`.

Atributos derivados:

| Coluna             | Origem / regra                                                       |
|--------------------|----------------------------------------------------------------------|
| `gestora`          | `fundos_fund_group`                                                  |
| `duration`         | `bonds_duration`                                                    |
| `emissor`          | `bonds_name`                                                        |
| `setor`            | `bonds_sector`                                                      |
| `pais`             | `bonds_branch`                                                      |
| `renda`            | `1` se `Product_N3 ∈ {Stocks, Bonds, ETF's}`, senão `0`             |
| `liquidez`         | constante `'3'`                                                     |
| `aplicacao_minima` | Funds → `1000`; Bonds → `bonds_min_qty_trade × bonds_bid_price`; UCITs → `250`; default → `250` |
| `bonds_is_public`      | `bonds_is_public`                                              |
| `bonds_rating_avenue`  | `bonds_rating_avenue`                                          |
| `bonds_duration_avenue`| `bonds_duration_avenue`                                        |

> `aplicacao_minima` de Funds está fixada em `1000` como contorno: o campo real
> (`fundos_minimum_initial_subscription_amount`) está com **erro na ingestão**.
> Quando a ingestão for corrigida, basta trocar pela coluna comentada.
