"""Testes de volatilidade realizada, backtest e dividend por ativo."""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.models.volatility import volatilidade_realizada
from allocation.opcoes.backtest import backtest_covered_call


def test_vol_realizada_de_serie_constante_e_zero():
    precos = pd.Series([100.0] * 50)
    assert volatilidade_realizada(precos) == 0.0


def test_vol_realizada_positiva_e_anualizada():
    rng = np.random.default_rng(0)
    # vol diária ~1% -> anualizada ~ 0.01*sqrt(252) ~ 0.16
    ret = rng.normal(0, 0.01, 2000)
    precos = pd.Series(100 * np.exp(np.cumsum(ret)))
    vol = volatilidade_realizada(precos)
    assert 0.12 < vol < 0.20


def test_vol_serie_curta_retorna_nan():
    assert np.isnan(volatilidade_realizada(pd.Series([100.0, 101.0])))


def test_backtest_serie_crescente_sempre_exercida():
    # Série sempre subindo mais que a distância -> exercício em todo trade.
    precos = pd.Series(np.linspace(100.0, 400.0, 400))
    df, resumo = backtest_covered_call(
        precos, ativo="X", distancia_strike_pct=0.02,
        dias_vencimento=10, janela_vol=30,
    )
    assert resumo.n_trades > 0
    # Série fortemente altista -> exercício na grande maioria dos trades.
    assert resumo.taxa_exercicio > 0.8
    # Capturou prêmio + valorização até o strike -> retorno positivo.
    assert resumo.retorno_medio_cc > 0


def test_backtest_historico_insuficiente():
    precos = pd.Series(np.linspace(100, 110, 20))
    df, resumo = backtest_covered_call(precos, janela_vol=60, dias_vencimento=14)
    assert resumo.n_trades == 0
    assert df.empty


def test_dividend_para_valor_unico():
    c = Config(dividend_yield=0.02)
    assert c.dividend_para("AAPL") == 0.02
    assert c.dividend_para("QUALQUER") == 0.02


def test_dividend_para_dict():
    c = Config(dividend_yield={"AAPL": 0.005, "SPY": 0.013})
    assert c.dividend_para("AAPL") == 0.005
    assert c.dividend_para("SPY") == 0.013
    assert c.dividend_para("DESCONHECIDO") == 0.0


def test_dividend_dict_negativo_invalido():
    import pytest
    with pytest.raises(ValueError):
        Config(dividend_yield={"AAPL": -0.01})
