-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos por Cliente
-- MAGIC
-- MAGIC Aplicação de restrição de concentração por cliente.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r3 AS (

WITH CTE_BONDS AS (

SELECT
  a.*
  ,b.Limite
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r2 a
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.vw_restricao_concentracao_actual b
ON  a.Product_N3 = b.Product_N3
    AND a.bonds_rating_avenue = b.RatingAvenue
    AND a.bonds_duration_avenue = b.DurationAvenue
    AND a.bonds_is_public = b.EmissorPublico

WHERE a.Product_N3 = 'Bonds'
      AND b.Limite > 0

)

,CTE_OUTROS AS (

SELECT
  a.*
  ,b.Limite
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r2 a
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.vw_restricao_concentracao_actual b
ON  a.Product_N3 = b.Product_N3

WHERE a.Product_N3 <> 'Bonds'
      AND b.Limite > 0

)

SELECT * FROM CTE_BONDS
UNION ALL SELECT * FROM CTE_OUTROS

);
