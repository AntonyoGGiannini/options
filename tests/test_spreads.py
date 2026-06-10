"""Testes de bull call spread e iron condor (mock IBIT com puts sintéticas)."""

from __future__ import annotations

import pandas as pd
import pytest

from allocation.config import Config
from allocation.opcoes.spreads import avaliar_bull_call_spreads, avaliar_iron_condors


@pytest.fixture
def config_spreads(pasta_mock):
    return Config(
        lista_ativos=["IBIT"],
        min_dias=0,
        max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )


def test_bull_call_invariantes(dados_ibit, config_spreads):
    df = avaliar_bull_call_spreads(dados_ibit, config_spreads)
    assert not df.empty
    # lucro_max + perda_max = largura do spread (identidade do payoff)
    soma = df["lucro_max"] + df["perda_max"]
    assert (soma - df["largura"]).abs().max() < 1e-9
    # break-even entre os strikes
    assert (df["breakeven"] > df["strike_long"]).all()
    assert (df["breakeven"] < df["strike_short"]).all()
    # débito positivo (estratégia de débito) e prob de lucro em (0, 1)
    assert (df["debito"] > 0).all()
    assert df["prob_lucro"].between(0, 1, inclusive="neither").all()
    # ordenado por score
    assert df["score_spread"].is_monotonic_decreasing


def test_bull_call_prob_decresce_com_breakeven(dados_ibit, config_spreads):
    """Para o mesmo vencimento, break-even mais alto = menor prob de lucro."""
    df = avaliar_bull_call_spreads(dados_ibit, config_spreads)
    algum_vencimento_com_pares = False
    for _, grupo in df.groupby("expiration"):
        if len(grupo) < 2:
            continue
        algum_vencimento_com_pares = True
        ordenado = grupo.sort_values("breakeven")
        # IVs diferentes por strike permitem pequenas inversões locais; a
        # correlação entre break-even e prob deve ser claramente negativa.
        corr = ordenado["breakeven"].corr(ordenado["prob_lucro"])
        assert corr < 0
    assert algum_vencimento_com_pares


def test_bull_call_largura_respeitada(dados_ibit, config_spreads):
    largura_max_pct = 0.10
    df = avaliar_bull_call_spreads(dados_ibit, config_spreads, largura_max_pct=largura_max_pct)
    if df.empty:
        pytest.skip("sem pares na largura restrita")
    assert (df["largura"] <= largura_max_pct * dados_ibit.preco_atual + 1e-9).all()


def test_iron_condor_economia(dados_ibit, config_spreads):
    df = avaliar_iron_condors(dados_ibit, config_spreads)
    assert not df.empty
    spot = dados_ibit.preco_atual
    # asas OTM em volta do spot, com proteção além do strike vendido
    assert (df["strike_put_short"] < spot).all()
    assert (df["strike_call_short"] > spot).all()
    assert (df["strike_put_long"] < df["strike_put_short"]).all()
    assert (df["strike_call_long"] > df["strike_call_short"]).all()
    # crédito positivo e perda máxima consistente
    assert (df["credito"] > 0).all()
    assert (df["perda_max"] > 0).all()
    assert ((df["largura_max"] - df["credito"] - df["perda_max"]).abs() < 1e-9).all()
    # break-evens em volta da zona de lucro
    assert (df["breakeven_inferior"] < df["strike_put_short"]).all()
    assert (df["breakeven_superior"] > df["strike_call_short"]).all()
    # prob de terminar entre os break-evens em [0, 1]
    assert df["prob_lucro"].between(0, 1).all()
    assert df["score_condor"].is_monotonic_decreasing


def test_iron_condor_sem_puts_degrada(dados_ibit, config_spreads):
    dados_sem_puts = type(dados_ibit)(
        ativo=dados_ibit.ativo,
        df_calls=dados_ibit.df_calls,
        preco_atual=dados_ibit.preco_atual,
        historico_precos=dados_ibit.historico_precos,
        df_puts=pd.DataFrame(),
    )
    assert avaliar_iron_condors(dados_sem_puts, config_spreads).empty
    # bull call não depende de puts
    assert not avaliar_bull_call_spreads(dados_sem_puts, config_spreads).empty
