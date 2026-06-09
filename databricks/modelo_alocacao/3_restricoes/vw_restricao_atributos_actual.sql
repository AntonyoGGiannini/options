-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Restrição Atributos
-- MAGIC
-- MAGIC Definição pelo preenchimento do IPS e pela política.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_restricao_atributos_personalizado AS (

WITH CTE_IPS_ATUAL AS (

SELECT * FROM avenue_intelligence_allocation.ips.dim_ips
WHERE CURRENT_DATE() BETWEEN DATE(RegistryDate) AND ExpirationDate
      AND get_json_object(Parameter, '$.Restricao_Atributos') IS NOT NULL

)

SELECT
  AvenueAccountId
  ,item.atributo AS Atributo
  ,item.operador AS Operador
  ,item.valor AS Valor
  ,DATE(RegistryDate) AS StartDate
  ,DATE(ExpirationDate) AS EndDate
FROM CTE_IPS_ATUAL
LATERAL VIEW EXPLODE(
    FROM_JSON(
        GET_JSON_OBJECT(Parameter, '$.Restricao_Atributos'),
        'ARRAY<STRUCT<atributo: STRING, operador: STRING, valor: STRING>>'
    )
) item AS item
WHERE item.atributo IS NOT NULL

);

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_restricao_atributos_actual AS (

WITH CTE_RESTRICAO_GERAL AS (

SELECT
  AvenueAccountId
  ,CASE
      WHEN LiquidityNeeds = 'VERY_IMPORTANT' THEN 'liquidez'
      WHEN InvestmentObjective = 'INCOME' THEN 'renda'
    END AS Atributo
  ,CASE
      WHEN LiquidityNeeds = 'VERY_IMPORTANT' THEN '<='
      WHEN InvestmentObjective = 'INCOME' THEN '='
    END AS Operador
  ,CASE
      WHEN LiquidityNeeds = 'VERY_IMPORTANT' THEN 5
      WHEN InvestmentObjective = 'INCOME' THEN 1
    END AS Valor
  ,DATE(DimStartDate) AS StartDate
  ,DATE(DimEndDate) AS EndDate
FROM av_datalake_l3.data_warehouse.dim_account
WHERE DimActiveFlag = 1
      AND CanTrade = 'Can Trade'
      AND (LiquidityNeeds = 'VERY_IMPORTANT' OR InvestmentObjective = 'INCOME')

)

SELECT * FROM CTE_RESTRICAO_GERAL
WHERE CURRENT_DATE() BETWEEN StartDate AND EndDate

UNION ALL

SELECT * FROM avenue_intelligence_allocation.modelo_alocacao.vw_restricao_atributos_personalizado
WHERE CURRENT_DATE() BETWEEN StartDate AND EndDate

);
