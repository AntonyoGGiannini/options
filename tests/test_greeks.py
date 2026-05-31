"""Testes dos Greeks de Black-Scholes."""

from __future__ import annotations

import numpy as np

from options.models.black_scholes import preco_call_bs
from options.models.greeks import calcular_greeks_call


def test_delta_em_faixa_e_atm_proximo_de_meio():
    g = calcular_greeks_call(100.0, 100.0, 0.5, 0.045, 0.0, 0.25)
    assert 0.0 < g["delta"] < 1.0
    assert 0.45 < g["delta"] < 0.65  # ATM, ligeiramente acima de 0.5


def test_gamma_e_vega_positivos():
    g = calcular_greeks_call(100.0, 105.0, 0.5, 0.045, 0.0, 0.25)
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_delta_via_diferencas_finitas():
    # delta = dC/dS, comparado por diferença central.
    S, K, T, r, q, iv = 100.0, 110.0, 0.4, 0.03, 0.0, 0.30
    h = 1e-4
    c_up = preco_call_bs(S + h, K, T, r, q, iv)
    c_dn = preco_call_bs(S - h, K, T, r, q, iv)
    delta_fd = (c_up - c_dn) / (2 * h)
    g = calcular_greeks_call(S, K, T, r, q, iv)
    assert abs(g["delta"] - delta_fd) < 1e-4


def test_vega_via_diferencas_finitas():
    S, K, T, r, q, iv = 100.0, 105.0, 0.5, 0.03, 0.0, 0.25
    h = 1e-5
    vega_fd = (preco_call_bs(S, K, T, r, q, iv + h) - preco_call_bs(S, K, T, r, q, iv - h)) / (2 * h)
    g = calcular_greeks_call(S, K, T, r, q, iv)
    assert abs(g["vega"] - vega_fd) < 1e-2


def test_invalidos_retornam_nan():
    g = calcular_greeks_call(100.0, 105.0, 0.0, 0.045, 0.0, 0.25)
    assert all(np.isnan(g[k]) for k in g)


def test_vetorizado():
    g = calcular_greeks_call(
        np.array([100.0, 100.0]), np.array([90.0, 130.0]),
        0.5, 0.045, 0.0, 0.25,
    )
    # Call mais ITM tem delta maior.
    assert g["delta"][0] > g["delta"][1]
