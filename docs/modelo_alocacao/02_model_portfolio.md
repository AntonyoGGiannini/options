# Etapa 2 — Definição de Model Portfolio

Define o **peso-alvo por categoria** (`AvenueCategoryId`) para cada perfil de
cliente. Os pesos são preenchidos no app
[All&In - Investimentos](https://allocation-intelligence-2846582141784626.gcp.databricksapps.com/)
(página *Model Portfolio*) e versionados temporalmente.

## `dim_model_portfolio`

Tabela dimensão **versionada (SCD por intervalo de datas)** a partir de
`research.model_portfolio`.

### Padrão de versionamento por datas

1. **`VW_DATES`** — monta os intervalos `[StartDate, EndDate]`:
   - inclui a linha-semente `1900-01-01` (default vigente "desde sempre");
   - une os `RefDate` distintos de `research.model_portfolio`;
   - `EndDate = LEAD(RefDate) - 1 dia`, com o último intervalo aberto em
     `9999-12-31`.
2. **`CTE_1900`** — preserva a versão `1900-01-01` da própria tabela atual
   (mantém o default já existente).
3. **`CTE_RESEARCH_RANK`** — para cada `RefDate`, rankeia por `MetadataIngestion DESC`
   e fica apenas com a ingestão mais recente (`RN = 1`) — dedupe de reenvios.
4. **`CTE_OUTROS`** — associa cada intervalo de `VW_DATES` (≠ 1900) à versão de
   research correspondente.
5. Resultado = `CTE_1900 UNION ALL CTE_OUTROS`.

> Padrão idêntico ao usado em `dim_ordem_produtos` e `dim_restricao_concentracao`.

### Colunas
`ModelPortfolioName`, `CodigoPerfil`, `AvenueCategoryId`, `Peso`,
`StartDate`, `EndDate`.

## `vw_model_portfolio_actual`

View final que entrega o model portfolio **vigente hoje** para as três
carteiras (Agregada, Expandida, Personalizada).

### Parte geral (Agregada / Expandida)

1. **`CTE_CLIENT_PROFILE`** — para cada cliente ativo (`fact_active_clients` no
   último `RefDate`), resolve o `CodigoPerfil`:
   - junta `dim_account` para obter `RiskTolerance`, `TimeHorizon`, `AvenueRiskProfile`;
   - mapeia `AvenueRiskProfile → CodigoPerfil` via `de_para_perfil`;
   - **override:** se `RiskTolerance = 'LOW'` e `TimeHorizon = 'SHORT'`, força `'P1'`.
2. **`CTE_MODEL_GERAL`** — junta o perfil do cliente a `dim_model_portfolio`
   pelo `CodigoPerfil`, filtrando a versão vigente
   (`CURRENT_DATE() BETWEEN StartDate AND EndDate`).

### Parte personalizada — `vw_model_portfolio_personalizado`

Lê a composição diretamente do **IPS** do cliente
(`ips.dim_ips`, `Parameter.ModelPortfolio`):

- **`CTE_IPS_DEDUP`** — mantém o IPS vigente por conta
  (`CURRENT_DATE() BETWEEN RegistryDate AND ExpirationDate`), com
  `ROW_NUMBER()` por `RegistryDate DESC, ConfirmationDate DESC` (`Rn = 1`).
- **`CTE_PORT_TESTE`** — explode `Parameter.ModelPortfolio.composition`
  (`MAP<STRING,STRING>`) em pares `AvenueCategoryId / Peso`; datas vêm de
  `ModelPortfolio.start` / `ModelPortfolio.end`.
- **`CTE_PORT`** — explode o objeto `Parameter.ModelPortfolio` direto; datas
  vêm de `RegistryDate` / `ExpirationDate`. Filtra apenas chaves que começam
  com `'AV'` (categorias válidas).
- `ModelPortfolioName = 'AvenuePersonalizada'`, `CodigoPerfil = IPSId`.

### Saída
`Date`, `AvenueAccountId`, `ModelPortfolioName`, `CodigoPerfil`,
`AvenueCategoryId`, `Peso`, `StartDate`, `EndDate`
(geral `UNION ALL` personalizado).
