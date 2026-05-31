"""Testes do modelo Monte Carlo."""

from __future__ import annotations

import numpy as np

from options.models.black_scholes import calcular_prob_exercicio_risk_neutral
from options.models.monte_carlo import (
    calcular_prob_acima_strike_monte_carlo,
    calcular_prob_acima_strike_monte_carlo_batch,
)


def test_mc_converge_para_d2_quando_mu_igual_r():
    # Sob mu = r e q = 0, o MC deve estimar a mesma prob do d2 risk-neutral.
    S0, K, T, r, iv = 100.0, 110.0, 0.5, 0.045, 0.30
    d2 = calcular_prob_exercicio_risk_neutral(S0, K, T, r, 0.0, iv)
    mc = calcular_prob_acima_strike_monte_carlo(
        S0, K, T, mu=r, sigma=iv, q=0.0, n_simulacoes=200_000, seed=7
    )
    assert abs(mc - d2) < 0.01


def test_mc_determinista_com_seed():
    a = calcular_prob_acima_strike_monte_carlo(100, 105, 0.5, 0.05, 0.25, seed=1)
    b = calcular_prob_acima_strike_monte_carlo(100, 105, 0.5, 0.05, 0.25, seed=1)
    assert a == b


def test_mc_invalidos_retornam_nan():
    assert np.isnan(calcular_prob_acima_strike_monte_carlo(100, 105, 0, 0.05, 0.25))
    assert np.isnan(calcular_prob_acima_strike_monte_carlo(100, 105, 0.5, 0.05, 0))


def test_batch_bate_com_escalar():
    S0 = np.array([100.0, 100.0, 100.0])
    K = np.array([95.0, 105.0, 130.0])
    T, mu, sigma = 0.5, 0.045, 0.25
    batch = calcular_prob_acima_strike_monte_carlo_batch(
        S0, K, T, mu=mu, sigma=sigma, n_simulacoes=100_000, seed=42, batch_size=2
    )
    # Cada item deve ser uma probabilidade válida e decrescente com o strike.
    assert batch.shape == (3,)
    assert np.all((batch >= 0) & (batch <= 1))
    assert batch[0] > batch[1] > batch[2]


def test_batch_propaga_nan():
    probs = calcular_prob_acima_strike_monte_carlo_batch(
        np.array([100.0, 100.0]), np.array([105.0, 105.0]),
        np.array([0.5, 0.0]), mu=0.05, sigma=np.array([0.25, 0.25]),
        n_simulacoes=10_000, seed=3,
    )
    assert not np.isnan(probs[0])
    assert np.isnan(probs[1])
