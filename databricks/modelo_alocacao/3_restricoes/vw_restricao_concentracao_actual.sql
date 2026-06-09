-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Restrição Concentração
-- MAGIC
-- MAGIC Definição pela política, apenas.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_restricao_concentracao_actual AS (

SELECT * FROM avenue_intelligence_allocation.modelo_alocacao.dim_restricao_concentracao
WHERE CURRENT_DATE() BETWEEN StartDate AND EndDate

);
