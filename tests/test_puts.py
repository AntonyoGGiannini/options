"""Testes do pipeline e ranking de puts cash-secured (modelos + mock IBIT)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.mock_provider import ProvedorMock
from allocation.models.black_scholes import (
    calcular_prob_exercicio_put_vetor,
    calcular_prob_exercicio_risk_neutral_vetor,
    preco_call_bs,
    preco_put_bs,
)
from allocation.models.greeks import calcular_greeks_call, calcular_greeks_put
from allocation.opcoes.pipeline import preparar_puts_para_modelo
from allocation.opcoes.puts import processar_ativo_puts
from allocation.runner import executar_puts

S, K, T, R, Q, IV = 100.0, np.array([90.0, 100.0, 110.0]), 0.25, 0.045, 0.01, 0.30


def test_prob_put_complementa_prob_call():
    prob_call = calcular_prob_exercicio_risk_neutral_vetor(S, K, T, R, Q, IV)
    prob_put = calcular_prob_exercicio_put_vetor(S, K, T, R, Q, IV)
    assert np.allclose(prob_call + prob_put, 1.0)
    # put mais ITM (strike maior) tem prob de exercício maior
    assert prob_put[0] < prob_put[1] < prob_put[2]


def test_paridade_put_call_precos():
    call = preco_call_bs(S, K, T, R, Q, IV)
    put = preco_put_bs(S, K, T, R, Q, IV)
    # C − P = S·e^(−qT) − K·e^(−rT)
    paridade = S * np.exp(-Q * T) - K * np.exp(-R * T)
    assert np.allclose(call - put, paridade)


def test_greeks_put_convencoes():
    g_call = calcular_greeks_call(S, K, T, R, Q, IV)
    g_put = calcular_greeks_put(S, K, T, R, Q, IV)
    # delta de put em (−1, 0); paridade: delta_call − delta_put = e^(−qT)
    assert ((g_put["delta"] > -1) & (g_put["delta"] < 0)).all()
    assert np.allclose(g_call["delta"] - g_put["delta"], np.exp(-Q * T))
    # gamma e vega são idênticos para call e put
    assert np.allclose(g_call["gamma"], g_put["gamma"])
    assert np.allclose(g_call["vega"], g_put["vega"])


def test_pipeline_puts_produz_colunas(dados_ibit):
    df = preparar_puts_para_modelo(
        dados_ibit.df_puts,
        preco_atual=dados_ibit.preco_atual,
        taxa_livre_risco=0.045,
        dividend_yield=0.0,
        usar_premio="bid",
        t_min=0,
        t_max=365,
        historico_precos=dados_ibit.historico_precos,
    )
    for col in [
        "prob_exercicio",
        "prob_empirica",
        "prob_exercicio_final",
        "premio",
        "T",
        "delta",
        "gamma",
        "vega",
        "theta",
        "iv_usada",
        "fonte_vol",
        "risco_atribuicao_antecipada",
        "distancia_strike_pct",
    ]:
        assert col in df.columns
    # delta de puts em (−1, 0)
    deltas = df["delta"].dropna()
    assert ((deltas > -1) & (deltas < 0)).all()
    # distancia_strike_pct positiva = strike abaixo do spot (OTM para put)
    otm = df[df["strike"] < dados_ibit.preco_atual]
    assert (otm["distancia_strike_pct"] > 0).all()
    # prob final >= prob d2 onde a empírica é usada (conservador)
    mask = df["usa_prob_empirica"] & df["prob_empirica"].notna()
    assert (df.loc[mask, "prob_exercicio_final"] >= df.loc[mask, "prob_exercicio"] - 1e-9).all()


def test_processar_ativo_puts_offline_ranqueia(pasta_mock):
    config = Config(
        lista_ativos=["IBIT"],
        top_n=5,
        prob_exerc_max=0.99,
        min_dias=0,
        max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo_puts("IBIT", provedor, config)
    assert not df.empty
    assert (df["ranking_ativo"] == range(1, len(df) + 1)).all()
    assert df["score_venda"].is_monotonic_decreasing
    assert (df["ativo"] == "IBIT").all()
    # economia da put: preço efetivo condicional ao exercício usa o custo de
    # atribuição integral (não ponderado pela probabilidade)
    custo_exerc_por_acao = np.maximum(0.0025 * df["strike"] * 100, 10.0) / 100
    esperado = df["strike"] - (df["premio"] - custo_exerc_por_acao)
    assert np.allclose(df["preco_efetivo_se_exercido"], esperado)
    assert (df["preco_efetivo_se_exercido"] < df["strike"]).all()
    assert (df["colateral_por_contrato"] == df["strike"] * 100).all()


def test_executar_puts_consolida(pasta_mock):
    config = Config(
        lista_ativos=["IBIT"],
        top_n=3,
        prob_exerc_max=0.99,
        min_dias=0,
        max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )
    matriz: list[pd.DataFrame] = []
    df = executar_puts(config, matriz_out=matriz)
    assert not df.empty
    assert len(df) <= 3
    assert matriz, "a matriz deve ser coletada"
    df_matriz = pd.concat(matriz, ignore_index=True)
    assert "status" in df_matriz.columns
    assert len(df_matriz) >= len(df)


def test_puts_ativo_sem_mock_de_puts_degrada(pasta_mock):
    """Ativo cujo mock não tem puts → resultado vazio sem exceção."""
    config = Config(
        lista_ativos=["AAPL"],
        top_n=3,
        prob_exerc_max=0.99,
        min_dias=0,
        max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo_puts("AAPL", provedor, config)
    assert df.empty
