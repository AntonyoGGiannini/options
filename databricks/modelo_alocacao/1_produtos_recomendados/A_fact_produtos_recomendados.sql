-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Recomendação Produtos - Base final
-- MAGIC
-- MAGIC Nessa etapa defineremos, por mês, os produtos recomendados para a carteira dos clientes.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1. Bonds

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW BONDS_RECOMENDADOS AS (

WITH CTE_DATA_CONSIDERADA AS (

SELECT MAX(DataFim) AS DataConsiderada
FROM avenue_intelligence_allocation.research.selecao_bonds
WHERE DataFim <= CURRENT_DATE()

)

,CTE_DADOS AS (

SELECT
  DATE_ADD(CURRENT_DATE(), -1) AS RefDate
  ,DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -1), 'yyyyMMdd') AS DimTimeSK
  ,b.ISIN AS Symbol
  ,b.Categoria
  ,d.Product_N3
  ,b.ClassificacaoLista
  ,b.Prioridade
  ,b.FlagCarteira
  ,b.Responsavel
  ,b.ClassificacaoPeriodo
FROM avenue_intelligence_allocation.research.selecao_bonds b
LEFT JOIN av_datalake_l3.data_warehouse.dim_product d
ON b.ISIN = d.ISIN AND d.DimActiveFlag = 1

WHERE (SELECT DataConsiderada FROM CTE_DATA_CONSIDERADA) BETWEEN DataInicio AND DataFim
      AND b.ISIN IS NOT NULL

)

,CTE_PONTUAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Campanha'

)

,CTE_MENSAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Mensal'
      AND Symbol NOT IN (SELECT DISTINCT Symbol FROM CTE_PONTUAL)

)

-- Identifica, por lista, quais prioridades foram selecionadas para campanhas/recomendações pontuais

,CTE_PRIORIDADES_OCUPADAS AS (

SELECT
  ClassificacaoLista
  ,Prioridade AS PrioridadeOcupada
FROM CTE_PONTUAL

)

-- Reprioriza os produtos mensais:
-- Para cada produto mensal, conta quantos produtos de campanha da mesma ClassificacaoLista possuem Prioridade <= à dele.
-- Isso "empurra" o produto mensal para baixo na fila, cedendo espaço para a campanha se inserir na posição correta.

,CTE_MENSAL_REPRIORIZADO AS (

SELECT
  m.RefDate
  ,m.DimTimeSK
  ,m.Symbol
  ,m.Categoria
  ,m.Product_N3
  ,m.ClassificacaoLista
  ,m.FlagCarteira
  ,m.Responsavel
  ,m.ClassificacaoPeriodo
  ,m.Prioridade AS PrioridadeOriginal
  ,m.Prioridade + COUNT(o.PrioridadeOcupada) AS Prioridade
FROM CTE_MENSAL m
LEFT JOIN CTE_PRIORIDADES_OCUPADAS o
ON o.ClassificacaoLista = m.ClassificacaoLista
   AND o.PrioridadeOcupada <= m.Prioridade

GROUP BY ALL

)

-- Une produtos mensais (já repriorizado) com campanhas pontuais,
-- mantendo a Prioridade original das campanhas intacta.
SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_MENSAL_REPRIORIZADO

UNION ALL

SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade                 -- mantém a prioridade original da campanha
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_PONTUAL

ORDER BY ClassificacaoLista, Prioridade

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2. ETFs

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW ETFS_RECOMENDADOS AS (

WITH CTE_DATA_CONSIDERADA AS (

SELECT MAX(DataFim) AS DataConsiderada
FROM avenue_intelligence_allocation.research.selecao_etfs
WHERE DataFim <= CURRENT_DATE()

)

,CTE_DADOS AS (

SELECT
  DATE_ADD(CURRENT_DATE(), -1) AS RefDate
  ,DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -1), 'yyyyMMdd') AS DimTimeSK
  ,b.Ticker AS Symbol
  ,b.Categoria
  ,d.Product_N3
  ,b.ClassificacaoLista
  ,b.Prioridade
  ,b.FlagCarteira
  ,b.Responsavel
  ,b.ClassificacaoPeriodo
FROM avenue_intelligence_allocation.research.selecao_etfs b
LEFT JOIN av_datalake_l3.data_warehouse.dim_product d
ON b.Ticker = d.Symbol AND d.DimActiveFlag = 1

