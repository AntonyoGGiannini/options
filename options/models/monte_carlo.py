"""Estimativa Monte Carlo da probabilidade de exercício (movimento log-normal)."""

from __future__ import annotations

import numpy as np


def calcular_prob_acima_strike_monte_carlo(S0, K, T, mu, sigma, q=0.0,
                                           n_simulacoes=10000, seed=None):
    """Estimativa Monte Carlo da probabilidade de exercício."""
    if T <= 0 or sigma <= 0 or K <= 0 or S0 <= 0 or n_simulacoes <= 0:
        return np.nan
    rng = np.random.default_rng(seed)
    choques = rng.standard_normal(n_simulacoes)
    precos_vencimento = S0 * np.exp(
        (mu - q - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * choques
    )
    return float(np.mean(precos_vencimento > K))


def calcular_prob_acima_strike_monte_carlo_batch(S0, K, T, mu, sigma, q=0.0,
                                                 n_simulacoes=10000, seed=None,
                                                 batch_size=500):
    """Versão vetorizada do Monte Carlo, processa em batches para economizar memória."""
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)
    S0_arr = np.asarray(S0, dtype=float)
    if S0_arr.ndim == 0:
        S0_arr = np.full(K_arr.shape, float(S0_arr))
    S0_arr, K_arr, T_arr, sigma_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, sigma_arr)

    probs = np.full(K_arr.shape, np.nan, dtype=float)
    if n_simulacoes <= 0 or batch_size <= 0:
        return probs

    validos = (T_arr > 0) & (sigma_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    indices_validos = np.flatnonzero(validos.ravel())
    if len(indices_validos) == 0:
        return probs

    rng = np.random.default_rng(seed)
    probs_flat = probs.ravel()
    S0_flat = S0_arr.ravel()
    K_flat = K_arr.ravel()
    T_flat = T_arr.ravel()
    sigma_flat = sigma_arr.ravel()

    for inicio in range(0, len(indices_validos), batch_size):
        idx = indices_validos[inicio:inicio + batch_size]
        choques = rng.standard_normal((len(idx), n_simulacoes))
        log_precos = (
            np.log(S0_flat[idx])[:, None]
            + ((mu - q - 0.5 * sigma_flat[idx] ** 2) * T_flat[idx])[:, None]
            + (sigma_flat[idx] * np.sqrt(T_flat[idx]))[:, None] * choques
        )
        probs_flat[idx] = np.mean(log_precos > np.log(K_flat[idx])[:, None], axis=1)

    return probs
