"""Testes de protective put e collar (mock IBIT com puts sintéticas)."""

from __future__ import annotations

import pytest

from allocation.config import Config
from allocation.opcoes.hedge import avaliar_collar, avaliar_protective_put


@pytest.fixture
def config_hedge(pasta_mock):
    return Config(
        lista_ativos=["IBIT"], prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
    )


def test_protective_put_economia(dados_ibit, config_hedge):
    df = avaliar_protective_put(dados_ibit, config_hedge)
    assert not df.empty
    # piso = strike − custo da proteção
    assert (df["piso"] == df["strike"] - df["custo_protecao"]).all()
    # proteção custa dinheiro: custo positivo e prob de uso em [0, 1]
    assert (df["custo_protecao"] > 0).all()
    assert df["prob_uso"].between(0, 1).all()
    # delta da posição protegida em (0, 1): menos direcional que a ação pura
    assert df["delta_posicao"].dropna().between(0, 1).all()
    # ordenado da menor para a maior perda máxima
    assert df["perda_max_pct"].is_monotonic_increasing


def test_collar_economia(dados_ibit, config_hedge):
    df = avaliar_collar(dados_ibit, config_hedge)
    assert not df.empty
    spot = dados_ibit.preco_atual
    # strikes em volta do spot
    assert (df["strike_put"] < spot).all()
    assert (df["strike_call"] > spot).all()
    # piso e teto consistentes com o custo líquido
    assert (df["piso"] == df["strike_put"] - df["custo_liquido"]).all()
    assert (df["teto"] == df["strike_call"] - df["custo_liquido"]).all()
    assert (df["teto"] > df["piso"]).all()
    # ordenado por proteção por unidade de custo
    assert df["score_hedge"].is_monotonic_decreasing


def test_collar_nao_pior_que_protective_put_mesmo_strike(dados_ibit, config_hedge):
    """A call vendida financia a put: para o mesmo strike/vencimento da put, a
    perda máxima do collar nunca é pior que a da protective put."""
    df_pp = avaliar_protective_put(dados_ibit, config_hedge)
    df_collar = avaliar_collar(dados_ibit, config_hedge)
    assert not df_pp.empty and not df_collar.empty

    pp = df_pp.set_index(["strike", "expiration"])["perda_max_pct"]
    for _, linha in df_collar.iterrows():
        chave = (linha["strike_put"], linha["expiration"])
        if chave in pp.index:
            assert linha["perda_max_pct"] <= pp.loc[chave] + 1e-9


def test_collar_sem_puts_degrada(dados_ibit, config_hedge):
    import pandas as pd

    dados_sem_puts = type(dados_ibit)(
        ativo=dados_ibit.ativo,
        df_calls=dados_ibit.df_calls,
        preco_atual=dados_ibit.preco_atual,
        historico_precos=dados_ibit.historico_precos,
        df_puts=pd.DataFrame(),
    )
    assert avaliar_collar(dados_sem_puts, config_hedge).empty
    assert avaliar_protective_put(dados_sem_puts, config_hedge).empty
