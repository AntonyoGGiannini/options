# Databricks notebook source
# MAGIC %md
# MAGIC ### Parâmetros

# COMMAND ----------

# CLIENTE
AvenueAccountId = 'f90b3e37-0e98-45c7-9c02-61f2cc6669f6'
ModelPortfolioName = 'AvenueExpandida'

# PARÂMETROS
Rebalanceamento = 0
CaixaAdicional = 100000

# COMMAND ----------

# MAGIC %md
# MAGIC ### Posição Atual

# COMMAND ----------

query_c = f"""
    SELECT c.Date, c.AvenueAccountId, p2.AvenueCategoryId, p.Product_N3, p.Product_N4, p.Product, p.Symbol, c.TotalNetDol
    FROM av_datalake_l3.data_warehouse.fact_custody c
    JOIN av_datalake_l3.data_warehouse.dim_product p ON p.DimProductSK = c.DimProductSK
    LEFT JOIN avenue_intelligence_allocation.general.fact_product p2 ON p2.DimProductSK = c.DimProductSK AND p2.DimTimeSK = c.DimTimeSK
    WHERE
        c.Date = (SELECT MAX(Date) FROM av_datalake_l3.data_warehouse.fact_custody) AND
        p.Product_N3 <> 'Balance US Banking' AND
        c.AvenueAccountId = '{AvenueAccountId}'"""

posicao_atual = spark.sql(query_c).toPandas()

# COMMAND ----------

# MAGIC %md
# MAGIC #### Posição Atual Agregada por Categoria - Sem Caixa

# COMMAND ----------

posicao_atual_agg = (
    posicao_atual[posicao_atual['Product_N3'] != 'Balance US Clearing']
    .groupby("AvenueCategoryId")
    .agg({"TotalNetDol": "sum"})
    .reset_index()
)

# COMMAND ----------

# MAGIC %md
# MAGIC #### Caixa

# COMMAND ----------

caixa = round(posicao_atual[posicao_atual['Product_N3'] == 'Balance US Clearing']['TotalNetDol'].sum(), 2)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Model Portfolio

# COMMAND ----------

query_mp = f"""
    SELECT Date, AvenueAccountId, ModelPortfolioName, CodigoPerfil, AvenueCategoryId, Peso
    FROM avenue_intelligence_allocation.modelo_alocacao.vw_model_portfolio_actual
    WHERE
        AvenueAccountId = '{AvenueAccountId}' AND
        ModelPortfolioName = '{ModelPortfolioName}'"""

model_portfolio = spark.sql(query_mp)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Otimizador

# COMMAND ----------

import numpy as np
import pandas as pd

