"""Probabilidade de exercício risk-neutral (Black-Scholes N(d2))."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm


def calcular_prob_exercicio_risk_neutral(S0, K, T, r, q, iv):
    """Probabilidade risk-neutral (Black-Scholes d2) de a call terminar ITM."""
    if T <= 0 or iv <= 0 or K <= 0 or S0 <= 0:
        return np.nan
    d2 = (np.log(S0 / K) + (r - q - 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
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
