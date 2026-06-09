-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos por Cliente
-- MAGIC
-- MAGIC Ordenação de prioridade por produto:
-- MAGIC
-- MAGIC 1º critério - Prioridade por Product_N3
-- MAGIC
-- MAGIC 2º critério - Prioridade por produto da recomendação mensal

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r4 AS (

SELECT DISTINCT
  r3.AvenueAccountId
  ,r3.ModelPortfolioName
  ,r3.CodigoPerfil
  ,r3.Categoria
  ,r3.Symbol
  ,r3.Product_N3
  ,r3.Prioridade
  ,r3.aplicacao_minima
  ,r3.Limite
  ,op.Ordem
  ,op.Ordem * 100 + r3.Prioridade AS PrioridadeFinal
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r3 r3
JOIN avenue_intelligence_allocation.modelo_alocacao.vw_ordem_produtos_actual op
ON  op.AvenueCategoryId = r3.Categoria
    AND op.Product_N3 = r3.Product_N3

ORDER BY Categoria, PrioridadeFinal

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Queries auxiliares de inspeção (diagnóstico — não fazem parte da view)

-- COMMAND ----------

SELECT
    *
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r4
WHERE AvenueAccountId = 'a23d7da4-25e1-4111-8dfa-2423e5855e72';

-- COMMAND ----------

SELECT c.Date, c.AvenueAccountId, p2.AvenueCategoryId, p.Product_N3, p.Product_N4, p.Product, p.Symbol, c.TotalNetDol
    FROM av_datalake_l3.data_warehouse.fact_custody c
    JOIN av_datalake_l3.data_warehouse.dim_product p ON p.DimProductSK = c.DimProductSK
    LEFT JOIN avenue_intelligence_allocation.general.fact_product p2 ON p2.DimProductSK = c.DimProductSK AND p2.DimTimeSK = c.DimTimeSK
    WHERE
        c.Date = (SELECT MAX(Date) FROM av_datalake_l3.data_warehouse.fact_custody) AND
        p.Product_N3 <> 'Balance US Banking' AND
        c.AvenueAccountId = 'a23d7da4-25e1-4111-8dfa-2423e5855e72';

-- COMMAND ----------

SELECT Date, AvenueAccountId, ModelPortfolioName, CodigoPerfil, AvenueCategoryId, Peso
    FROM avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_actual
    WHERE
        AvenueAccountId = 'a23d7da4-25e1-4111-8dfa-2423e5855e72' AND
        ModelPortfolioName = 'AvenuePersonalizada';

-- COMMAND ----------

SELECT
    f.*
    ,CASE
            WHEN f.Product_N3 = "Funds" THEN f.fundos_isin
            WHEN f.Product_N3 = "Bonds" THEN f.bonds_isin
            WHEN f.Product_N3 = "UCITs" THEN replace(f.fundos_ticker, '.GB', '')
            ELSE f.Symbol
        END as Symbol
FROM avenue_intelligence_allocation.general.fact_product f
WHERE f.DimTimeSK = 20260521 AND CASE
            WHEN f.Product_N3 = "Funds" THEN f.fundos_isin
            WHEN f.Product_N3 = "Bonds" THEN f.bonds_isin
            WHEN f.Product_N3 = "UCITs" THEN replace(f.fundos_ticker, '.GB', '')
            ELSE f.Symbol
        END IS NULL;
