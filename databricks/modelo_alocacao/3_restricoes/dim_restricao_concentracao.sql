-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Restrição Concentração
-- MAGIC
-- MAGIC Por ora, definição somente pela política.

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW VW_DATES AS (

WITH CTE_RefDates AS (

SELECT DISTINCT StartDate AS RefDate
FROM avenue_intelligence_allocation.modelo_alocacao.dim_restricao_concentracao
WHERE StartDate = '1900-01-01'

UNION ALL

SELECT DISTINCT DATE(RefDate) AS RefDate
FROM avenue_intelligence_allocation.research.restricao_concentracao

)

SELECT
  RefDate AS StartDate
  ,COALESCE(LEAD(RefDate) OVER (ORDER BY RefDate) - INTERVAL 1 DAY, DATE '9999-12-31') AS EndDate
FROM CTE_RefDates

);

-- COMMAND ----------

CREATE OR REPLACE TABLE avenue_intelligence_allocation.modelo_alocacao.dim_restricao_concentracao AS (

WITH CTE_1900 AS (

SELECT
  c.Product_N3
  ,c.RatingAvenue
  ,c.DurationAvenue
  ,c.EmissorPublico
  ,c.Limite
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.dim_restricao_concentracao c
ON d.StartDate = c.StartDate

WHERE d.StartDate = '1900-01-01'

)

,CTE_RESEARCH_RANK AS (

SELECT
  Product_N3
  ,RatingAvenue
  ,DurationAvenue
  ,EmissorPublico
  ,Limite
  ,DATE(RefDate) AS RefDate
  ,RANK() OVER (PARTITION BY DATE(RefDate) ORDER BY MetadataIngestion DESC) AS RN
FROM avenue_intelligence_allocation.research.restricao_concentracao

)

,CTE_OUTROS AS (

SELECT
  c.Product_N3
  ,c.RatingAvenue
  ,c.DurationAvenue
  ,c.EmissorPublico
  ,c.Limite
  ,d.StartDate
  ,d.EndDate
FROM VW_DATES d
LEFT JOIN CTE_RESEARCH_RANK c
ON d.StartDate = c.RefDate AND c.RN = 1

WHERE d.StartDate <> '1900-01-01'

)

SELECT * FROM CTE_1900
UNION ALL SELECT * FROM CTE_OUTROS

);
