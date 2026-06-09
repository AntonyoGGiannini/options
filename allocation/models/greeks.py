"""Greeks de Black-Scholes para opções europeias (com dividend yield contínuo).

Convenções:
- ``theta`` é por ano (dividir por 365 para theta diário);
- ``vega`` é por variação de 1.0 (100 p.p.) de volatilidade;
- ``rho`` é por variação de 1.0 (100 p.p.) da taxa.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm


def calcular_greeks_call(S0, K, T, r, q, iv):
    """Calcula delta, gamma, vega, theta e rho de uma call (vetorizado).

    Retorna um dict de arrays (ou escalares) com NaN onde os parâmetros são
    inválidos.
    """
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    forma = S0_arr.shape
    delta = np.full(forma, np.nan)
    gamma = np.full(forma, np.nan)
    vega = np.full(forma, np.nan)
    theta = np.full(forma, np.nan)
    rho = np.full(forma, np.nan)

    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    s, k, t, v = S0_arr[validos], K_arr[validos], T_arr[validos], iv_arr[validos]
    sqrt_t = np.sqrt(t)
    d1 = (np.log(s / k) + (r - q + 0.5 * v ** 2) * t) / (v * sqrt_t)
    d2 = d1 - v * sqrt_t
    pdf_d1 = norm.pdf(d1)
    disc_q = np.exp(-q * t)
    disc_r = np.exp(-r * t)

    delta[validos] = disc_q * norm.cdf(d1)
    gamma[validos] = disc_q * pdf_d1 / (s * v * sqrt_t)
    vega[validos] = s * disc_q * pdf_d1 * sqrt_t
    theta[validos] = (
        -(s * disc_q * pdf_d1 * v) / (2 * sqrt_t)
        - r * k * disc_r * norm.cdf(d2)
        + q * s * disc_q * norm.cdf(d1)
    )
    rho[validos] = k * t * disc_r * norm.cdf(d2)

    def _talvez_escalar(arr):
        return arr if arr.ndim else float(arr)

    return {
        "delta": _talvez_escalar(delta),
        "gamma": _talvez_escalar(gamma),
        "vega": _talvez_escalar(vega),
        "theta": _talvez_escalar(theta),
        "rho": _talvez_escalar(rho),
    }


def calcular_greeks_put(S0, K, T, r, q, iv):
    """Calcula delta, gamma, vega, theta e rho de uma put (vetorizado).

    Retorna um dict de arrays (ou escalares) com NaN onde os parâmetros são
    inválidos. Mesmas convenções da call: theta por ano, vega/rho por 100 p.p.
    """
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    forma = S0_arr.shape
    delta = np.full(forma, np.nan)
    gamma = np.full(forma, np.nan)
    vega = np.full(forma, np.nan)
    theta = np.full(forma, np.nan)
    rho = np.full(forma, np.nan)

    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    s, k, t, v = S0_arr[validos], K_arr[validos], T_arr[validos], iv_arr[validos]
    sqrt_t = np.sqrt(t)
    d1 = (np.log(s / k) + (r - q + 0.5 * v ** 2) * t) / (v * sqrt_t)
    d2 = d1 - v * sqrt_t
    pdf_d1 = norm.pdf(d1)
    disc_q = np.exp(-q * t)
    disc_r = np.exp(-r * t)

    delta[validos] = disc_q * (norm.cdf(d1) - 1.0)
    gamma[validos] = disc_q * pdf_d1 / (s * v * sqrt_t)
    vega[validos] = s * disc_q * pdf_d1 * sqrt_t
    theta[validos] = (
        -(s * disc_q * pdf_d1 * v) / (2 * sqrt_t)
        + r * k * disc_r * norm.cdf(-d2)
        - q * s * disc_q * norm.cdf(-d1)
    )
    rho[validos] = -k * t * disc_r * norm.cdf(-d2)

    def _talvez_escalar(arr):
        return arr if arr.ndim else float(arr)

    return {
        "delta": _talvez_escalar(delta),
        "gamma": _talvez_escalar(gamma),
        "vega": _talvez_escalar(vega),
        "theta": _talvez_escalar(theta),
        "rho": _talvez_escalar(rho),
    }