WHERE (SELECT DataConsiderada FROM CTE_DATA_CONSIDERADA) BETWEEN DataInicio AND DataFim
      AND b.Ticker IS NOT NULL

)

,CTE_PONTUAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Campanha'

)

,CTE_MENSAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Mensal'
      AND Symbol NOT IN (SELECT DISTINCT Symbol FROM CTE_PONTUAL)

)

-- Identifica, por lista, quais prioridades foram selecionadas para campanhas/recomendações pontuais

,CTE_PRIORIDADES_OCUPADAS AS (

SELECT
  ClassificacaoLista
  ,Prioridade AS PrioridadeOcupada
FROM CTE_PONTUAL

)

-- Reprioriza os produtos mensais:
-- Para cada produto mensal, conta quantos produtos de campanha da mesma ClassificacaoLista possuem Prioridade <= à dele.
-- Isso "empurra" o produto mensal para baixo na fila, cedendo espaço para a campanha se inserir na posição correta.

,CTE_MENSAL_REPRIORIZADO AS (

SELECT
  m.RefDate
  ,m.DimTimeSK
  ,m.Symbol
  ,m.Categoria
  ,m.Product_N3
  ,m.ClassificacaoLista
  ,m.FlagCarteira
  ,m.Responsavel
  ,m.ClassificacaoPeriodo
  ,m.Prioridade AS PrioridadeOriginal
  ,m.Prioridade + COUNT(o.PrioridadeOcupada) AS Prioridade
FROM CTE_MENSAL m
LEFT JOIN CTE_PRIORIDADES_OCUPADAS o
ON o.ClassificacaoLista = m.ClassificacaoLista
   AND o.PrioridadeOcupada <= m.Prioridade

GROUP BY ALL

)

-- Une produtos mensais (já repriorizado) com campanhas pontuais,
-- mantendo a Prioridade original das campanhas intacta.
SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_MENSAL_REPRIORIZADO

UNION ALL

SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade                 -- mantém a prioridade original da campanha
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_PONTUAL

ORDER BY ClassificacaoLista, Prioridade

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3. Fundos

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW FUNDOS_RECOMENDADOS AS (

WITH CTE_DATA_CONSIDERADA AS (

SELECT MAX(DataFim) AS DataConsiderada
FROM avenue_intelligence_allocation.research.selecao_fundos
WHERE DataFim <= CURRENT_DATE()

)

,CTE_DADOS AS (

SELECT
  DATE_ADD(CURRENT_DATE(), -1) AS RefDate
  ,DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -1), 'yyyyMMdd') AS DimTimeSK
  ,b.ISIN AS Symbol
  ,b.Categoria
  ,d.Product_N3
  ,b.ClassificacaoLista
  ,b.Prioridade
  ,b.FlagCarteira
  ,b.Responsavel
  ,b.ClassificacaoPeriodo
FROM avenue_intelligence_allocation.research.selecao_fundos b
LEFT JOIN av_datalake_l3.data_warehouse.dim_product d
ON b.ISIN = d.ISIN AND d.DimActiveFlag = 1

WHERE (SELECT DataConsiderada FROM CTE_DATA_CONSIDERADA) BETWEEN DataInicio AND DataFim
      AND b.ISIN IS NOT NULL

)

,CTE_PONTUAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Campanha'

)

,CTE_MENSAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Mensal'
      AND Symbol NOT IN (SELECT DISTINCT Symbol FROM CTE_PONTUAL)

)

-- Identifica, por lista, quais prioridades foram selecionadas para campanhas/recomendações pontuais

,CTE_PRIORIDADES_OCUPADAS AS (

SELECT
  ClassificacaoLista
  ,Prioridade AS PrioridadeOcupada
FROM CTE_PONTUAL

)

-- Reprioriza os produtos mensais:
-- Para cada produto mensal, conta quantos produtos de campanha da mesma ClassificacaoLista possuem Prioridade <= à dele.
-- Isso "empurra" o produto mensal para baixo na fila, cedendo espaço para a campanha se inserir na posição correta.

,CTE_MENSAL_REPRIORIZADO AS (

SELECT
  m.RefDate
  ,m.DimTimeSK
  ,m.Symbol
  ,m.Categoria
  ,m.Product_N3
  ,m.ClassificacaoLista
  ,m.FlagCarteira
  ,m.Responsavel
  ,m.ClassificacaoPeriodo
  ,m.Prioridade AS PrioridadeOriginal
  ,m.Prioridade + COUNT(o.PrioridadeOcupada) AS Prioridade
FROM CTE_MENSAL m
LEFT JOIN CTE_PRIORIDADES_OCUPADAS o
ON o.ClassificacaoLista = m.ClassificacaoLista
   AND o.PrioridadeOcupada <= m.Prioridade

GROUP BY ALL

)

