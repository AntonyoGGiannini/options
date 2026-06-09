-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos por Cliente
-- MAGIC
-- MAGIC Aplicação de restrição de produtos por cliente.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r1 AS (

SELECT
  e.Date
  ,e.AvenueAccountId
  ,e.ModelPortfolioName
  ,e.CodigoPerfil
  ,e.Categoria
  ,e.Symbol
  ,e.Product_N3
  ,e.Prioridade
  ,e.gestora
  ,e.duration
  ,e.setor
  ,e.emissor
  ,e.renda
  ,e.liquidez
  ,e.pais
  ,e.bonds_rating_avenue
  ,e.bonds_duration_avenue
  ,e.bonds_is_public
  ,e.aplicacao_minima
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client e
LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.vw_restricao_produtos_actual r
ON  r.AvenueAccountId = e.AvenueAccountId
    AND r.Restricao = e.Categoria
    AND r.Product_N3 = e.Product_N3

WHERE COALESCE(r.FlagRestricao, 1) = 1

);

-- COMMAND ----------

-- Essa era a query ativa até 29/05

-- SELECT
--   e.Date,
--   e.AvenueAccountId,
--   e.ModelPortfolioName,
--   e.CodigoPerfil,
--   e.Categoria,
--   e.Symbol,
--   e.Product_N3,
--   e.Prioridade,
--   e.gestora,
--   e.duration,
--   e.setor,
--   e.emissor,
--   e.renda,
--   e.liquidez,
--   e.pais,
--   e.bonds_rating_avenue,
--   e.bonds_duration_avenue,
--   e.bonds_is_public,
--   e.aplicacao_minima
-- FROM
--   avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client e
--     LEFT JOIN avenue_intelligence_allocation.modelo_alocacao.vw_restricao_produtos_actual r
--       ON r.AvenueAccountId = e.AvenueAccountId
--       AND r.Restricao = e.Categoria
--       AND r.Product_N3 = e.Product_N3
-- WHERE
--   CASE
--     WHEN
--       NOT EXISTS (
--         SELECT
--           1
--         FROM
--           avenue_intelligence_allocation.modelo_alocacao.vw_restricao_produtos_actual r2
--         WHERE
--           r2.AvenueAccountId = e.AvenueAccountId
--       )
--     THEN
--       1
--     ELSE COALESCE(r.FlagRestricao, 0)
--   END = 1
