-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos Recomendados Atributos

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_produtos_recomendados_atributos AS (

WITH CTE_PRODUCT_MAX AS (

SELECT * FROM avenue_intelligence_allocation.general.fact_product
WHERE DimTimeSK = (SELECT MAX(DimTimeSK) FROM avenue_intelligence_allocation.general.fact_product)

)

SELECT
  r.*
  ,p.fundos_fund_group AS gestora
  ,p.bonds_duration AS duration
  ,p.bonds_name AS emissor
  ,p.bonds_sector AS setor
  ,p.bonds_branch AS pais
  ,CASE
      WHEN p.Product_N3 IN ('Stocks', 'Bonds', "ETF's") THEN 1
      ELSE 0
    END AS renda
  ,'3' AS liquidez
  ,CASE
      WHEN p.Product_N3 = 'Funds' THEN 1000 --p.fundos_minimum_initial_subscription_amount
      WHEN p.Product_N3 = 'Bonds' THEN p.bonds_min_qty_trade * p.bonds_bid_price
      WHEN p.Product_N3 = 'UCITs' THEN 250
      ELSE 250
    END AS aplicacao_minima
  ,p.bonds_is_public
  ,p.bonds_rating_avenue
  ,p.bonds_duration_avenue
FROM avenue_intelligence_allocation.modelo_alocacao.fact_produtos_recomendados r
LEFT JOIN CTE_PRODUCT_MAX p
ON  p.Symbol = r.Symbol
    OR p.bonds_isin = r.Symbol

WHERE r.DimTimeSK = (SELECT MAX(DimTimeSK) FROM avenue_intelligence_allocation.modelo_alocacao.fact_produtos_recomendados)

);
