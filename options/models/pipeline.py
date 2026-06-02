"""Pipeline de cálculo de métricas por cadeia de opções."""

from __future__ import annotations

import numpy as np
import pandas as pd

from options.models.black_scholes import calcular_prob_exercicio_risk_neutral_vetor
from options.models.empirical import calcular_probabilidade_empirica_batch
from options.models.greeks import calcular_greeks_call
from options.models.monte_carlo import calcular_prob_acima_strike_monte_carlo_batch
from options.models.volatility import volatilidade_realizada


def calcular_premio_vetor(df, usar_premio):
    """Seleciona a coluna de prêmio conforme a convenção escolhida."""
    if usar_premio == "bid":
        return df["bid"]
    if usar_premio == "ask":
        return df["ask"]
    if usar_premio == "lastPrice":
        return df["lastPrice"]
    if usar_premio == "mid":
        mid_valido = (
            df["bid"].notna() & df["ask"].notna()
            & (df["bid"] > 0) & (df["ask"] > 0)
        )
        return ((df["bid"] + df["ask"]) / 2).where(mid_valido, df["lastPrice"])
    raise ValueError("usar_premio deve ser: bid, ask, lastPrice ou mid")


def preparar_calls_para_modelo(
    df_calls,
    preco_atual,
    taxa_livre_risco,
    dividend_yield,
    usar_premio,
    mu=0.0,
    n_simulacoes=10000,
    seed=None,
    batch_size=500,
    t_min=0,
    t_max=365,
    dias_ano=365,
    historico_precos=None,
    usar_prob_d2=True,
    usar_prob_mc=True,
    usar_prob_empirica=True,
    min_amostras_empirica=30,
):
    """
    Calcula métricas de contrato por cadeia de opções.
    Flags usar_prob_d2 / usar_prob_mc / usar_prob_empirica permitem ligar/desligar
    cada modelo independentemente.
    prob_exercicio_final = max(prob_exercicio, prob_empirica) — abordagem conservadora.
    """
    if df_calls.empty:
        return df_calls.copy()

    df = df_calls.copy()

    df["preco_atual"] = preco_atual
    df["dias_vencimento"] = (
        pd.to_datetime(df["expiration"]).dt.normalize()
        - pd.Timestamp.today().normalize()
    ).dt.days

    hoje = pd.Timestamp.today().normalize().date()
    df["dias_uteis_ate_vencimento"] = df["expiration"].apply(
        lambda x: int(np.busday_count(hoje, pd.Timestamp(x).date()))
    )

    df["T"] = df["dias_vencimento"] / dias_ano
    df["premio"] = calcular_premio_vetor(df, usar_premio)

    df["distancia_strike_pct"] = (df["strike"] / df["preco_atual"]) - 1
    df["retorno_necessario"] = df["distancia_strike_pct"]
    df["retorno_premio_pct"] = df["premio"] / df["preco_atual"]
    df["retorno_anualizado_pct"] = df["retorno_premio_pct"] * (dias_ano / df["dias_vencimento"])
    df["rendimento"] = df["premio"] / preco_atual

    df = df[(df["dias_vencimento"] >= t_min) & (df["dias_vencimento"] <= t_max)].copy()

    # --- volatilidade efetiva: IV implícita com fallback para vol histórica ---
    iv = df["impliedVolatility"].to_numpy(dtype=float)
    iv_valida = np.isfinite(iv) & (iv > 0)
    vol_hist = (
        volatilidade_realizada(historico_precos)
        if historico_precos is not None and len(historico_precos) > 0
        else np.nan
    )
    iv_usada = np.where(iv_valida, iv, vol_hist)
    df["iv_usada"] = iv_usada
    df["fonte_vol"] = np.where(iv_valida, "implicita", "historica")

    # --- prob_exercicio (d2 / risk-neutral) ---
    if usar_prob_d2:
        df["prob_exercicio"] = calcular_prob_exercicio_risk_neutral_vetor(
            df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
            df["T"].to_numpy(), taxa_livre_risco, dividend_yield, iv_usada
        )
    else:
        df["prob_exercicio"] = np.nan

    # --- prob_exercicio_mc (Monte Carlo) ---
    if usar_prob_mc:
        df["prob_exercicio_mc"] = calcular_prob_acima_strike_monte_carlo_batch(
            df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
            df["T"].to_numpy(), mu=mu, sigma=iv_usada,
            q=dividend_yield, n_simulacoes=n_simulacoes,
            seed=seed, batch_size=batch_size
        )
    else:
        df["prob_exercicio_mc"] = np.nan

    # --- Greeks (Black-Scholes) ---
    greeks = calcular_greeks_call(
        df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
        df["T"].to_numpy(), taxa_livre_risco, dividend_yield, iv_usada,
    )
    df["delta"] = greeks["delta"]
    df["gamma"] = greeks["gamma"]
    df["vega"] = greeks["vega"]
    df["theta"] = greeks["theta"]
    df["rho"] = greeks["rho"]

    # --- risco de atribuição antecipada (heurística) ---
    # Calls americanas com dividendo (q>0) e delta alto têm risco de exercício
    # antecipado próximo à data ex-dividendo.
    df["risco_atribuicao_antecipada"] = (dividend_yield > 0) & (df["delta"] >= 0.70)

    # --- prob_empirica (histórico) ---
    if usar_prob_empirica and historico_precos is not None and len(historico_precos) > 0:
        probs_emp, usa_emp = calcular_probabilidade_empirica_batch(
            historico_precos,
            df["preco_atual"].to_numpy(),
            df["strike"].to_numpy(),
            df["dias_uteis_ate_vencimento"].to_numpy(),
            min_amostras=min_amostras_empirica,
        )
        df["prob_empirica"] = probs_emp
        df["usa_prob_empirica"] = usa_emp
    else:
        df["prob_empirica"] = np.nan
        df["usa_prob_empirica"] = False

    # --- prob_exercicio_final = max(d2, empirica) ---
    df["prob_exercicio_final"] = df["prob_exercicio"]
    mascara = df["usa_prob_empirica"] & df["prob_empirica"].notna()
    df.loc[mascara, "prob_exercicio_final"] = np.fmax(
        df.loc[mascara, "prob_exercicio"],
        df.loc[mascara, "prob_empirica"],
    )

    return df
