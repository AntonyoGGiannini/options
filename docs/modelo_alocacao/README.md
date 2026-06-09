# Modelo de Alocação — Avenue Intelligence Allocation

Pipeline de **recomendação e alocação de produtos por cliente** implementado em
Databricks (catálogo `avenue_intelligence_allocation`). A partir das seleções de
research, do model portfolio definido por perfil, das restrições (IPS + política)
e da posição atual do cliente, o modelo produz uma **ordem de compra otimizada**
para enquadrar a carteira ao alvo recomendado.

> Este documento descreve o pipeline Databricks que dá suporte ao app
> [All&In - Investimentos](https://allocation-intelligence-2846582141784626.gcp.databricksapps.com/).
> Ele é independente do screener de covered calls que vive no restante deste
> repositório (módulo `allocation/opcoes`), embora compartilhem o tema de alocação.

## Visão geral do fluxo

```
1. Produtos Recomendados        ── o QUE pode ser recomendado (research, por classe)
   └─ fact_produtos_recomendados
   └─ vw_produtos_recomendados_atributos   (+ atributos: gestora, duration, rating…)

2. Model Portfolio              ── QUANTO de cada categoria por perfil/carteira
   └─ dim_model_portfolio                  (SCD versionada pelo app)
   └─ vw_model_portfolio_actual            (Agregada / Expandida / Personalizada)

3. Restrições                   ── o que NÃO pode entrar / limites
   ├─ vw_restricao_produtos_actual         (IPS)
   ├─ vw_restricao_atributos_actual        (IPS + política)
   └─ vw_restricao_concentracao_actual     (política → dim_restricao_concentracao)

4. Produtos por Cliente (enabled) ── cruza tudo e aplica restrições em cadeia
   └─ vw_enabled_product_client            (base = model portfolio × recomendados)
   ├─ _r1  (aplica restrição de PRODUTOS)
   ├─ _r2  (aplica restrição de ATRIBUTOS)
   ├─ _r3  (aplica restrição de CONCENTRAÇÃO)
   └─ _r4  (aplica ORDEM dos produtos → PrioridadeFinal)
        └─ enabled_product_client_r4       (registro histórico / snapshot)

5. Otimizador                   ── decide a COMPRA dado caixa e posição atual
   ├─ otimizador_caixa()        (water-filling do gap por categoria)
   └─ alocar_produtos()         (distribui o delta entre produtos por prioridade)
```

## Convenções

- **Idioma:** nomes em português (`Categoria`, `Prioridade`, `Peso`,
  `Restricao`, `FlagCarteira`), seguindo o padrão do restante do projeto.
- **Catálogos/schemas:**
  - `avenue_intelligence_allocation.research` — seleções e parâmetros vindos do
    research / app (camada de entrada).
  - `avenue_intelligence_allocation.modelo_alocacao` — tabelas e views do modelo
    (camada de processamento).
  - `avenue_intelligence_allocation.alocacao` — registros históricos (snapshots).
  - `avenue_intelligence_allocation.ips` — Investment Policy Statement por conta.
  - `avenue_intelligence_allocation.general` / `av_datalake_l3.data_warehouse` —
    dimensões e fatos corporativos (produtos, contas, custódia, clientes ativos).
- **Versionamento temporal (SCD):** dimensões definidas via app
  (`dim_model_portfolio`, `dim_ordem_produtos`, `dim_restricao_concentracao`)
  usam o padrão `StartDate` / `EndDate`, com uma linha-semente `1900-01-01`
  representando o default vigente "desde sempre". As views `*_actual` filtram
  `CURRENT_DATE() BETWEEN StartDate AND EndDate`.
- **RefDate:** a maioria das fatos usa `D-1` (`DATE_ADD(CURRENT_DATE(), -1)`).

## Carteiras suportadas

Três modalidades, todas resolvidas em `vw_model_portfolio_actual`:

| Carteira              | Origem do peso por categoria                                   |
|-----------------------|----------------------------------------------------------------|
| **Agregada**          | model portfolio do perfil de risco do cliente                  |
| **Expandida**         | model portfolio do perfil de risco do cliente                  |
| **Personalizada**     | composição definida no IPS do cliente (`Parameter.ModelPortfolio`) |

## Documentação por etapa

| Etapa | Arquivo |
|-------|---------|
| 1. Produtos Recomendados        | [01_produtos_recomendados.md](01_produtos_recomendados.md) |
| 2. Model Portfolio              | [02_model_portfolio.md](02_model_portfolio.md) |
| 3. Restrições                   | [03_restricoes.md](03_restricoes.md) |
| 4. Produtos por Cliente (enabled)| [04_produtos_por_cliente.md](04_produtos_por_cliente.md) |
| 5. Otimizador                   | [05_otimizador.md](05_otimizador.md) |
