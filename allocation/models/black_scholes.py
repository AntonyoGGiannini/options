"""Probabilidade de exercício risk-neutral (Black-Scholes N(d2))."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm


def preco_call_bs(S0, K, T, r, q, iv):
    """Preço de uma call europeia (Black-Scholes) com dividend yield contínuo.

    Aceita escalares ou arrays (broadcast). Retorna NaN onde os parâmetros são
    inválidos (T<=0, iv<=0, etc.).
    """
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    precos = np.full(S0_arr.shape, np.nan, dtype=float)
    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    s, k, t, v = S0_arr[validos], K_arr[validos], T_arr[validos], iv_arr[validos]
    d1 = (np.log(s / k) + (r - q + 0.5 * v**2) * t) / (v * np.sqrt(t))
    d2 = d1 - v * np.sqrt(t)
    precos[validos] = s * np.exp(-q * t) * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)
    return precos if precos.ndim else float(precos)


def preco_put_bs(S0, K, T, r, q, iv):
    """Preço de uma put europeia (Black-Scholes) com dividend yield contínuo.

    Aceita escalares ou arrays (broadcast). Retorna NaN onde os parâmetros são
    inválidos (T<=0, iv<=0, etc.).
    """
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    precos = np.full(S0_arr.shape, np.nan, dtype=float)
    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    s, k, t, v = S0_arr[validos], K_arr[validos], T_arr[validos], iv_arr[validos]
    d1 = (np.log(s / k) + (r - q + 0.5 * v**2) * t) / (v * np.sqrt(t))
    d2 = d1 - v * np.sqrt(t)
    precos[validos] = k * np.exp(-r * t) * norm.cdf(-d2) - s * np.exp(-q * t) * norm.cdf(-d1)
    return precos if precos.ndim else float(precos)


def calcular_prob_exercicio_risk_neutral(S0, K, T, r, q, iv):
    """Probabilidade risk-neutral (Black-Scholes d2) de a call terminar ITM."""
    if T <= 0 or iv <= 0 or K <= 0 or S0 <= 0:
        return np.nan
    d2 = (np.log(S0 / K) + (r - q - 0.5 * iv**2) * T) / (iv * np.sqrt(T))
    return float(norm.cdf(d2))


def calcular_prob_exercicio_risk_neutral_vetor(S0, K, T, r, q, iv):
    """Versão vetorizada de calcular_prob_exercicio_risk_neutral."""
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    probs = np.full(S0_arr.shape, np.nan, dtype=float)
    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    d2 = (
        np.log(S0_arr[validos] / K_arr[validos])
        + (r - q - 0.5 * iv_arr[validos] ** 2) * T_arr[validos]
    ) / (iv_arr[validos] * np.sqrt(T_arr[validos]))
    probs[validos] = norm.cdf(d2)
    return probs


def calcular_prob_exercicio_put_vetor(S0, K, T, r, q, iv):
    """Probabilidade risk-neutral N(−d2) de a put terminar ITM (S_T < K).

    Complemento exato da prob da call: N(d2) + N(−d2) = 1.
    """
    probs_call = calcular_prob_exercicio_risk_neutral_vetor(S0, K, T, r, q, iv)
    return 1.0 - probs_call
