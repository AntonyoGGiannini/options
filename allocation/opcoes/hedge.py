"""Proteção de posição via opções: protective put e collar.

Convenção de prêmio por perna: a perna comprada usa ``ask`` e a vendida usa
``bid`` (conservador), independente de ``config.usar_premio`` do screener.

Probabilidades por perna: prob_uso_put = N(−d2) da put (chance de a proteção
terminar ITM); prob_exercicio_call = N(d2) da call (chance de entregar as
ações no teto).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado
from allocation.logging_setup import obter_logger
from allocation.opcoes.pipeline import (
    preparar_calls_para_modelo,
    preparar_puts_para_modelo,
)

logger = obter_logger(__name__)

_EPS_CUSTO = 1e-6


def _preparar_pernas(dados: DadosMercado, config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pipelines das duas pernas: put comprada (ask) e call vendida (bid)."""
    base = dict(
        preco_atual=dados.preco_atual,
        taxa_livre_risco=config.taxa_livre_risco,
        dividend_yield=config.dividend_para(dados.ativo),
        t_min=config.min_dias,
        t_max=config.max_dias,
        dias_ano=config.dias_ano,
        historico_precos=dados.historico_precos if config.usar_prob_empirica else None,
        usar_prob_d2=config.usar_prob_d2,
        usar_prob_empirica=config.usar_prob_empirica,
        min_amostras_empirica=config.min_amostras_empirica,
        liquidez_volume_min=config.liquidez_volume_min,
        liquidez_open_interest_min=config.liquidez_open_interest_min,
        liquidez_spread_max=config.liquidez_spread_max,
    )
    df_puts = (
        preparar_puts_para_modelo(dados.df_puts, usar_premio="ask", **base)
        if not dados.df_puts.empty
        else pd.DataFrame()
    )
    df_calls = preparar_calls_para_modelo(dados.df_calls, usar_premio="bid", **base)
    return df_puts, df_calls


def avaliar_protective_put(
    dados: DadosMercado,
    config: Config,
    preco_custo: float | None = None,
) -> pd.DataFrame:
    """Avalia puts de proteção para uma posição no ativo.

    Considera apenas puts OTM/ATM (strike <= spot) na janela [min_dias,
    max_dias]: custo da proteção (ask + custo de compra por ação), piso
    garantido (strike − custo), perda máxima vs. spot (ou vs. custo médio, se
    informado), custo anualizado como fração do spot e probabilidade de uso
    N(−d2). Ordenado por perda máxima.
    """
    df_puts, _ = _preparar_pernas(dados, config)
    if df_puts.empty:
        logger.info("[%s] Sem puts para proteção na fonte de dados.", dados.ativo)
        return pd.DataFrame()

    spot = dados.preco_atual
    df_puts = df_puts[df_puts["strike"] <= spot]
    if df_puts.empty:
        logger.info("[%s] Sem puts OTM/ATM para proteção.", dados.ativo)
        return pd.DataFrame()
    base = preco_custo if preco_custo is not None else spot
    custo_compra_por_acao = config.custo_compra / config.tamanho_contrato

    df = df_puts.copy()
    df["custo_protecao"] = df["premio"] + custo_compra_por_acao
    df["piso"] = df["strike"] - df["custo_protecao"]
    df["perda_max_pct"] = (base - df["piso"]) / base
    df["custo_protecao_pct"] = df["custo_protecao"] / spot
    df["custo_anualizado_pct"] = df["custo_protecao_pct"] / df["T"]
    df["prob_uso"] = df["prob_exercicio_final"]
    # delta da posição protegida: 1 (ação) + delta da put comprada
    df["delta_posicao"] = 1.0 + df["delta"]

    df["ativo"] = dados.ativo
    colunas = [
        "ativo",
        "strike",
        "expiration",
        "dias_vencimento",
        "premio",
        "custo_protecao",
        "custo_protecao_pct",
        "custo_anualizado_pct",
        "piso",
        "perda_max_pct",
        "prob_uso",
        "delta_posicao",
        "passou_liquidez",
        "iv_usada",
        "fonte_vol",
    ]
    df = df[[c for c in colunas if c in df.columns]].copy()
    return df.sort_values("perda_max_pct", ignore_index=True)


