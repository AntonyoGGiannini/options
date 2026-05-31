"""Testes do modelo Black-Scholes d2."""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from options.models.black_scholes import (
    calcular_prob_exercicio_risk_neutral,
    calcular_prob_exercicio_risk_neutral_vetor,
)


def _d2_analitico(S0, K, T, r, q, iv):
    return (np.log(S0 / K) + (r - q - 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))


def test_d2_bate_com_valor_analitico():
    S0, K, T, r, q, iv = 100.0, 105.0, 0.5, 0.045, 0.0, 0.25
    esperado = float(norm.cdf(_d2_analitico(S0, K, T, r, q, iv)))
    obtido = calcular_prob_exercicio_risk_neutral(S0, K, T, r, q, iv)
    assert abs(obtido - esperado) < 1e-12


def test_atm_proximo_de_meio():
    # Call exatamente no dinheiro, vol/prazo pequenos -> prob ~ 0.5
    p = calcular_prob_exercicio_risk_neutral(100.0, 100.0, 1e-4, 0.0, 0.0, 0.01)
    assert abs(p - 0.5) < 0.05


def test_prob_decresce_com_strike():
    base = dict(S0=100.0, T=0.5, r=0.045, q=0.0, iv=0.25)
    p_baixo = calcular_prob_exercicio_risk_neutral(K=90.0, **base)
    p_alto = calcular_prob_exercicio_risk_neutral(K=120.0, **base)
    assert p_baixo > p_alto


def test_entradas_invalidas_retornam_nan():
    assert np.isnan(calcular_prob_exercicio_risk_neutral(100, 105, 0, 0.045, 0, 0.25))
    assert np.isnan(calcular_prob_exercicio_risk_neutral(100, 105, 0.5, 0.045, 0, 0))
    assert np.isnan(calcular_prob_exercicio_risk_neutral(-1, 105, 0.5, 0.045, 0, 0.25))


def test_vetor_igual_ao_escalar():
    S0 = np.array([100.0, 100.0, 100.0])
    K = np.array([90.0, 100.0, 120.0])
    T, r, q, iv = 0.5, 0.045, 0.0, 0.25
    vet = calcular_prob_exercicio_risk_neutral_vetor(S0, K, T, r, q, iv)
    esc = [calcular_prob_exercicio_risk_neutral(s, k, T, r, q, iv)
           for s, k in zip(S0, K, strict=True)]
    np.testing.assert_allclose(vet, esc, rtol=1e-12)


def test_vetor_propaga_nan_em_T_invalido():
    probs = calcular_prob_exercicio_risk_neutral_vetor(
        np.array([100.0, 100.0]), np.array([105.0, 105.0]),
        np.array([0.5, 0.0]), 0.045, 0.0, np.array([0.25, 0.25]),
    )
    assert not np.isnan(probs[0])
    assert np.isnan(probs[1])
