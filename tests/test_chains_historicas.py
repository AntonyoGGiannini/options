"""Testes do store de chains históricas e do data_referencia do pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from allocation.data.chains_historicas import StoreChainsHistoricas
from allocation.opcoes.pipeline import preparar_calls_para_modelo


def _chain_exemplo() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": [50.0, 55.0, 45.0],
            "bid": [1.0, 0.4, 0.8],
            "ask": [1.1, 0.5, 0.9],
            "lastPrice": [1.05, 0.45, 0.85],
            "volume": [500, 200, 300],
            "openInterest": [1000, 800, 600],
            "impliedVolatility": [0.5, 0.55, 0.6],
            "expiration": ["2025-01-17", "2025-01-17", "2025-01-17"],
            "type": ["CALL", "CALL", "PUT"],
        }
    )


def test_store_round_trip(tmp_path):
    store = StoreChainsHistoricas(tmp_path)
    caminho = store.salvar_snapshot("IBIT", "2025-01-06", _chain_exemplo(), spot=50.0)
    assert caminho.exists()
    assert store.tem_snapshot("IBIT", "2025-01-06")

    snap = store.carregar_snapshot("IBIT", "2025-01-06")
    assert snap.ativo == "IBIT"
    assert snap.spot == 50.0
    assert snap.data_pregao == pd.Timestamp("2025-01-06")
    assert len(snap.df_calls) == 2
    assert len(snap.df_puts) == 1
    assert (snap.df_calls["data_pregao"] == "2025-01-06").all()
    assert (snap.df_calls["ativo"] == "IBIT").all()


def test_store_datas_disponiveis_e_serie_spot(tmp_path):
    store = StoreChainsHistoricas(tmp_path)
    for data, spot in [("2025-01-06", 50.0), ("2025-01-07", 51.0), ("2025-01-08", 49.5)]:
        store.salvar_snapshot("IBIT", data, _chain_exemplo(), spot=spot)

    datas = store.datas_disponiveis("IBIT")
    assert datas == [pd.Timestamp(d) for d in ["2025-01-06", "2025-01-07", "2025-01-08"]]
    assert store.datas_disponiveis("IBIT", inicio="2025-01-07") == datas[1:]
    assert store.datas_disponiveis("IBIT", fim="2025-01-07") == datas[:2]
    assert store.datas_disponiveis("XXXX") == []

    spots = store.serie_spot("IBIT")
    assert list(spots.values) == [50.0, 51.0, 49.5]
    assert list(spots.index) == datas


def test_store_valida_colunas_e_spot(tmp_path):
    store = StoreChainsHistoricas(tmp_path)
    com_falta = _chain_exemplo().drop(columns=["openInterest"])
    with pytest.raises(ValueError, match="colunas obrigatórias"):
        store.salvar_snapshot("IBIT", "2025-01-06", com_falta, spot=50.0)
    with pytest.raises(ValueError, match="spot"):
        store.salvar_snapshot("IBIT", "2025-01-06", _chain_exemplo(), spot=0.0)


def test_pipeline_data_referencia_historica():
    """Com data_referencia, o pipeline conta dias a partir dela (replay)."""
    df = _chain_exemplo()
    df = df[df["type"] == "CALL"]
    out = preparar_calls_para_modelo(
        df,
        preco_atual=50.0,
        taxa_livre_risco=0.045,
        dividend_yield=0.0,
        usar_premio="bid",
        t_min=0,
        t_max=365,
        data_referencia="2025-01-06",
    )
    # 2025-01-06 (seg) → 2025-01-17 (sex): 11 dias corridos, 9 úteis
    assert (out["dias_vencimento"] == 11).all()
    assert (out["dias_uteis_ate_vencimento"] == 9).all()
    assert np.allclose(out["T"], 11 / 365)