def avaliar_collar(
    dados: DadosMercado,
    config: Config,
    preco_custo: float | None = None,
    max_por_vencimento: int = 5,
) -> pd.DataFrame:
    """Avalia collars (put comprada + call vendida) para uma posição no ativo.

    Cruza, por vencimento, as ``max_por_vencimento`` melhores puts (menor custo
    de proteção) e calls (maior prêmio) com strike_put < spot < strike_call.
    Para cada par: custo líquido (ask da put − bid da call + custos), piso,
    teto, perda/ganho máximos e ``score_hedge = perda_evitada_pct /
    max(custo_liquido_pct, eps)`` — proteção obtida por unidade de custo.
    Ordenado por score_hedge.
    """
    df_puts, df_calls = _preparar_pernas(dados, config)
    if df_puts.empty or df_calls.empty:
        logger.info("[%s] Sem pernas suficientes para collar.", dados.ativo)
        return pd.DataFrame()

    spot = dados.preco_atual
    base = preco_custo if preco_custo is not None else spot
    custo_compra_por_acao = config.custo_compra / config.tamanho_contrato
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato

    puts_otm = df_puts[df_puts["strike"] < spot]
    calls_otm = df_calls[df_calls["strike"] > spot]

    linhas = []
    vencimentos = sorted(set(puts_otm["expiration"]) & set(calls_otm["expiration"]))
    for expiration in vencimentos:
        # cap combinatório: melhores puts (proteção mais barata) × melhores
        # calls (mais prêmio) do vencimento
        p = puts_otm[puts_otm["expiration"] == expiration].nsmallest(max_por_vencimento, "premio")
        c = calls_otm[calls_otm["expiration"] == expiration].nlargest(max_por_vencimento, "premio")
        for _, put in p.iterrows():
            for _, call in c.iterrows():
                custo_liquido = (
                    put["premio"] + custo_compra_por_acao - call["premio"] + custo_venda_por_acao
                )
                piso = put["strike"] - custo_liquido
                teto = call["strike"] - custo_liquido
                linhas.append(
                    {
                        "ativo": dados.ativo,
                        "expiration": expiration,
                        "dias_vencimento": put["dias_vencimento"],
                        "strike_put": put["strike"],
                        "strike_call": call["strike"],
                        "premio_put": put["premio"],
                        "premio_call": call["premio"],
                        "custo_liquido": custo_liquido,
                        "custo_liquido_pct": custo_liquido / spot,
                        "piso": piso,
                        "teto": teto,
                        "perda_max_pct": (base - piso) / base,
                        "ganho_max_pct": (teto - base) / base,
                        "prob_uso_put": put["prob_exercicio_final"],
                        "prob_exercicio_call": call["prob_exercicio_final"],
                        "custo_anualizado_pct": (custo_liquido / spot) / put["T"],
                        "liquidez_ok": bool(put["passou_liquidez"] and call["passou_liquidez"]),
                    }
                )

    if not linhas:
        logger.info("[%s] Nenhum par put/call viável para collar.", dados.ativo)
        return pd.DataFrame()

    df = pd.DataFrame(linhas)
    # perda evitada vs. posição sem proteção (que pode perder tudo): a perda
    # fica limitada a perda_max_pct — o restante (1 − perda_max) é o protegido.
    df["perda_evitada_pct"] = (1.0 - df["perda_max_pct"]).clip(lower=0)
    df["score_hedge"] = df["perda_evitada_pct"] / np.maximum(df["custo_liquido_pct"], _EPS_CUSTO)
    return df.sort_values("score_hedge", ascending=False, ignore_index=True)
