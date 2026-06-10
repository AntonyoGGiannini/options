"""Estratégias multi-perna: bull call spread e iron condor.

Convenção de prêmio por perna: a perna comprada usa ``ask`` e a vendida usa
``bid`` (conservador), independente de ``config.usar_premio`` do screener.

Probabilidade de lucro risk-neutral via N(d2) no break-even (bull call) ou
entre os break-evens (iron condor), reutilizando models/black_scholes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado
from allocation.logging_setup import obter_logger
from allocation.models.black_scholes import calcular_prob_exercicio_risk_neutral_vetor
from allocation.opcoes.pipeline import (
    preparar_calls_para_modelo,
    preparar_puts_para_modelo,
)

logger = obter_logger(__name__)

_COLUNAS_PERNA = [
    "expiration",
    "strike",
    "premio",
    "iv_usada",
    "passou_liquidez",
    "T",
    "dias_vencimento",
]


def _preparar_perna(
    df_opcoes, dados: DadosMercado, config: Config, usar_premio: str, tipo: str
) -> pd.DataFrame:
    """Pipeline de uma perna (sem modelos de probabilidade — a prob de lucro do
    spread é calculada no break-even, não por perna)."""
    if df_opcoes.empty:
        return pd.DataFrame(columns=_COLUNAS_PERNA)
    preparar = preparar_calls_para_modelo if tipo == "call" else preparar_puts_para_modelo
    perna = preparar(
        df_opcoes,
        preco_atual=dados.preco_atual,
        taxa_livre_risco=config.taxa_livre_risco,
        dividend_yield=config.dividend_para(dados.ativo),
        usar_premio=usar_premio,
        t_min=config.min_dias,
        t_max=config.max_dias,
        dias_ano=config.dias_ano,
        historico_precos=dados.historico_precos,
        usar_prob_d2=False,
        usar_prob_empirica=False,
        liquidez_volume_min=config.liquidez_volume_min,
        liquidez_open_interest_min=config.liquidez_open_interest_min,
        liquidez_spread_max=config.liquidez_spread_max,
    )
    if perna.empty:
        return pd.DataFrame(columns=_COLUNAS_PERNA)
    return perna[_COLUNAS_PERNA].copy()


def avaliar_bull_call_spreads(
    dados: DadosMercado,
    config: Config,
    largura_max_pct: float = 0.15,
    max_por_vencimento: int = 20,
) -> pd.DataFrame:
    """Avalia bull call spreads (compra K1, vende K2 > K1, mesmo vencimento).

    Considera pernas compradas com strike próximo do spot (até
    ``largura_max_pct`` de distância) e largura K2−K1 ≤ largura_max_pct × spot.
    Para cada par: débito (ask da comprada − bid da vendida + custos por ação),
    lucro máximo, perda máxima (= débito), break-even e probabilidade de lucro
    N(d2) no break-even com IV interpolada entre as pernas.
    ``score_spread = (lucro_max / debito) × prob_lucro``. Exige liquidez nas
    duas pernas e lucro máximo positivo. Top ``max_por_vencimento`` por
    vencimento, ordenado por score.
    """
    spot = dados.preco_atual
    compra = _preparar_perna(dados.df_calls, dados, config, "ask", "call")
    venda = _preparar_perna(dados.df_calls, dados, config, "bid", "call")
    if compra.empty or venda.empty:
        logger.info("[%s] Sem calls suficientes para bull call spread.", dados.ativo)
        return pd.DataFrame()

    # perna comprada perto do spot (spread direcional, não deep ITM/OTM)
    banda = largura_max_pct * spot
    compra = compra[(compra["strike"] >= spot - banda) & (compra["strike"] <= spot + banda)]

    pares = compra.merge(venda, on="expiration", suffixes=("_compra", "_venda"))
    pares = pares[
        (pares["strike_venda"] > pares["strike_compra"])
        & (pares["strike_venda"] - pares["strike_compra"] <= banda)
    ].copy()
    if pares.empty:
        logger.info("[%s] Nenhum par de strikes viável para bull call spread.", dados.ativo)
        return pd.DataFrame()

    custo_compra_por_acao = config.custo_compra / config.tamanho_contrato
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato

    pares["largura"] = pares["strike_venda"] - pares["strike_compra"]
    pares["debito"] = (
        pares["premio_compra"]
        - pares["premio_venda"]
        + custo_compra_por_acao
        + custo_venda_por_acao
    )
    pares["lucro_max"] = pares["largura"] - pares["debito"]
    pares["perda_max"] = pares["debito"]
    pares["breakeven"] = pares["strike_compra"] + pares["debito"]
    pares["liquidez_ok"] = pares["passou_liquidez_compra"] & pares["passou_liquidez_venda"]

    pares = pares[(pares["debito"] > 0) & (pares["lucro_max"] > 0) & pares["liquidez_ok"]].copy()
    if pares.empty:
        logger.info("[%s] Nenhum bull call spread com lucro possível e liquidez.", dados.ativo)
        return pd.DataFrame()

    # IV no break-even interpolada linearmente entre as IVs usadas das pernas
    frac = ((pares["breakeven"] - pares["strike_compra"]) / pares["largura"]).clip(0, 1)
    iv_be = pares["iv_usada_compra"] + frac * (pares["iv_usada_venda"] - pares["iv_usada_compra"])

    # prob de lucro: terminar acima do break-even (risk-neutral)
    pares["prob_lucro"] = calcular_prob_exercicio_risk_neutral_vetor(
        spot,
        pares["breakeven"].to_numpy(),
        pares["T_compra"].to_numpy(),
        config.taxa_livre_risco,
        config.dividend_para(dados.ativo),
        iv_be.to_numpy(),
    )
    pares["retorno_max_pct"] = pares["lucro_max"] / pares["debito"]
    pares["score_spread"] = pares["retorno_max_pct"] * pares["prob_lucro"]

    pares["ativo"] = dados.ativo
    pares = pares.rename(
        columns={
            "strike_compra": "strike_long",
            "strike_venda": "strike_short",
            "premio_compra": "premio_long",
            "premio_venda": "premio_short",
            "dias_vencimento_compra": "dias_vencimento",
        }
    )
    colunas = [
        "ativo",
        "expiration",
        "dias_vencimento",
        "strike_long",
        "strike_short",
        "premio_long",
        "premio_short",
        "largura",
        "debito",
        "lucro_max",
        "perda_max",
        "breakeven",
        "retorno_max_pct",
        "prob_lucro",
        "score_spread",
        "liquidez_ok",
    ]
    pares = pares[colunas].sort_values("score_spread", ascending=False)
    pares = pares.groupby("expiration", group_keys=False).head(max_por_vencimento)
    return pares.sort_values("score_spread", ascending=False, ignore_index=True)


def _spreads_credito_adjacentes(
    perna_venda: pd.DataFrame, perna_compra: pd.DataFrame, lado: str
) -> pd.DataFrame:
    """Spreads de crédito com strikes adjacentes (perna comprada vizinha da
    vendida): put = proteção no strike imediatamente abaixo; call = no
    imediatamente acima. Retorna um spread por strike vendido."""
    base = perna_venda.merge(
        perna_compra[["expiration", "strike", "premio", "passou_liquidez"]],
        on=["expiration", "strike"],
        suffixes=("_venda", "_compra"),
    )
    if base.empty:
        return base
    asc = lado == "put"  # put: protege abaixo; call: protege acima
    base = base.sort_values(["expiration", "strike"], ascending=[True, asc])
    grupo = base.groupby("expiration")
    base["strike_protecao"] = grupo["strike"].shift(1)
    base["premio_protecao"] = grupo["premio_compra"].shift(1)
    base["liquidez_protecao"] = grupo["passou_liquidez_compra"].shift(1)
    base = base.dropna(subset=["strike_protecao"]).copy()
    base["credito"] = base["premio_venda"] - base["premio_protecao"]
    base["largura"] = (base["strike"] - base["strike_protecao"]).abs()
    base["liquidez_ok"] = base["passou_liquidez_venda"] & base["liquidez_protecao"].astype(bool)
    return base


def avaliar_iron_condors(
    dados: DadosMercado,
    config: Config,
    max_por_vencimento: int = 10,
) -> pd.DataFrame:
    """Avalia iron condors (bull put spread + bear call spread OTM, strikes
    adjacentes em cada asa).

    Exige cadeia de puts (``dados.df_puts``); sem ela, loga e retorna vazio.
    Para cada combinação put-spread × call-spread no mesmo vencimento com
    strike_put_short < spot < strike_call_short: crédito líquido, perda máxima
    (maior largura − crédito), break-evens e probabilidade de terminar entre
    eles (N(d2) no BE inferior − N(d2) no BE superior, risk-neutral).
    ``score_condor = (credito / perda_max) × prob_lucro``.
    """
    if dados.df_puts.empty:
        logger.info("[%s] Sem cadeia de puts — iron condor indisponível.", dados.ativo)
        return pd.DataFrame()

    spot = dados.preco_atual
    puts_venda = _preparar_perna(dados.df_puts, dados, config, "bid", "put")
    puts_compra = _preparar_perna(dados.df_puts, dados, config, "ask", "put")
    calls_venda = _preparar_perna(dados.df_calls, dados, config, "bid", "call")
    calls_compra = _preparar_perna(dados.df_calls, dados, config, "ask", "call")
    if puts_venda.empty or calls_venda.empty:
        logger.info("[%s] Sem pernas suficientes para iron condor.", dados.ativo)
        return pd.DataFrame()

    asa_put = _spreads_credito_adjacentes(
        puts_venda[puts_venda["strike"] < spot], puts_compra, "put"
    )
    asa_call = _spreads_credito_adjacentes(
        calls_venda[calls_venda["strike"] > spot], calls_compra, "call"
    )
    if asa_put.empty or asa_call.empty:
        logger.info("[%s] Sem asas OTM viáveis para iron condor.", dados.ativo)
        return pd.DataFrame()

    # cap combinatório: melhores asas (maior crédito) por vencimento
    asa_put = (
        asa_put.sort_values("credito", ascending=False)
        .groupby("expiration", group_keys=False)
        .head(max_por_vencimento)
    )
    asa_call = (
        asa_call.sort_values("credito", ascending=False)
        .groupby("expiration", group_keys=False)
        .head(max_por_vencimento)
    )

    condors = asa_put.merge(asa_call, on="expiration", suffixes=("_put", "_call"))
    if condors.empty:
        logger.info("[%s] Nenhum vencimento com as duas asas do condor.", dados.ativo)
        return pd.DataFrame()

    custo_por_acao = 2 * (config.custo_venda + config.custo_compra) / config.tamanho_contrato
    condors["credito"] = condors["credito_put"] + condors["credito_call"] - custo_por_acao
    condors["largura_max"] = np.maximum(condors["largura_put"], condors["largura_call"])
    condors["perda_max"] = condors["largura_max"] - condors["credito"]
    condors["breakeven_inferior"] = condors["strike_put"] - condors["credito"]
    condors["breakeven_superior"] = condors["strike_call"] + condors["credito"]
    condors["liquidez_ok"] = condors["liquidez_ok_put"] & condors["liquidez_ok_call"]

    condors = condors[
        (condors["credito"] > 0) & (condors["perda_max"] > 0) & condors["liquidez_ok"]
    ].copy()
    if condors.empty:
        logger.info("[%s] Nenhum iron condor com crédito positivo e liquidez.", dados.ativo)
        return pd.DataFrame()

    q = config.dividend_para(dados.ativo)
    # prob de terminar entre os break-evens: N(d2) é a prob de S_T > K, então
    # prob(BE_inf < S_T < BE_sup) = N(d2)(BE_inf) − N(d2)(BE_sup). IV de cada
    # break-even = IV usada do strike vendido da asa correspondente.
    prob_acima_inf = calcular_prob_exercicio_risk_neutral_vetor(
        spot,
        condors["breakeven_inferior"].to_numpy(),
        condors["T_put"].to_numpy(),
        config.taxa_livre_risco,
        q,
        condors["iv_usada_put"].to_numpy(),
    )
    prob_acima_sup = calcular_prob_exercicio_risk_neutral_vetor(
        spot,
        condors["breakeven_superior"].to_numpy(),
        condors["T_call"].to_numpy(),
        config.taxa_livre_risco,
        q,
        condors["iv_usada_call"].to_numpy(),
    )
    condors["prob_lucro"] = np.clip(prob_acima_inf - prob_acima_sup, 0.0, 1.0)
    condors["score_condor"] = (condors["credito"] / condors["perda_max"]) * condors["prob_lucro"]

    condors["ativo"] = dados.ativo
    condors = condors.rename(
        columns={
            "strike_put": "strike_put_short",
            "strike_protecao_put": "strike_put_long",
            "strike_call": "strike_call_short",
            "strike_protecao_call": "strike_call_long",
            "dias_vencimento_put": "dias_vencimento",
        }
    )
    colunas = [
        "ativo",
        "expiration",
        "dias_vencimento",
        "strike_put_long",
        "strike_put_short",
        "strike_call_short",
        "strike_call_long",
        "credito",
        "largura_max",
        "perda_max",
        "breakeven_inferior",
        "breakeven_superior",
        "prob_lucro",
        "score_condor",
        "liquidez_ok",
    ]
    condors = condors[colunas].sort_values("score_condor", ascending=False)
    condors = condors.groupby("expiration", group_keys=False).head(max_por_vencimento)
    return condors.sort_values("score_condor", ascending=False, ignore_index=True)
