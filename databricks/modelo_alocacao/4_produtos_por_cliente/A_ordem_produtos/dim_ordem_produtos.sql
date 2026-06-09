-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Tabela - dim_ordem_produtos
-- MAGIC
-- MAGIC Definição da ordem dos produtos através do preenchimento do app [All&In - Investimentos](https://allocation-intelligence-2846582141784626.gcp.databricksapps.com/) (página Ordem Produtos).

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW VW_DATES AS (

WITH CTE_RefDates AS (

SELECT DISTINCT StartDate AS RefDate
FROM avenue_intelligence_allocation.modelo_alocacao.dim_ordem_produtos
WHERE StartDate = '1900-01-01'

UNION ALL

SELECT DISTINCT DATE(RefDate) AS RefDate
FROM avenue_intelligence_allocation.research.ordem_produtos

)

SELECT
  RefDate AS StartDate
  ,COALESCE(LEAD(RefDate) OVER (ORDER BY RefDate) - INTERVAL 1 DAY, DATE '9999-12-31') AS EndDate
FROM CTE_RefDates

);

-- COMMAND ----------

CREATE OR REPLACE TABLE avenue_intelligence_allocation.modelo_alocacao.dim_ordem_produtos AS (

WITH CTE_1900 AS (

SELECT
  o.Product_N3
  ,o.AvenueCategoryId
  ,o.Ordem
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.dim_ordem_produtos o
ON d.StartDate = o.StartDate

WHERE d.StartDate = '1900-01-01'

)

,CTE_RESEARCH_RANK AS (

SELECT
  Product_N3
  ,AvenueCategoryId
  ,Ordem
  ,DATE(RefDate) AS RefDate
  ,RANK() OVER (PARTITION BY DATE(RefDate) ORDER BY MetadataIngestion DESC) AS RN
FROM avenue_intelligence_allocation.research.ordem_produtos

)

,CTE_OUTROS AS (

SELECT
  o.Product_N3
  ,o.AvenueCategoryId
  ,o.Ordem
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN CTE_RESEARCH_RANK o
ON d.StartDate = o.RefDate AND o.RN = 1

WHERE d.StartDate <> '1900-01-01'

)

SELECT * FROM CTE_1900
UNION ALL SELECT * FROM CTE_OUTROS

);
