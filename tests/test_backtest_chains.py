"""Testes do replay do screener sobre chains históricas reais."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from allocation.config import Config
from allocation.data.chains_historicas import StoreChainsHistoricas
from allocation.opcoes import backtest_chains
from allocation.opcoes.backtest_chains import (
    calibracao_probabilidade,
    replay_screener_chains,
    validar_parametros_grid,
)


def _chain(linhas: list[dict]) -> pd.DataFrame:
    """Monta uma cadeia de calls a partir de dicts {strike, bid, ask, expiration}."""
    df = pd.DataFrame(linhas)
    df["lastPrice"] = (df["bid"] + df["ask"]) / 2
    df["volume"] = 1000
    df["openInterest"] = 2000
    df["impliedVolatility"] = 0.5
    df["type"] = "CALL"
    return df


_CHAIN_MORTA = _chain([{"strike": 99.0, "bid": 0.0, "ask": 0.0, "expiration": "2099-01-01"}])


@pytest.fixture
def store_replay(tmp_path) -> StoreChainsHistoricas:
    """Quatro pregões determinísticos para P&L conhecido.

    - 2025-01-06 (spot 50): vende K=52 exp 2025-01-17 a bid 0.50; a linha com
      bid 0 deve ser excluída pelo filtro de qualidade.
    - 2025-01-17 (spot 51): só fornece o spot de liquidação (OTM: 51 < 52).
    - 2025-01-20 (spot 50): vende K=52 exp 2025-01-31 a bid 0.50.
    - 2025-01-31 (spot 56): liquidação exercida (56 > 52).
    """
    store = StoreChainsHistoricas(tmp_path)
    store.salvar_snapshot(
        "IBIT",
        "2025-01-06",
        _chain(
            [
                {"strike": 52.0, "bid": 0.50, "ask": 0.55, "expiration": "2025-01-17"},
                {"strike": 51.0, "bid": 0.0, "ask": 0.55, "expiration": "2025-01-17"},
            ]
        ),
        spot=50.0,
    )
    store.salvar_snapshot("IBIT", "2025-01-17", _CHAIN_MORTA, spot=51.0)
    store.salvar_snapshot(
        "IBIT",
        "2025-01-20",
        _chain([{"strike": 52.0, "bid": 0.50, "ask": 0.55, "expiration": "2025-01-31"}]),
        spot=50.0,
    )
    store.salvar_snapshot("IBIT", "2025-01-31", _CHAIN_MORTA, spot=56.0)
    return store


@pytest.fixture
def config_replay() -> Config:
    # prob_exerc_max=1.0 desliga o filtro de probabilidade: o P&L do teste
    # não deve depender do valor do modelo, só da mecânica de liquidação.
    return Config(lista_ativos=["IBIT"], prob_exerc_max=1.0, min_dias=7, max_dias=20)


def test_replay_pnl_conhecido(store_replay, config_replay):
    df_trades, resumo = replay_screener_chains("IBIT", store_replay, config_replay)

    assert resumo.n_pregoes_avaliados == 2  # sequencial pula 01-17 e 01-31
    assert resumo.n_trades == 2
    assert resumo.n_incompletos == 0

    t1 = df_trades.iloc[0]
    assert t1["data_entrada"] == pd.Timestamp("2025-01-06")
    assert t1["strike"] == 52.0
    assert not t1["exercido"]
    assert t1["S_vencimento"] == 51.0
    # OTM: (51 − 50 + 0.50) / 50, sem custo de exercício (custo_venda = 0)
    assert t1["retorno_cc"] == pytest.approx(0.03)
    assert t1["dias_vencimento"] == 11
    assert t1["retorno_cc_anualizado"] == pytest.approx(0.03 * 365 / 11)
    assert t1["retorno_buy_hold"] == pytest.approx(0.02)

    t2 = df_trades.iloc[1]
    assert t2["data_entrada"] == pd.Timestamp("2025-01-20")
    assert t2["exercido"]
    assert t2["S_vencimento"] == 56.0
    # exercida: custo de exercício max(0.25% × 52 × 100, 10) = 13 → 0.13/ação
    # (52 − 50 + 0.50 − 0.13) / 50
    assert t2["retorno_cc"] == pytest.approx(2.37 / 50)
    assert t2["retorno_buy_hold"] == pytest.approx(0.12)

    assert resumo.taxa_exercicio_realizada == pytest.approx(0.5)
    assert resumo.retorno_medio_trade == pytest.approx((0.03 + 0.0474) / 2)
    # bid=0 nunca vira trade (filtro de qualidade)
    assert (df_trades["bid_entrada"] > 0).all()
    assert (df_trades["strike"] != 51.0).all()


def test_replay_passo_fixo_avalia_todos_os_pregoes(store_replay, config_replay):
    df_trades, resumo = replay_screener_chains("IBIT", store_replay, config_replay, passo_dias=1)
    assert resumo.n_pregoes_avaliados == 4
    assert resumo.n_trades == 2  # chains "mortas" (bid 0) não geram candidata
    assert resumo.n_sem_candidata == 2


def test_replay_vencimento_fora_do_store_conta_incompleto(tmp_path, config_replay):
    store = StoreChainsHistoricas(tmp_path)
    store.salvar_snapshot(
        "IBIT",
        "2025-01-06",
        _chain([{"strike": 52.0, "bid": 0.50, "ask": 0.55, "expiration": "2025-01-17"}]),
        spot=50.0,
    )
    df_trades, resumo = replay_screener_chains("IBIT", store, config_replay)
    assert resumo.n_trades == 0
    assert resumo.n_incompletos == 1
    assert df_trades.empty


def test_replay_anti_look_ahead(store_replay, config_replay, monkeypatch):
    """O histórico passado ao pipeline nunca pode ultrapassar a data do pregão."""
    historicos_vistos: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    original = backtest_chains.preparar_calls_para_modelo

    def espiao(*args, **kwargs):
        hist = kwargs.get("historico_precos")
        if hist is not None and len(hist) > 0:
            historicos_vistos.append((pd.Timestamp(kwargs["data_referencia"]), hist.index.max()))
        return original(*args, **kwargs)

    monkeypatch.setattr(backtest_chains, "preparar_calls_para_modelo", espiao)

    # série diária que se estende muito além dos pregões do store
    idx = pd.bdate_range("2024-10-01", "2025-06-30")
    historico = pd.Series(np.linspace(45, 60, len(idx)), index=idx)

    replay_screener_chains("IBIT", store_replay, config_replay, historico_precos=historico)

    assert historicos_vistos, "pipeline deveria ter recebido histórico"
    for data_pregao, max_hist in historicos_vistos:
        assert max_hist <= data_pregao


def test_calibracao_probabilidade():
    df = pd.DataFrame(
        {
            "prob_exercicio_final": [0.05, 0.06, 0.30, 0.32],
            "exercido": [False, False, True, False],
        }
    )
    cal = calibracao_probabilidade(df, n_buckets=2)
    assert len(cal) == 2
    assert cal["n_trades"].sum() == 4
    assert cal["freq_exercicio_realizada"].iloc[0] == pytest.approx(0.0)
    assert cal["freq_exercicio_realizada"].iloc[1] == pytest.approx(0.5)
    assert calibracao_probabilidade(pd.DataFrame()).empty


def test_grid_de_parametros(store_replay, config_replay):
    grade = {"prob_exerc_max": [1e-9, 1.0], "min_dias": [7, 12]}
    df = validar_parametros_grid("IBIT", store_replay, config_replay, grade)
    assert len(df) == 4
    assert {"prob_exerc_max", "min_dias", "n_trades", "retorno_medio_trade"} <= set(df.columns)

    permissiva = df[(df["prob_exerc_max"] == 1.0) & (df["min_dias"] == 7)].iloc[0]
    assert permissiva["n_trades"] == 2
    # prob_exerc_max ~0 rejeita tudo; min_dias=12 exclui as opções de 11 dias
    assert (df.loc[df["prob_exerc_max"] == 1e-9, "n_trades"] == 0).all()
    assert (df.loc[df["min_dias"] == 12, "n_trades"] == 0).all()


def test_grid_valida_parametros(store_replay, config_replay):
    with pytest.raises(ValueError, match="prob_exerc_max"):
        validar_parametros_grid("IBIT", store_replay, config_replay, {"prob_exerc_max": [1.5]})
    with pytest.raises(ValueError, match="desconhecidos"):
        validar_parametros_grid("IBIT", store_replay, config_replay, {"parametro_inexistente": [1]})
    with pytest.raises(ValueError, match="grade"):
        validar_parametros_grid("IBIT", store_replay, config_replay, {})