def otimizador_caixa(model_portfolio, posicao_atual_agg, caixa, caixa_adicional=0):

    # ============================================================================
    # Otimizador de alocação de caixa — Water-filling (versão otimizada)
    # ============================================================================

    # Garante float em CAIXA (caixa e CaixaAdicional podem vir como Decimal do Spark)
    CAIXA = float(caixa_adicional) + float(caixa)

    # --- 1. Conversão única para pandas -----------------------------------------
    mp_pd = model_portfolio.toPandas() if hasattr(model_portfolio, "toPandas") else model_portfolio
    pa_pd = posicao_atual_agg.toPandas() if hasattr(posicao_atual_agg, "toPandas") else posicao_atual_agg

    # --- 2. Merge categoria x peso recomendado ----------------------------------
    carteira = (
        mp_pd[["AvenueCategoryId", "Peso"]]
        .merge(pa_pd, on="AvenueCategoryId", how="outer")
        .fillna({"Peso": 0.0, "TotalNetDol": 0.0})
        .rename(columns={"TotalNetDol": "ValorAtual"})
        .sort_values("AvenueCategoryId", ignore_index=True)
    )

    # Cast Decimal -> float ANTES de extrair pra numpy (Spark Decimal não converte
    # diretamente em np.float64 via .to_numpy(dtype=...) em algumas versões)
    carteira["ValorAtual"] = carteira["ValorAtual"].astype(float)
    carteira["Peso"]       = carteira["Peso"].astype(float)

    categoria    = carteira["AvenueCategoryId"].to_numpy()
    valor_atual  = carteira["ValorAtual"].to_numpy(dtype=np.float64)
    peso         = carteira["Peso"].to_numpy(dtype=np.float64)

    # --- 3. Patrimônio total e alvos recomendados -------------------------------
    patrimonio_total = valor_atual.sum() + CAIXA
    soma_pesos       = peso.sum()
    inv_pat          = 1.0 / patrimonio_total if patrimonio_total > 0 else 0.0

    peso_recomendado  = peso / soma_pesos if soma_pesos > 0 else np.zeros_like(peso)
    valor_recomendado = peso_recomendado * patrimonio_total

    # --- 4. Gap por categoria ---------------------------------------------------
    gap       = np.maximum(valor_recomendado - valor_atual, 0.0)
    soma_gaps = gap.sum()

    # --- 5. Water-filling vetorizado --------------------------------------------
    if soma_gaps <= CAIXA:
        compra_venda   = gap.copy()
        nivel_residual = 0.0
    else:
        gaps_sorted = np.sort(gap)[::-1]
        n           = gaps_sorted.size
        cumsum      = np.cumsum(gaps_sorted)
        k_arr       = np.arange(1, n + 1, dtype=np.float64)
        L_k         = (cumsum - CAIXA) / k_arr
        proximo     = np.append(gaps_sorted[1:], -np.inf)
        k_star      = np.argmax(L_k >= proximo)
        nivel_residual = L_k[k_star]
        compra_venda   = np.maximum(gap - nivel_residual, 0.0)

    # --- 6. Derivadas pós-alocação ----------------------------------------------
    valor_depois     = valor_atual + compra_venda
    peso_atual       = valor_atual  * inv_pat
    peso_depois      = valor_depois * inv_pat
    aderencia_atual  = np.minimum(valor_atual,  valor_recomendado) * inv_pat
    aderencia_depois = np.minimum(valor_depois, valor_recomendado) * inv_pat

    # --- 7. Linha "Caixa" -------------------------------------------------------
    caixa_usado    = float(compra_venda.sum())
    caixa_residual = CAIXA - caixa_usado

    # --- 8. Layout final em uma única construção -------------------------------
    tabela_final = pd.DataFrame({
        "AvenueCategoryId":  np.concatenate([["Caixa"], categoria,         ["TOTAL"]]),
        "ValorAtual":        np.concatenate([[CAIXA],   valor_atual,        [valor_atual.sum() + CAIXA]]),
        "PesoAtual":         np.concatenate([[CAIXA * inv_pat], peso_atual, [peso_atual.sum() + CAIXA * inv_pat]]),
        "ValorRecomendado":  np.concatenate([[0.0],     valor_recomendado, [valor_recomendado.sum()]]),
        "PesoRecomendado":   np.concatenate([[0.0],     peso_recomendado,  [peso_recomendado.sum()]]),
        "AderenciaAtual":    np.concatenate([[0.0],     aderencia_atual,   [aderencia_atual.sum()]]),
        "CompraVenda":       np.concatenate([[-caixa_usado], compra_venda, [compra_venda.sum() - caixa_usado]]),
        "ValorDepois":       np.concatenate([[caixa_residual], valor_depois, [valor_depois.sum() + caixa_residual]]),
        "PesoDepois":        np.concatenate([[caixa_residual * inv_pat], peso_depois, [peso_depois.sum() + caixa_residual * inv_pat]]),
        "AderenciaDepois":   np.concatenate([[0.0],     aderencia_depois,  [aderencia_depois.sum()]]),
    })

    return tabela_final

# COMMAND ----------

