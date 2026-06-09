# Etapa 4 — Definição de Produtos por Cliente (views *enabled*)

Cruza model portfolio × produtos recomendados e aplica, **em cadeia**, todas as
restrições da Etapa 3, terminando com a ordenação de prioridade. Cada view
consome a anterior:

```
vw_enabled_product_client            (base: model portfolio × recomendados+atributos)
  └─ vw_enabled_product_client_r1    + restrição de PRODUTOS
       └─ vw_enabled_product_client_r2    + restrição de ATRIBUTOS
            └─ vw_enabled_product_client_r3    + restrição de CONCENTRAÇÃO (Limite)
                 └─ vw_enabled_product_client_r4    + ORDEM dos produtos (PrioridadeFinal)
                      └─ enabled_product_client_r4  (snapshot histórico)
```

## A. Ordem dos Produtos

### `dim_ordem_produtos`
Tabela versionada (mesmo padrão SCD `1900-01-01` + `RANK()` por
`MetadataIngestion DESC`) a partir de `research.ordem_produtos`. Define a
`Ordem` de cada `AvenueCategoryId` dentro de seu `Product_N3`, preenchida no app
(página *Ordem Produtos*).

### `vw_ordem_produtos_actual`
Filtra `dim_ordem_produtos` pela vigência (`CURRENT_DATE() BETWEEN StartDate AND EndDate`).

## Base — `vw_enabled_product_client` (Model Portfolio)

Junta a carteira-alvo do cliente com os produtos recomendados + atributos:

- `vw_model_portfolio_actual` (último `Date`, `Peso > 0`)
- `⋈ vw_produtos_recomendados_atributos` (último `Date`) por `AvenueCategoryId = Categoria`

Carrega para frente os atributos essenciais: `gestora`, `duration`,
`aplicacao_minima`, `bonds_duration_avenue`, `bonds_is_public`,
`bonds_rating_avenue`, `emissor`, `setor`, `pais`, `renda`, `liquidez`,
além de `Symbol`, `Product_N3`, `Prioridade`, `CodigoPerfil`, `ModelPortfolioName`.

## R1 — `vw_enabled_product_client_r1` (Restrição de Produtos)

`LEFT JOIN vw_restricao_produtos_actual` por
`AvenueAccountId + Restricao = Categoria + Product_N3`, mantendo apenas
`COALESCE(FlagRestricao, 1) = 1` (sem restrição = permitido).

> A query anterior (ativa até 29/05) está preservada comentada no notebook: ela
> só aplicava o filtro quando existia *alguma* restrição para a conta, caindo em
> `COALESCE(FlagRestricao, 0)` caso contrário. A versão atual é mais simples e
> permissiva por default.

## R2 — `vw_enabled_product_client_r2` (Restrição de Atributos)

Mantém de `_r1` apenas as linhas que **não violam nenhuma** restrição de atributo
(`WHERE NOT EXISTS (... viola ...)`). A avaliação é feita por atributo:

- **`duration`** (numérico): operadores `>`, `<`, `>=`, `<=`, `=`, `<>`.
- **`gestora`, `setor`, `emissor`** (textuais): operadores `=`, `<>`.

Regras de robustez:
- atributo `NULL` no produto → não filtra (não há como violar);
- operador desconhecido → `TRUE` (lenient, não filtra);
- a violação só "derruba" a linha quando o atributo existe **e** a condição
  da restrição não é satisfeita.

## R3 — `vw_enabled_product_client_r3` (Restrição de Concentração)

Anexa o `Limite` de `vw_restricao_concentracao_actual` e mantém só produtos com
`Limite > 0`. O join difere por classe:

- **Bonds:** join por `Product_N3 + bonds_rating_avenue + bonds_duration_avenue
  + bonds_is_public` (limite granular por rating/duração/emissor público).
- **Demais:** join apenas por `Product_N3`.

Resultado = `CTE_BONDS UNION ALL CTE_OUTROS`.

## R4 — `vw_enabled_product_client_r4` (Ordem dos Produtos)

Junta `_r3` com `vw_ordem_produtos_actual` (`AvenueCategoryId + Product_N3`) e
calcula a **prioridade final** combinando dois critérios:

```
PrioridadeFinal = Ordem * 100 + Prioridade
```

- **1º critério** — `Ordem` por `Product_N3`/categoria (peso 100);
- **2º critério** — `Prioridade` do produto na recomendação mensal (desempate).

Saída ordenada por `Categoria, PrioridadeFinal`, carregando `aplicacao_minima`
e `Limite` (insumos do otimizador). Inclui `SELECT DISTINCT` para evitar
duplicidades do join.

> O notebook traz queries auxiliares de inspeção (filtro por um
> `AvenueAccountId` exemplo, posição de custódia, model portfolio personalizado
> e checagem de símbolos nulos em `fact_product`) — são de diagnóstico, não
> fazem parte da view.

## Registro histórico — `enabled_product_client_r4`

Após aplicar todas as restrições, grava um snapshot da base final em
`avenue_intelligence_allocation.alocacao.enabled_product_client_r4`,
acrescentando `IngestionDate = CURRENT_TIMESTAMP()`, para manter o histórico
das versões diárias.

```sql
INSERT INTO ...alocacao.enabled_product_client_r4
SELECT *, CURRENT_TIMESTAMP() AS IngestionDate
FROM ...modelo_alocacao.vw_enabled_product_client_r4;
```
