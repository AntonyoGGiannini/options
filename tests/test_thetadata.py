"""Testes da normalização e ingestão Theta Data (sem rede: payloads fixos)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from allocation.data.chains_historicas import StoreChainsHistoricas
from allocation.data.thetadata import (
    _normalizar_chain_theta,
    _normalizar_oi_theta,
    _simbolo_occ,
    baixar_chains_historicas,
)

FORMATO_EOD = ["ms_of_day", "open", "high", "low", "close", "volume", "count", "bid", "ask", "date"]
FORMATO_OI = ["ms_of_day", "open_interest", "date"]

PAYLOAD_EOD = {
    "header": {"error_type": "null", "format": FORMATO_EOD},
    "response": [
        {
            "contract": {"root": "IBIT", "expiration": 20250117, "strike": 52000, "right": "C"},
            "ticks": [
                [0, 0.48, 0.60, 0.45, 0.52, 1000, 10, 0.50, 0.55, 20250106],
                [0, 0.50, 0.62, 0.47, 0.55, 800, 8, 0.52, 0.58, 20250107],
            ],
        },
        {
            "contract": {"root": "IBIT", "expiration": 20250117, "strike": 45000, "right": "P"},
            "ticks": [[0, 0.30, 0.35, 0.28, 0.31, 200, 2, 0.30, 0.34, 20250106]],
        },
    ],
}

PAYLOAD_OI = {
    "header": {"error_type": "null", "format": FORMATO_OI},
    "response": [
        {
            "contract": {"root": "IBIT", "expiration": 20250117, "strike": 52000, "right": "C"},
            "ticks": [[0, 1500, 20250106], [0, 1600, 20250107]],
        },
        {
            "contract": {"root": "IBIT", "expiration": 20250117, "strike": 45000, "right": "P"},
            "ticks": [[0, 700, 20250106]],
        },
    ],
}


def test_normalizar_chain_theta():
    df = _normalizar_chain_theta(PAYLOAD_EOD, "IBIT")
    assert len(df) == 3

    call = df[(df["type"] == "CALL") & (df["data_pregao"] == "2025-01-06")].iloc[0]
    assert call["strike"] == 52.0  # milésimos de dólar -> dólares
    assert call["expiration"] == "2025-01-17"
    assert call["bid"] == 0.50
    assert call["ask"] == 0.55
    assert call["lastPrice"] == 0.52
    assert call["volume"] == 1000
    assert call["contractSymbol"] == "IBIT250117C00052000"
    assert call["mid"] == pytest.approx(0.525)
    assert call["spread_pct"] == pytest.approx(0.05 / 0.525)
    assert np.isnan(call["impliedVolatility"])  # EOD não traz IV (fallback de vol)

    put = df[df["type"] == "PUT"].iloc[0]
    assert put["strike"] == 45.0
    assert put["contractSymbol"] == "IBIT250117P00045000"

    assert _normalizar_chain_theta({"header": {}, "response": []}, "IBIT").empty


def test_normalizar_oi_theta():
    df = _normalizar_oi_theta(PAYLOAD_OI)
    assert len(df) == 3
    linha = df[(df["type"] == "CALL") & (df["data_pregao"] == "2025-01-07")].iloc[0]
    assert linha["openInterest"] == 1600


def test_simbolo_occ_com_strike_fracionario():
    assert _simbolo_occ("AAPL", "2025-06-20", "PUT", 187.5) == "AAPL250620P00187500"


class ClienteFalso:
    """Stub do ClienteThetaData com os payloads fixos acima."""

    def listar_expiracoes(self, ativo):
        return ["2024-06-21", "2025-01-17", "2026-12-18"]

    def eod_chain_bulk(self, ativo, expiration, start_date, end_date):
        return PAYLOAD_EOD

    def open_interest_bulk(self, ativo, expiration, start_date, end_date):
        return PAYLOAD_OI

    def eod_stock(self, ativo, start_date, end_date):
        return pd.Series({pd.Timestamp("2025-01-06"): 50.0, pd.Timestamp("2025-01-07"): 51.0})


def test_baixar_chains_historicas(tmp_path):
    store = StoreChainsHistoricas(tmp_path)
    n = baixar_chains_historicas("IBIT", "2025-01-01", "2025-01-31", store, cliente=ClienteFalso())
    # expirations fora da janela (+margem) são ignoradas; 2 pregões gravados
    assert n == 2
    assert store.datas_disponiveis("IBIT") == [
        pd.Timestamp("2025-01-06"),
        pd.Timestamp("2025-01-07"),
    ]

    snap = store.carregar_snapshot("IBIT", "2025-01-06")
    assert snap.spot == 50.0
    assert len(snap.df_calls) == 1
    assert len(snap.df_puts) == 1
    call = snap.df_calls.iloc[0]
    assert call["openInterest"] == 1500  # merge do bulk de OI
    assert not call["inTheMoney"]  # call 52 com spot 50 -> OTM
    assert not snap.df_puts.iloc[0]["inTheMoney"]  # put 45 com spot 50 -> OTM

    # idempotente: re-rodar sem sobrescrever não regrava nada
    assert (
        baixar_chains_historicas("IBIT", "2025-01-01", "2025-01-31", store, cliente=ClienteFalso())
        == 0
    )