display(posicao_atual_agg)

# COMMAND ----------

tabela_final = otimizador_caixa(model_portfolio, posicao_atual_agg, caixa, CaixaAdicional)
display(tabela_final)

# COMMAND ----------

categorias_gap = tabela_final[(tabela_final['CompraVenda'] > 0) & (tabela_final['AvenueCategoryId'] != 'TOTAL')][['AvenueCategoryId', 'CompraVenda']].reset_index(drop=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Produtos Habilitados

# COMMAND ----------

query = f"""
    SELECT *
    FROM avenue_intelligence_allocation.modelo_alocacao.vw_enabled_product_client_r4
    WHERE
        AvenueAccountId = '{AvenueAccountId}' AND
        ModelPortfolioName = '{ModelPortfolioName}'
"""

produtos_disponiveis = spark.sql(query).toPandas()
display(produtos_disponiveis)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Modelo de Compra

# COMMAND ----------

import pandas as pd

# Categoria que absorve qualquer sobra do processo de alocação

def alocar_produtos(
    df_produtos: pd.DataFrame,
    df_alocacao: pd.DataFrame,
    df_posicoes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Distribui o delta de compra (CompraVenda) entre os produtos de cada
    categoria, seguindo a ordem de PrioridadeFinal.

    Considera a posição atual do cliente em cada produto: o teto de alocação
    é aplicado sobre o saldo já existente, não apenas sobre o valor a comprar.

    Regra de sobra: qualquer resíduo que não couber nos produtos da categoria
    de origem é redirecionado para AV1010. Se AV1010 também não conseguir
    absorver respeitando teto/mínima, força alocação no produto de maior
    prioridade da AV1010 ignorando o teto (a posição atual é somada à
    alocação, mas não a limita).

    Parâmetros
    ----------
    df_produtos : DataFrame
        Catálogo de produtos com Categoria, Symbol, Product_N3,
        PrioridadeFinal, aplicacao_minima, Limite.
    df_alocacao : DataFrame
        Delta por categoria com AvenueCategoryId, ValorDepois, CompraVenda.
    df_posicoes : DataFrame, opcional
        Posição atual do cliente com Symbol e TotalNetDol. Se None ou vazio,
        assume posição zero em todos os produtos.

    Retorna
    -------
    DataFrame com: Categoria, Symbol, Product_N3, PrioridadeFinal,
    ValorAlocado, PesoPortfolio, Status.
    Status ∈ {'ALOCADO', 'ALOCADO_FORCADO', 'SOBRA_CATEGORIA'}.
    """

    CATEGORIA_SOBRA = "AV1010"

    # --- Preparação ---------------------------------------------------------
    prod = df_produtos.copy()

    aloc = df_alocacao.loc[df_alocacao["AvenueCategoryId"] != "TOTAL"].copy()
    total_carteira = float(aloc["ValorDepois"].sum())

    # Guarda defensiva: sem patrimônio não há como aplicar tetos percentuais
    if total_carteira <= 0:
        return pd.DataFrame(columns=[
            "Categoria", "Symbol", "Product_N3", "PrioridadeFinal",
            "ValorAlocado", "PesoPortfolio", "Status",
        ])

    # Posições atuais → dict {symbol: valor}, agregando símbolos repetidos
    if df_posicoes is not None and not df_posicoes.empty:
        posicoes = (df_posicoes.groupby("Symbol")["TotalNetDol"]
                               .sum()
                               .astype(float)
                               .to_dict())
    else:
        posicoes = {}

    # Categorias que precisam comprar — separa AV1010 para processar por último
    alvo = aloc.loc[aloc["CompraVenda"] > 0, ["AvenueCategoryId", "CompraVenda"]]
    alvo_outras = alvo.loc[alvo["AvenueCategoryId"] != CATEGORIA_SOBRA]
    valor_av1010_proprio = float(
        alvo.loc[alvo["AvenueCategoryId"] == CATEGORIA_SOBRA, "CompraVenda"].sum()
    )

    linhas = []
    sobra_acumulada = 0.0

    # --- 1. Processa todas as categorias != AV1010 --------------------------
    for _, lcat in alvo_outras.iterrows():
        categoria = lcat["AvenueCategoryId"]
        valor_restante = float(lcat["CompraVenda"])

        produtos_cat = (prod.loc[prod["Categoria"] == categoria]
                            .sort_values("PrioridadeFinal")
                            .reset_index(drop=True))

        if produtos_cat.empty:
            # Sem produtos disponíveis na categoria — manda toda a verba pra AV1010
            sobra_acumulada += valor_restante
            continue

        for _, p in produtos_cat.iterrows():
            minima = float(p["aplicacao_minima"])
            teto_absoluto = float(p["Limite"]) * total_carteira
            posicao_atual = posicoes.get(p["Symbol"], 0.0)
            espaco_disponivel = max(teto_absoluto - posicao_atual, 0.0)

            # Estourou ou bateu o teto → pula
            if espaco_disponivel <= 0:
                continue

            # Espaço menor que mínima → pula pro próximo
            if espaco_disponivel < minima:
                continue

            if valor_restante < minima:
                break

            valor_alocavel = min(valor_restante, espaco_disponivel)
            if valor_alocavel < minima:
                continue

            linhas.append({
                "Categoria": categoria,
                "Symbol": p["Symbol"],
                "Product_N3": p.get("Product_N3"),
                "PrioridadeFinal": int(p["PrioridadeFinal"]),
                "ValorAlocado": round(valor_alocavel, 2),
                "PesoPortfolio": round(valor_alocavel / total_carteira, 6),
                "Status": "ALOCADO",
            })
            valor_restante -= valor_alocavel

        # Resíduo da categoria → vai pra AV1010
        if valor_restante > 0.005:
            sobra_acumulada += valor_restante

    # --- 2. Processa AV1010 com verba própria + sobras acumuladas -----------
    valor_av1010 = valor_av1010_proprio + sobra_acumulada

    if valor_av1010 > 0.005:
        produtos_av1010 = (prod.loc[prod["Categoria"] == CATEGORIA_SOBRA]
                               .sort_values("PrioridadeFinal")
                               .reset_index(drop=True))

        if produtos_av1010.empty:
            # Sem produtos AV1010 cadastrados — última opção, registra como sobra
            linhas.append(_sobra(CATEGORIA_SOBRA, valor_av1010))
        else:
            valor_restante = valor_av1010

            # 2a. Passada normal respeitando teto (descontando posição atual) e mínima
            for _, p in produtos_av1010.iterrows():
                minima = float(p["aplicacao_minima"])
                teto_absoluto = float(p["Limite"]) * total_carteira
                posicao_atual = posicoes.get(p["Symbol"], 0.0)
                espaco_disponivel = max(teto_absoluto - posicao_atual, 0.0)

                if espaco_disponivel <= 0:
                    continue
                if espaco_disponivel < minima:
                    continue
                if valor_restante < minima:
                    break

                valor_alocavel = min(valor_restante, espaco_disponivel)
                if valor_alocavel < minima:
                    continue

                linhas.append({
                    "Categoria": CATEGORIA_SOBRA,
                    "Symbol": p["Symbol"],
                    "Product_N3": p.get("Product_N3"),
                    "PrioridadeFinal": int(p["PrioridadeFinal"]),
                    "ValorAlocado": round(valor_alocavel, 2),
                    "PesoPortfolio": round(valor_alocavel / total_carteira, 6),
                    "Status": "ALOCADO",
                })
                valor_restante -= valor_alocavel

            # 2b. Sobra forçada: empurra resíduo no produto de maior prioridade,
            #     ignorando teto. A posição atual continua sendo somada (é
            #     consolidada se já existe linha desse símbolo), mas não limita
            #     o valor da força.
            if valor_restante > 0.005:
                p_top = produtos_av1010.iloc[0]
                symbol_top = p_top["Symbol"]

                # Procura linha existente do top priority pra consolidar
                linha_existente = next(
                    (ln for ln in linhas if ln["Symbol"] == symbol_top
                     and ln["Categoria"] == CATEGORIA_SOBRA),
                    None,
                )

                if linha_existente is not None:
                    novo_valor = linha_existente["ValorAlocado"] + valor_restante
                    linha_existente["ValorAlocado"] = round(novo_valor, 2)
                    linha_existente["PesoPortfolio"] = round(novo_valor / total_carteira, 6)
                    linha_existente["Status"] = "ALOCADO_FORCADO"
                else:
                    linhas.append({
                        "Categoria": CATEGORIA_SOBRA,
                        "Symbol": symbol_top,
                        "Product_N3": p_top.get("Product_N3"),
                        "PrioridadeFinal": int(p_top["PrioridadeFinal"]),
                        "ValorAlocado": round(valor_restante, 2),
                        "PesoPortfolio": round(valor_restante / total_carteira, 6),
                        "Status": "ALOCADO_FORCADO",
                    })

    cols = ["Categoria", "Product_N3", "Symbol",
            "PrioridadeFinal", "ValorAlocado", "PesoPortfolio", "Status"]
    return pd.DataFrame(linhas, columns=cols)


def _sobra(categoria: str, valor: float) -> dict:
    """Linha de rastreio para valor que não foi alocado na categoria."""
    return {
        "Categoria": categoria,
        "Product_N3": None,
        "Symbol": None,

        "PrioridadeFinal": None,
        "ValorAlocado": round(valor, 2),
        "PesoPortfolio": None,
        "Status": "SOBRA_CATEGORIA",
    }

# COMMAND ----------

display(produtos_disponiveis)

# COMMAND ----------

resultado = alocar_produtos(produtos_disponiveis, tabela_final, posicao_atual)
resultado.display()

# COMMAND ----------

# CategoryName, Product_N3, Symbol, ProductName, Valor, Taxas, YTW, Quantidade, Peso

query = f"""SELECT DISTINCT
    f.AvenueCategoryId,
    pc.NomeCategoria,
    pc.Categoria_N1,
    pc.Categoria_N2,
    pc.Categoria_N3,
    f.Product_N3,
    CASE
        WHEN f.Product_N3 = "Funds" THEN f.fundos_isin
        WHEN f.Product_N3 = "Bonds" THEN f.bonds_isin
        WHEN f.Product_N3 = "UCITs" THEN replace(f.fundos_ticker, '.GB', '')
        ELSE f.Symbol
    END as Symbol,
    f.ProductName,
    CASE
        WHEN f.Product_N3 = "Funds" THEN f.fundos_ongoing_charges
        WHEN f.Product_N3 = "ETF's" THEN f.etfs_expense_ratio
        ELSE 0
    END as Taxas,
    f.bonds_sector as Setor,
    CASE
        WHEN f.Product_N4 = "Certificate of Deposit" THEN f.bonds_coupon
        ELSE f.bonds_yield_to_worst
    END as YTW,
    f.bonds_spread as SpreadBonds
FROM
    avenue_intelligence_allocation.general.fact_product f
JOIN
    avenue_intelligence_allocation.general.dim_product_categoria pc ON pc.AvenueCategoryId = f.AvenueCategoryId
WHERE
    f.DimTimeSK = (SELECT MAX(DimTimeSK) FROM avenue_intelligence_allocation.general.fact_product)"""

produtos = spark.sql(query)
produtos_resultado = produtos.toPandas().merge(
    resultado,
    left_on=["Symbol"],
    right_on=["Symbol"],
    how="inner"
).sort_values('AvenueCategoryId')

display(produtos_resultado)
