-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Registro Físico - Enabled R4
-- MAGIC
-- MAGIC Após aplicar todas as restrições definidas no modelo, salvamos fotos da base final, para manter registro histórico das versões.

-- COMMAND ----------

INSERT INTO avenue_intelligence_allocation.alocacao.enabled_product_client_r4 (

SELECT
  *
  ,CURRENT_TIMESTAMP() AS IngestionDate
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r4

);
