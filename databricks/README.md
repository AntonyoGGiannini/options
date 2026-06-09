# Databricks — Notebooks versionados (Git folders / Repos)

Esta pasta contém os notebooks do **modelo de alocação** em formato *source* do
Databricks, prontos para serem executados via **Databricks Git folders (Repos)**.
A execução continua acontecendo no Databricks; o git é apenas a fonte de verdade
do código.

A documentação conceitual de cada etapa está em
[`../docs/modelo_alocacao/`](../docs/modelo_alocacao/README.md).

## Formato dos arquivos

Cada arquivo é um notebook em *source format*, reconhecido automaticamente pelo
Databricks ao sincronizar o repo:

- `.sql` → notebook SQL. Primeira linha `-- Databricks notebook source`,
  células separadas por `-- COMMAND ----------`, markdown em `-- MAGIC %md`.
- `.py` → notebook Python. Primeira linha `# Databricks notebook source`,
  células separadas por `# COMMAND ----------`, markdown em `# MAGIC %md`.

## Como ligar o Repo

1. No Databricks: **Workspace → Repos → Add Repo**.
2. Aponte para este repositório git e selecione o branch desejado.
3. Os arquivos em `databricks/modelo_alocacao/` aparecem como notebooks
   executáveis. Configure os Jobs/Workflows apontando para eles.

> Edições feitas no Databricks podem ser commitadas de volta pela UI do Repo;
> edições feitas no git aparecem após **Pull** no Repo.

## Estrutura e ordem de execução

A ordem importa: views consomem tabelas/views das etapas anteriores.

```
modelo_alocacao/
├── 1_produtos_recomendados/
│   ├── A_fact_produtos_recomendados.sql      → tabela fact_produtos_recomendados
│   └── B_produtos_recomendados_atributos.sql → vw_produtos_recomendados_atributos
├── 2_model_portfolio/
│   ├── dim_model_portfolio.sql               → tabela (SCD versionada)
│   └── vw_model_portfolio_actual.sql         → vw_model_portfolio_personalizado + _actual
├── 3_restricoes/
│   ├── vw_restricao_produtos_actual.sql
│   ├── vw_restricao_atributos_actual.sql     → _personalizado + _actual
│   ├── dim_restricao_concentracao.sql        → tabela (SCD versionada)
│   └── vw_restricao_concentracao_actual.sql
├── 4_produtos_por_cliente/
│   ├── A_ordem_produtos/
│   │   ├── dim_ordem_produtos.sql            → tabela (SCD versionada)
│   │   └── vw_ordem_produtos_actual.sql
│   ├── 0_enabled_model_portfolio.sql         → vw_enabled_product_client (base)
│   ├── 1_enabled_r1_restricao_produtos.sql   → vw_enabled_product_client_r1
│   ├── 2_enabled_r2_restricao_atributos.sql  → vw_enabled_product_client_r2
│   ├── 3_enabled_r3_restricao_concentracao.sql → vw_enabled_product_client_r3
│   ├── 4_enabled_r4_ordem_produtos.sql       → vw_enabled_product_client_r4
│   └── 5_enabled_r4_registro_historico.sql   → snapshot em alocacao.enabled_product_client_r4
└── 5_otimizador/
    └── otimizador.py                         → otimizador_caixa + alocar_produtos
```

### Dependências entre etapas

1. **Etapa 1** depende das tabelas `research.selecao_*` e `dim_product`.
2. **Etapa 2** é independente das etapas 1/3.
3. **Etapa 3** é independente das etapas 1/2.
4. **Etapa 4** depende de **1, 2 e 3** (cruza model portfolio × recomendados e
   aplica as restrições em cadeia r1 → r4). Dentro dela:
   `A_ordem_produtos` e `0_enabled` antes de `1_r1 → 2_r2 → 3_r3 → 4_r4 → 5_registro`.
5. **Etapa 5** (otimizador) consome `vw_model_portfolio_actual` e
   `vw_enabled_product_client_r4`, além da custódia atual.

> Sugestão de orquestração: um Job com tarefas 1, 2, 3 em paralelo → etapa 4 em
> sequência (respeitando r1→r4) → registro histórico. O otimizador (etapa 5) é
> normalmente executado sob demanda por cliente.
