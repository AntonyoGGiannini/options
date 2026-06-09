-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Produtos por Cliente
-- MAGIC
-- MAGIC Aplicação de restrição de atributos por cliente.

-- COMMAND ----------

CREATE OR REPLACE VIEW avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r2 AS (

SELECT
  e.*
FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r1 e
WHERE NOT EXISTS (

    SELECT 1
    FROM avenue_intelligence_allocation.modelo_alocacao.vw_restricao_atributos_actual r
    WHERE r.AvenueAccountId = e.AvenueAccountId
          AND ( ( r.Atributo = 'duration'
                  AND e.duration IS NOT NULL
                  AND NOT (
                          CASE r.Operador
                              WHEN '>'  THEN e.duration >  CAST(r.Valor AS DOUBLE)
                              WHEN '<'  THEN e.duration <  CAST(r.Valor AS DOUBLE)
                              WHEN '>=' THEN e.duration >= CAST(r.Valor AS DOUBLE)
                              WHEN '<=' THEN e.duration <= CAST(r.Valor AS DOUBLE)
                              WHEN '='  THEN e.duration =  CAST(r.Valor AS DOUBLE)
                              WHEN '<>' THEN e.duration <> CAST(r.Valor AS DOUBLE)
                              ELSE TRUE -- operador desconhecido: default lenient (não filtra)
                            END ) )

              -- Duration (numérico)
              OR ( r.Atributo = 'gestora'
                  AND e.gestora IS NOT NULL
                  AND NOT (
                          CASE r.Operador
                              WHEN '='  THEN e.gestora =  r.Valor
                              WHEN '<>' THEN e.gestora <> r.Valor
                              ELSE TRUE
                            END ) )

              -- Setor (textual)
              OR ( r.Atributo = 'setor'
                  AND e.setor IS NOT NULL
                  AND NOT (
                          CASE r.Operador
                              WHEN '='  THEN e.setor =  r.Valor
                              WHEN '<>' THEN e.setor <> r.Valor
                              ELSE TRUE
                            END ) )

              -- Emissor (textual)
              OR ( r.Atributo = 'emissor'
                  AND e.emissor IS NOT NULL
                  AND NOT (
                          CASE r.Operador
                              WHEN '='  THEN e.emissor =  r.Valor
                              WHEN '<>' THEN e.emissor <> r.Valor
                              ELSE TRUE
                            END ) )
              )

)

);
