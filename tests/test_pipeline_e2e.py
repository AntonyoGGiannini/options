"""Testes de integração do pipeline e do ranking usando os mocks (IBIT)."""

from __future__ import annotations

import pandas as pd

from options.config import Config
from options.data.mock_provider import ProvedorMock
from options.models.pipeline import preparar_calls_para_modelo
from options.ranking import processar_ativo
from options.runner import executar


def test_provedor_mock_carrega(dados_ibit):
    assert dados_ibit.ativo == "IBIT"
    assert dados_ibit.preco_atual > 0
    assert not dados_ibit.df_calls.empty
    assert len(dados_ibit.historico_precos) > 0


def test_pipeline_produz_colunas_esperadas(dados_ibit):
    df = preparar_calls_para_modelo(
        df_calls=dados_ibit.df_calls,
        preco_atual=dados_ibit.preco_atual,
        taxa_livre_risco=0.045,
        dividend_yield=0.0,
        usar_premio="bid",
        n_simulacoes=2000,
        seed=42,
        t_min=0,
        t_max=365,
        historico_precos=dados_ibit.historico_precos,
    )
    for col in ["prob_exercicio", "prob_exercicio_mc", "prob_empirica",
                "prob_exercicio_final", "premio", "T"]:
        assert col in df.columns
    # prob_exercicio_final >= prob_exercicio onde a empírica é usada (conservador)
    mask = df["usa_prob_empirica"] & df["prob_empirica"].notna()
    assert (df.loc[mask, "prob_exercicio_final"] >= df.loc[mask, "prob_exercicio"] - 1e-9).all()


def test_processar_ativo_offline_ranqueia(pasta_mock):
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365, n_simulacoes=2000,
        modo_offline=True, pasta_mock=pasta_mock,
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo("IBIT", provedor, config)
    assert not df.empty
    assert (df["ranking_ativo"] == range(1, len(df) + 1)).all()
    # Score deve estar ordenado de forma decrescente.
    assert df["score_venda"].is_monotonic_decreasing
    assert (df["ativo"] == "IBIT").all()


def test_executar_consolida_resultado(pasta_mock):
    config = Config(
        lista_ativos=["IBIT"], top_n=3, prob_exerc_max=0.99,
        min_dias=0, max_dias=365, n_simulacoes=1000,
        modo_offline=True, pasta_mock=pasta_mock,
    )
    df = executar(config)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) <= 3
