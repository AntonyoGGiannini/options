-- Databricks notebook source
-- MAGIC %md
-- MAGIC # View Final - Ordem Produtos Atual

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_ordem_produtos_actual AS (

SELECT * FROM avenue_intelligence_allocation.modelo_alocacao.dim_ordem_produtos
WHERE CURRENT_DATE() BETWEEN StartDate AND EndDate

);