-- Une produtos mensais (já repriorizado) com campanhas pontuais,
-- mantendo a Prioridade original das campanhas intacta.
SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_MENSAL_REPRIORIZADO

UNION ALL

SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade                 -- mantém a prioridade original da campanha
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_PONTUAL

ORDER BY ClassificacaoLista, Prioridade

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4. Stocks

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW STOCKS_RECOMENDADOS AS (

WITH CTE_DATA_CONSIDERADA AS (

SELECT MAX(DataFim) AS DataConsiderada
FROM avenue_intelligence_allocation.research.selecao_stocks
WHERE DataFim <= CURRENT_DATE()

)

,CTE_DADOS AS (

SELECT
  DATE_ADD(CURRENT_DATE(), -1) AS RefDate
  ,DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -1), 'yyyyMMdd') AS DimTimeSK
  ,Ticker AS Symbol
  ,Categoria
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM avenue_intelligence_allocation.research.selecao_stocks
WHERE (SELECT DataConsiderada FROM CTE_DATA_CONSIDERADA) BETWEEN DataInicio AND DataFim
      AND Ticker IS NOT NULL

)

,CTE_PONTUAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Campanha'

)

,CTE_MENSAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Mensal'
      AND Symbol NOT IN (SELECT DISTINCT Symbol FROM CTE_PONTUAL)

)

-- Identifica, por lista, quais prioridades foram selecionadas para campanhas/recomendações pontuais

,CTE_PRIORIDADES_OCUPADAS AS (

SELECT
  ClassificacaoLista
  ,Prioridade AS PrioridadeOcupada
FROM CTE_PONTUAL

)

-- Reprioriza os produtos mensais:
-- Para cada produto mensal, conta quantos produtos de campanha da mesma ClassificacaoLista possuem Prioridade <= à dele.
-- Isso "empurra" o produto mensal para baixo na fila, cedendo espaço para a campanha se inserir na posição correta.

,CTE_MENSAL_REPRIORIZADO AS (

SELECT
  m.RefDate
  ,m.DimTimeSK
  ,m.Symbol
  ,m.Categoria
  ,m.ClassificacaoLista
  ,m.FlagCarteira
  ,m.Responsavel
  ,m.ClassificacaoPeriodo
  ,m.Prioridade AS PrioridadeOriginal
  ,m.Prioridade + COUNT(o.PrioridadeOcupada) AS Prioridade
FROM CTE_MENSAL m
LEFT JOIN CTE_PRIORIDADES_OCUPADAS o
ON o.ClassificacaoLista = m.ClassificacaoLista
   AND o.PrioridadeOcupada <= m.Prioridade

GROUP BY ALL

)

-- Une produtos mensais (já repriorizado) com campanhas pontuais,
-- mantendo a Prioridade original das campanhas intacta.
SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_MENSAL_REPRIORIZADO

UNION ALL

SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,ClassificacaoLista
  ,Prioridade                 -- mantém a prioridade original da campanha
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_PONTUAL

ORDER BY ClassificacaoLista, Prioridade

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5. UCITS

-- COMMAND ----------

CREATE OR REPLACE TEMPORARY VIEW UCITS_RECOMENDADOS AS (

WITH CTE_DATA_CONSIDERADA AS (

SELECT MAX(DataFim) AS DataConsiderada
FROM avenue_intelligence_allocation.research.selecao_ucits
WHERE DataFim <= CURRENT_DATE()

)

,CTE_DADOS AS (

SELECT
  DATE_ADD(CURRENT_DATE(), -1) AS RefDate
  ,DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -1), 'yyyyMMdd') AS DimTimeSK
  ,b.ISIN AS Symbol
  ,b.Categoria
  ,d.Product_N3
  ,b.ClassificacaoLista
  ,b.Prioridade
  ,b.FlagCarteira
  ,b.Responsavel
  ,b.ClassificacaoPeriodo
FROM avenue_intelligence_allocation.research.selecao_ucits b
LEFT JOIN av_datalake_l3.data_warehouse.dim_product d
ON b.ISIN = d.ISIN AND d.DimActiveFlag = 1

