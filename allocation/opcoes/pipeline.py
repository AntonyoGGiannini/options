"""Pipeline de cálculo de métricas por cadeia de opções (calls e puts)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.models.black_scholes import (
    calcular_prob_exercicio_put_vetor,
    calcular_prob_exercicio_risk_neutral_vetor,
)
from allocation.models.empirical import calcular_probabilidade_empirica_batch
from allocation.models.greeks import calcular_greeks_call, calcular_greeks_put
from allocation.models.volatility import volatilidade_realizada


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


def preparar_opcoes_para_modelo(
    df_opcoes,
    preco_atual,
    taxa_livre_risco,
    dividend_yield,
    usar_premio,
    t_min=0,
    t_max=365,
    dias_ano=365,
    historico_precos=None,
    usar_prob_d2=True,
    usar_prob_empirica=True,
    min_amostras_empirica=30,
    liquidez_volume_min=100,
    liquidez_open_interest_min=500,
    liquidez_spread_max=0.15,
    tipo="call",
):
    """
    Calcula métricas de contrato por cadeia de opções (calls ou puts).
    Flags usar_prob_d2 / usar_prob_empirica permitem ligar/desligar cada modelo.
    prob_exercicio_final = max(prob_exercicio_d2, prob_empirica) — conservador.

    tipo: "call" (default) ou "put". Para puts: prob de exercício = N(−d2),
    greeks de put, prob empírica conta quedas até o strike e
    distancia_strike_pct = 1 − strike/spot (positivo = OTM abaixo do spot, mesma
    semântica de "distância OTM mínima" do filtro).

    Premissas:
    - Greeks e prob d2 assumem exercício europeu (Black-Scholes). O flag
      risco_atribuicao_antecipada sinaliza contratos com |delta| ≥ 0.70 onde o
      exercício antecipado é mais provável (calls: condicionado a dividendo;
      puts ITM profundas: risco por juros, independente de dividendo).
    - prob_d2 (risk-neutral) e prob_empirica (mundo real) são medidas distintas;
      combiná-las via max é conservador mas heterogêneo por construção.

    Convenção de tempo:
    - T e todas as anualizações usam dias-calendário sobre ``dias_ano``
      (ACT/365 por padrão), a convenção usual de Black-Scholes e do decaimento
      do prêmio. Para base de pregões, use ``dias_ano = 252`` na config.
    - A prob_empirica usa dias úteis (``np.busday_count``), coerente com a
      série histórica de pregões. Não é inconsistência: são domínios distintos.
    """
    if tipo not in {"call", "put"}:
        raise ValueError("tipo deve ser 'call' ou 'put'")

    if df_opcoes.empty:
        return df_opcoes.copy()

    df = df_opcoes.copy()

    # garante colunas de liquidez (robustez para mocks/dados sem mid/spread_pct)
    if "mid" not in df.columns:
        df["mid"] = (df["bid"] + df["ask"]) / 2
    if "spread_pct" not in df.columns:
        df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"]

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

    if tipo == "call":
        df["distancia_strike_pct"] = (df["strike"] / df["preco_atual"]) - 1
    else:
        df["distancia_strike_pct"] = 1 - (df["strike"] / df["preco_atual"])
    df["retorno_necessario"] = df["distancia_strike_pct"]
    df["retorno_premio_pct"] = df["premio"] / df["preco_atual"]

    # guarda contra divisão por zero antes de anualizar
    df = df[df["dias_vencimento"] > 0].copy()

    df["retorno_anualizado_pct"] = df["retorno_premio_pct"] * (dias_ano / df["dias_vencimento"])
    df["rendimento"] = df["premio"] / preco_atual

    df = df[(df["dias_vencimento"] >= t_min) & (df["dias_vencimento"] <= t_max)].copy()

    # --- liquidez: flag (não descarta) para o ranking e a matriz completa ---
    df["passou_liquidez"] = (
        (df["volume"] >= liquidez_volume_min)
        & (df["openInterest"] >= liquidez_open_interest_min)
        & (df["spread_pct"] <= liquidez_spread_max)
    )

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
        calcular_prob = (
            calcular_prob_exercicio_risk_neutral_vetor
            if tipo == "call"
            else calcular_prob_exercicio_put_vetor
        )
        df["prob_exercicio"] = calcular_prob(
            df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
            df["T"].to_numpy(), taxa_livre_risco, dividend_yield, iv_usada
        )
    else:
        df["prob_exercicio"] = np.nan

    # --- Greeks (Black-Scholes) ---
    calcular_greeks = calcular_greeks_call if tipo == "call" else calcular_greeks_put
    greeks = calcular_greeks(
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
    # antecipado próximo à data ex-dividendo. Puts ITM profundas têm risco por
    # juros (independe de dividendo).
    if tipo == "call":
        df["risco_atribuicao_antecipada"] = (dividend_yield > 0) & (df["delta"] >= 0.70)
    else:
        df["risco_atribuicao_antecipada"] = df["delta"] <= -0.70

    # --- prob_empirica (histórico, janelas não-sobrepostas) ---
    if usar_prob_empirica and historico_precos is not None and len(historico_precos) > 0:
        probs_emp, usa_emp = calcular_probabilidade_empirica_batch(
            historico_precos,
            df["preco_atual"].to_numpy(),
            df["strike"].to_numpy(),
            df["dias_uteis_ate_vencimento"].to_numpy(),
            min_amostras=min_amostras_empirica,
            direcao="acima" if tipo == "call" else "abaixo",
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


def preparar_calls_para_modelo(df_calls, *args, **kwargs):
    """Métricas da cadeia de calls — ver ``preparar_opcoes_para_modelo``."""
    kwargs["tipo"] = "call"
    return preparar_opcoes_para_modelo(df_calls, *args, **kwargs)


def preparar_puts_para_modelo(df_puts, *args, **kwargs):
    """Métricas da cadeia de puts — ver ``preparar_opcoes_para_modelo``."""
    kwargs["tipo"] = "put"
    return preparar_opcoes_para_modelo(df_puts, *args, **kwargs)
