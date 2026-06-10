"""Testes da camada de dados com cadeia de puts (mock e round-trip)."""

from __future__ import annotations

import pandas as pd

from allocation.data.mock_provider import ProvedorMock, salvar_dados_mock


def test_mock_ibit_carrega_puts(dados_ibit):
    assert not dados_ibit.df_puts.empty
    assert (dados_ibit.df_puts["type"] == "PUT").all()
    # mesma estrutura de colunas essenciais da cadeia de calls
    for col in ["strike", "bid", "ask", "expiration", "impliedVolatility"]:
        assert col in dados_ibit.df_puts.columns


def test_round_trip_salvar_e_carregar_puts(tmp_path, dados_ibit):
    salvar_dados_mock(
        "IBIT",
        dados_ibit.df_calls,
        dados_ibit.preco_atual,
        dados_ibit.historico_precos,
        str(tmp_path),
        df_puts=dados_ibit.df_puts,
    )
    dados = ProvedorMock(str(tmp_path)).obter("IBIT")
    assert len(dados.df_puts) == len(dados_ibit.df_puts)
    assert dados.preco_atual == dados_ibit.preco_atual


def test_mock_sem_puts_degrada_gracioso(tmp_path, dados_ibit):
    """Sem arquivo de puts, o provedor carrega normalmente com df_puts vazio."""
    salvar_dados_mock(
        "IBIT",
        dados_ibit.df_calls,
        dados_ibit.preco_atual,
        dados_ibit.historico_precos,
        str(tmp_path),
    )
    dados = ProvedorMock(str(tmp_path)).obter("IBIT")
    assert isinstance(dados.df_puts, pd.DataFrame)
    assert dados.df_puts.empty
    assert not dados.df_calls.empty
