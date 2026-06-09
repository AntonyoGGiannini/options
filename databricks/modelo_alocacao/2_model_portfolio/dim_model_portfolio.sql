-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Tabela - dim_model_portfolio
-- MAGIC
-- MAGIC Definição dos model portfolios através do preenchimento do app [All&In - Investimentos](https://allocation-intelligence-2846582141784626.gcp.databricksapps.com/) (página Model Portfolio).

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW VW_DATES AS (

WITH CTE_RefDates AS (

SELECT DISTINCT StartDate AS RefDate
FROM avenue_intelligence_allocation.modelo_alocacao.dim_model_portfolio
WHERE StartDate = '1900-01-01'

UNION ALL

SELECT DISTINCT DATE(RefDate) AS RefDate
FROM avenue_intelligence_allocation.research.model_portfolio

)

SELECT
  RefDate AS StartDate
  ,COALESCE(LEAD(RefDate) OVER (ORDER BY RefDate) - INTERVAL 1 DAY, DATE '9999-12-31') AS EndDate
FROM CTE_RefDates

);

-- COMMAND ----------

CREATE OR REPLACE TABLE avenue_intelligence_allocation.modelo_alocacao.dim_model_portfolio AS (

WITH CTE_1900 AS (

SELECT
  m.ModelPortfolioName
  ,m.CodigoPerfil
  ,m.AvenueCategoryId
  ,m.Peso
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.dim_model_portfolio m
ON d.StartDate = m.StartDate

WHERE d.StartDate = '1900-01-01'

)

,CTE_RESEARCH_RANK AS (

SELECT
  ModelPortfolioName
  ,CodigoPerfil
  ,AvenueCategoryId
  ,Peso
  ,DATE(RefDate) AS RefDate
  ,RANK() OVER ( PARTITION BY DATE(RefDate) ORDER BY MetadataIngestion DESC) AS RN
FROM avenue_intelligence_allocation.research.model_portfolio

)

,CTE_OUTROS AS (

SELECT
  m.ModelPortfolioName
  ,m.CodigoPerfil
  ,m.AvenueCategoryId
  ,m.Peso
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN CTE_RESEARCH_RANK m
ON d.StartDate = m.RefDate AND m.RN = 1

WHERE d.StartDate <> '1900-01-01'

)

SELECT * FROM CTE_1900
UNION ALL SELECT * FROM CTE_OUTROS

);
