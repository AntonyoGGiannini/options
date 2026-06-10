"""Testes da probabilidade empírica histórica."""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.models.empirical import calcular_probabilidade_empirica_batch


def test_historico_curto_nao_usa_empirica():
    precos = pd.Series([100.0, 101.0, 102.0])  # poucas amostras
    probs, usa = calcular_probabilidade_empirica_batch(
        precos,
        np.array([100.0]),
        np.array([105.0]),
        np.array([1]),
        min_amostras=30,
    )
    assert not usa[0]
    assert np.isnan(probs[0])


def test_serie_sempre_subindo_da_prob_alta_para_strike_baixo():
    # Série estritamente crescente: em qualquer janela o retorno futuro é > 0,
    # logo a prob de superar um strike levemente acima é 1.0.
    precos = pd.Series(np.linspace(100.0, 200.0, 200))
    probs, usa = calcular_probabilidade_empirica_batch(
        precos,
        np.array([100.0]),
        np.array([100.5]),
        np.array([5]),
        min_amostras=30,
    )
    assert usa[0]
    assert probs[0] == 1.0


def test_strike_inalcancavel_da_prob_zero():
    precos = pd.Series(np.linspace(100.0, 110.0, 200))
    # Strike 1000% acima — nunca atingido no histórico.
    probs, usa = calcular_probabilidade_empirica_batch(
        precos,
        np.array([100.0]),
        np.array([1000.0]),
        np.array([5]),
        min_amostras=30,
    )
    assert usa[0]
    assert probs[0] == 0.0


def test_multiplas_janelas_processadas():
    # Série longa o suficiente para 30+ janelas não-sobrepostas de tamanho 20.
    # 30 janelas × 20 dias + 20 de lookahead = 620 pontos mínimos.
    precos = pd.Series(np.linspace(100.0, 150.0, 700))
    probs, usa = calcular_probabilidade_empirica_batch(
        precos,
        np.array([100.0, 100.0]),
        np.array([101.0, 101.0]),
        np.array([5, 20]),  # duas janelas distintas
        min_amostras=30,
    )
    assert usa.all()
    assert np.all((probs >= 0) & (probs <= 1))
