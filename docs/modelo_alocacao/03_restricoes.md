# Etapa 3 — Definição de Restrições

Define o que **não pode** entrar na carteira do cliente e os **limites de
concentração**. Há três famílias de restrição, com origens distintas:

| Restrição     | Origem                          | View `*_actual`                       |
|---------------|---------------------------------|---------------------------------------|
| Produtos      | IPS                             | `vw_restricao_produtos_actual`        |
| Atributos     | IPS + política                  | `vw_restricao_atributos_actual`       |
| Concentração  | política                        | `vw_restricao_concentracao_actual`    |

## 1. `vw_restricao_produtos_actual` — Restrição de Produtos (IPS)

Marca, por conta, quais combinações de `Categoria × Product_N3` estão
**permitidas ou bloqueadas** (`FlagRestricao`), a partir de
`Parameter.Restricao_Produtos` no IPS.

Etapas:
1. **`CTE_DATAS_LIMITE`** — coleta todas as datas-limite (`RegistryDate` e
   `ExpirationDate`) dos IPS que possuem `Restricao_Produtos`.
2. **`CTE_INTERVALOS`** — monta intervalos `[StartDate, EndDate]` por conta com
   `LEAD(DataLimite) - 1 dia`.
3. **`CTE_INTERVALOS_PRIORIDADE`** — para cada intervalo, escolhe o IPS aplicável
   resolvendo conflitos com `QUALIFY ROW_NUMBER()`:
   - prioridade por `Horizon`: `Pontual` (1) > `Permanente` (2) > demais (3);
   - desempate por `RegistryDate DESC`.
4. **`CTE_RESTRICOES`** — explode o `MAP<STRING,INT>` de `Restricao_Produtos`.
   A chave traz `<Restricao>_<Product_N3>`; via regex separa o sufixo de classe
   (`Bonds|ETFs|Funds|Stocks|UCITS|UCITs`) em `Product_N3` e o restante em
   `Restricao`. `value` → `FlagRestricao`.
5. Saída agregada com `MIN(FlagRestricao)` por
   `AvenueAccountId, Product_N3, Restricao`, filtrando o intervalo vigente.

> Semântica do flag: `1` = permitido; o consumo a jusante (R1) usa
> `COALESCE(FlagRestricao, 1) = 1` — ou seja, ausência de restrição = permitido.

## 2. `vw_restricao_atributos_actual` — Restrição de Atributos (IPS + política)

Restrições do tipo `Atributo Operador Valor` (ex.: `duration <= 5`).

### Parte política (`CTE_RESTRICAO_GERAL`)
Derivada de `dim_account` (ativa, `CanTrade = 'Can Trade'`):
- `LiquidityNeeds = 'VERY_IMPORTANT'` → `liquidez <= 5`;
- `InvestmentObjective = 'INCOME'` → `renda = 1`.

### Parte IPS — `vw_restricao_atributos_personalizado`
Explode `Parameter.Restricao_Atributos`
(`ARRAY<STRUCT<atributo, operador, valor>>`) dos IPS vigentes.

Saída = política `UNION ALL` IPS, ambas filtradas pela vigência
(`CURRENT_DATE() BETWEEN StartDate AND EndDate`).

Colunas: `AvenueAccountId`, `Atributo`, `Operador`, `Valor`,
`StartDate`, `EndDate`.

## 3. Restrição de Concentração (política)

### `dim_restricao_concentracao`
Tabela versionada por datas a partir de `research.restricao_concentracao`,
usando o **mesmo padrão SCD** de `dim_model_portfolio` (linha-semente
`1900-01-01` + `RANK()` por `MetadataIngestion DESC`).

Define o `Limite` (fração do patrimônio) por combinação de:
`Product_N3`, `RatingAvenue`, `DurationAvenue`, `EmissorPublico`.

### `vw_restricao_concentracao_actual`
Simplesmente filtra `dim_restricao_concentracao` pela vigência
(`CURRENT_DATE() BETWEEN StartDate AND EndDate`).
