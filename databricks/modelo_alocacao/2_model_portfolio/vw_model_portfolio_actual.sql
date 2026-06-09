-- Databricks notebook source
-- MAGIC %md
-- MAGIC # View Final - Model Portfolio Atual
-- MAGIC
-- MAGIC Base final de model portfolio.
-- MAGIC
-- MAGIC Trazendo os model portfolio atuais definidos para as 3 carteiras disponíveis para os clientes: Agregada, Expandida e Personalizada.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_personalizado AS (

WITH CTE_IPS_DEDUP AS (

SELECT
  *
  ,ROW_NUMBER() OVER (PARTITION BY AvenueAccountId ORDER BY RegistryDate DESC, ConfirmationDate DESC) AS Rn
FROM avenue_intelligence_allocation.ips.dim_ips
WHERE CURRENT_DATE() BETWEEN DATE(RegistryDate) AND ExpirationDate
      AND get_json_object(Parameter, '$.ModelPortfolio') IS NOT NULL

)

,CTE_PORT_TESTE AS (

SELECT
  (SELECT MAX(Date) FROM av_datalake_l3.data_warehouse.fact_custody) AS Date
  ,i.AvenueAccountId
  ,'AvenuePersonalizada'                   AS ModelPortfolioName
  ,i.IPSId                                 AS CodigoPerfil
  ,x.key                                   AS AvenueCategoryId
  ,CAST(x.value AS DECIMAL(5,2))           AS Peso
  ,DATE(i.Parameter:ModelPortfolio:start)  AS StartDate
  ,DATE(i.Parameter:ModelPortfolio:end)    AS EndDate

FROM (SELECT * FROM CTE_IPS_DEDUP WHERE Rn = 1) i

LATERAL VIEW explode(from_json(i.Parameter:ModelPortfolio:composition, 'MAP<STRING, STRING>')) x

)

,CTE_PORT AS (

SELECT
  (SELECT MAX(Date) FROM av_datalake_l3.data_warehouse.fact_custody) AS Date
  ,i.AvenueAccountId
  ,'AvenuePersonalizada'                   AS ModelPortfolioName
  ,i.IPSId                                 AS CodigoPerfil
  ,x.key                                   AS AvenueCategoryId
  ,CAST(x.value AS DECIMAL(5,2))           AS Peso
  ,DATE(i.RegistryDate)                    AS StartDate
  ,DATE(i.ExpirationDate)                  AS EndDate

FROM (SELECT * FROM CTE_IPS_DEDUP WHERE Rn = 1) i

LATERAL VIEW explode(from_json(i.Parameter:ModelPortfolio, 'MAP<STRING, STRING>')) x

)

SELECT * FROM CTE_PORT_TESTE
UNION ALL
SELECT * FROM CTE_PORT WHERE LEFT(AvenueCategoryId, 2) = 'AV'

);

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_actual AS (

WITH CTE_CLIENT_PROFILE AS (

SELECT
  ac.RefDate AS Date
  ,ac.AvenueAccountId
  ,CASE
      WHEN a.RiskTolerance == 'LOW' AND a.TimeHorizon = 'SHORT' THEN 'P1'
      ELSE p.CodigoPerfil
    END AS CodigoPerfil
FROM av_datalake_l3.data_warehouse.fact_active_clients ac
JOIN av_datalake_l3.data_warehouse.dim_account a
ON a.DimAccountSK = ac.DimAccountSK

JOIN avenue_intelligence_allocation.modelo_alocacao.de_para_perfil p
ON p.AvenueRiskProfile = a.AvenueRiskProfile

WHERE ac.RefDate = (SELECT MAX(RefDate) FROM av_datalake_l3.data_warehouse.fact_active_clients)

)

,CTE_MODEL_GERAL AS (

SELECT
  p.Date
  ,p.AvenueAccountId
  ,m.*
FROM CTE_CLIENT_PROFILE p
JOIN avenue_intelligence_allocation.modelo_alocacao.dim_model_portfolio m
ON p.CodigoPerfil = m.CodigoPerfil

WHERE CURRENT_DATE() BETWEEN m.StartDate AND m.EndDate

)

SELECT * FROM CTE_MODEL_GERAL

UNION ALL

SELECT * FROM avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_personalizado

);
