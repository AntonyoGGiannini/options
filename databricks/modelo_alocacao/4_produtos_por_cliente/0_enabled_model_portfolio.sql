-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos por Cliente
-- MAGIC
-- MAGIC Etapa de marcação de atributos essenciais para as próximas definições.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client AS (

SELECT
  mp.Date
  ,mp.AvenueAccountId
  ,mp.ModelPortfolioName
  ,mp.CodigoPerfil
  ,pr.Categoria
  ,pr.Symbol
  ,pr.Product_N3
  ,pr.Prioridade
  ,pr.gestora
  ,pr.duration
  ,pr.aplicacao_minima
  ,pr.bonds_duration_avenue
  ,pr.bonds_is_public
  ,pr.bonds_rating_avenue
  ,pr.emissor
  ,pr.setor
  ,pr.pais
  ,pr.renda
  ,pr.liquidez
FROM avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_actual mp
JOIN avenue_intelligence_allocation.modelo_alocacao.vw_produtos_recomendados_atributos pr
ON mp.AvenueCategoryId = pr.Categoria

WHERE mp.Peso > 0
      AND pr.Date = (SELECT MAX(Date) FROM avenue_intelligence_allocation.modelo_alocacao.vw_produtos_recomendados_atributos)
      AND mp.Date = (SELECT MAX(Date) FROM avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_actual)

);
