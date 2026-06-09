-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Restrição Produtos
-- MAGIC
-- MAGIC Definição pelo preenchimento do IPS, apenas.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_restricao_produtos_actual AS (

WITH CTE_DATAS_LIMITE AS (

SELECT DISTINCT
  AvenueAccountId
  ,CAST(RegistryDate AS DATE) AS DataLimite
FROM avenue_intelligence_allocation.ips.dim_ips
WHERE get_json_object(Parameter, '$.Restricao_Produtos') IS NOT NULL

UNION

SELECT DISTINCT
  AvenueAccountId
  ,CAST(ExpirationDate AS DATE) AS DataLimite
FROM avenue_intelligence_allocation.ips.dim_ips
WHERE get_json_object(Parameter, '$.Restricao_Produtos') IS NOT NULL

)

,CTE_INTERVALOS AS (

SELECT
  AvenueAccountId
  ,DataLimite AS StartDate
  ,DATEADD(DAY, -1, LEAD(DataLimite) OVER (PARTITION BY AvenueAccountId ORDER BY DataLimite)) AS EndDate
FROM CTE_DATAS_LIMITE

)

,CTE_INTERVALOS_PRIORIDADE AS (

SELECT
  i.AvenueAccountId
  ,i.StartDate
  ,i.EndDate
  ,d.IPSId
  ,d.Horizon
  ,d.Parameter
FROM CTE_INTERVALOS i
INNER JOIN avenue_intelligence_allocation.ips.dim_ips d
ON  i.AvenueAccountId = d.AvenueAccountId
    AND i.StartDate >= CAST(d.RegistryDate AS DATE)
    AND i.StartDate <= CAST(d.ExpirationDate AS DATE)

WHERE i.EndDate IS NOT NULL

QUALIFY ROW_NUMBER() OVER (
    PARTITION BY i.AvenueAccountId, i.StartDate
    ORDER BY
      CASE WHEN d.Horizon = 'Pontual'    THEN 1
           WHEN d.Horizon = 'Permanente' THEN 2
           ELSE 3
      END ASC
      ,CAST(d.RegistryDate AS DATE) DESC
    ) = 1

)

,CTE_RESTRICOES AS (

SELECT
  p.AvenueAccountId
  ,REGEXP_EXTRACT(restricao.key, '_(Bonds|ETFs|Funds|Stocks|UCITS|UCITs)$', 1) AS Product_N3
  ,REGEXP_REPLACE(restricao.key, '_(Bonds|ETFs|Funds|Stocks|UCITS|UCITs)$', '') AS Restricao
  ,p.StartDate
  ,p.EndDate
  ,restricao.value AS FlagRestricao
FROM CTE_INTERVALOS_PRIORIDADE p
LATERAL VIEW EXPLODE(
    FROM_JSON(
        GET_JSON_OBJECT(p.Parameter, '$.Restricao_Produtos'),
        'MAP<STRING, INT>'
    )
    ) restricao AS key, value

)

SELECT
  AvenueAccountId
  ,Product_N3
  ,Restricao
  ,MIN(FlagRestricao) AS FlagRestricao
  ,DATE(StartDate) AS StartDate
  ,DATE(EndDate) AS EndDate
FROM CTE_RESTRICOES
WHERE CURRENT_DATE() BETWEEN DATE(StartDate) AND DATE(EndDate)
GROUP BY ALL

);