WHERE (SELECT DataConsiderada FROM CTE_DATA_CONSIDERADA) BETWEEN DataInicio AND DataFim
      AND b.ISIN IS NOT NULL

)

,CTE_PONTUAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Campanha'

)

,CTE_MENSAL AS (

SELECT * FROM CTE_DADOS
WHERE ClassificacaoPeriodo = 'Mensal'
      AND Symbol NOT IN (SELECT DISTINCT Symbol FROM CTE_PONTUAL)

)

-- Identifica, por lista, quais prioridades foram selecionadas para campanhas/recomendações pontuais

,CTE_PRIORIDADES_OCUPADAS AS (

SELECT
  ClassificacaoLista
  ,Prioridade AS PrioridadeOcupada
FROM CTE_PONTUAL

)

-- Reprioriza os produtos mensais:
-- Para cada produto mensal, conta quantos produtos de campanha da mesma ClassificacaoLista possuem Prioridade <= à dele.
-- Isso "empurra" o produto mensal para baixo na fila, cedendo espaço para a campanha se inserir na posição correta.

,CTE_MENSAL_REPRIORIZADO AS (

SELECT
  m.RefDate
  ,m.DimTimeSK
  ,m.Symbol
  ,m.Categoria
  ,m.Product_N3
  ,m.ClassificacaoLista
  ,m.FlagCarteira
  ,m.Responsavel
  ,m.ClassificacaoPeriodo
  ,m.Prioridade AS PrioridadeOriginal
  ,m.Prioridade + COUNT(o.PrioridadeOcupada) AS Prioridade
FROM CTE_MENSAL m
LEFT JOIN CTE_PRIORIDADES_OCUPADAS o
ON o.ClassificacaoLista = m.ClassificacaoLista
   AND o.PrioridadeOcupada <= m.Prioridade

GROUP BY ALL

)

-- Une produtos mensais (já repriorizado) com campanhas pontuais,
-- mantendo a Prioridade original das campanhas intacta.
SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_MENSAL_REPRIORIZADO

UNION ALL

SELECT
  RefDate
  ,DimTimeSK
  ,Symbol
  ,Categoria
  ,Product_N3
  ,ClassificacaoLista
  ,Prioridade                 -- mantém a prioridade original da campanha
  ,FlagCarteira
  ,Responsavel
  ,ClassificacaoPeriodo
FROM CTE_PONTUAL

ORDER BY ClassificacaoLista, Prioridade

);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Tabela Final

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS avenue_intelligence_allocation.modelo_alocacao.fact_produtos_recomendados (

Date DATE COMMENT 'Data de Referência'
,DimTimeSK STRING COMMENT 'Data de Referência (string)'
,Symbol STRING COMMENT 'ISIN/Ticker do produto'
,Product_N3 STRING COMMENT 'Classe do produto'
,Categoria STRING COMMENT 'Categoria do produto'
,Prioridade INT COMMENT 'Ordem de prioridade do produto'
,Descricao STRING COMMENT 'Descricao do produto'
,SellingPoints STRING COMMENT 'Selling points do produto'
,ClassificacaoLista STRING COMMENT 'Classificação da lista de recomendação'
,FlagCarteira INT COMMENT 'Flag de inclusão na carteira automática'

);

-- COMMAND ----------

DELETE FROM avenue_intelligence_allocation.modelo_alocacao.fact_produtos_recomendados
WHERE Date = DATE_ADD(CURRENT_DATE(), -1);

-- COMMAND ----------

INSERT INTO avenue_intelligence_allocation.modelo_alocacao.fact_produtos_recomendados (

WITH CTE_UNION AS (

SELECT * FROM BONDS_RECOMENDADOS
UNION ALL SELECT * FROM ETFS_RECOMENDADOS
UNION ALL SELECT * FROM FUNDOS_RECOMENDADOS
-- UNION ALL SELECT * FROM STOCKS_RECOMENDADOS
UNION ALL SELECT * FROM UCITS_RECOMENDADOS

)

SELECT
  RefDate AS Date
  ,DimTimeSK
  ,Symbol
  ,Product_N3
  ,Categoria AS AvenueCategoryId
  ,Prioridade
  ,CAST(NULL AS STRING) AS Descricao
  ,CAST(NULL AS STRING) AS SellingPoints
  ,ClassificacaoLista
  ,FlagCarteira
FROM CTE_UNION

);
