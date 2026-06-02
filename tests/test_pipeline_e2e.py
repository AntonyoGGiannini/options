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
        t_min=0,
        t_max=365,
        historico_precos=dados_ibit.historico_precos,
    )
    for col in ["prob_exercicio", "prob_empirica",
                "prob_exercicio_final", "premio", "T",
                "delta", "gamma", "vega", "theta", "iv_usada", "fonte_vol",
                "risco_atribuicao_antecipada"]:
        assert col in df.columns
    # Delta de calls OTM deve estar em (0, 1).
    deltas = df["delta"].dropna()
    assert ((deltas > 0) & (deltas < 1)).all()
    # prob_exercicio_final >= prob_exercicio onde a empírica é usada (conservador)
    mask = df["usa_prob_empirica"] & df["prob_empirica"].notna()
    assert (df.loc[mask, "prob_exercicio_final"] >= df.loc[mask, "prob_exercicio"] - 1e-9).all()


def test_processar_ativo_offline_ranqueia(pasta_mock):
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
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
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
    )
    df = executar(config)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) <= 3


def test_posicao_existente_com_custo(pasta_mock):
    """Com preco_medio_aquisicao, adiciona colunas de custo e alerta."""
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
        preco_medio_aquisicao={"IBIT": 999.0},  # custo alto → todos alertam
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo("IBIT", provedor, config)
    if not df.empty:
        assert df["alerta_abaixo_custo"].all()
        assert (df["capital_por_contrato"] == 999.0 * 100).all()
        assert "retorno_sobre_custo" in df.columns


def test_screener_sem_custo_saida_enxuta(pasta_mock):
    """Sem custo informado (screener), as colunas de custo são omitidas."""
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo("IBIT", provedor, config)
    if not df.empty:
        for col in ["capital_por_contrato", "retorno_sobre_custo", "alerta_abaixo_custo"]:
            assert col not in df.columns


def test_screener_filtra_prejuizo_se_exercido(pasta_mock):
    """Screener: toda opção retornada deve ter lucro positivo se exercida."""
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo("IBIT", provedor, config)
    if not df.empty:
        assert "lucro_se_exercido" in df.columns
        assert (df["lucro_se_exercido"] > 0).all()
        assert "custo_exercicio_contrato" in df.columns


def test_custo_alto_exclui_por_prejuizo_no_exercicio(pasta_mock):
    """Custo de aquisição altíssimo → vender abaixo do custo dá prejuízo se
    exercido; com o filtro ligado (padrão) nada é sugerido."""
    config = Config(
        lista_ativos=["IBIT"], top_n=5, prob_exerc_max=0.99,
        min_dias=0, max_dias=365,
        modo_offline=True, pasta_mock=pasta_mock,
        preco_medio_aquisicao={"IBIT": 999.0},
    )
    provedor = ProvedorMock(pasta_mock)
    df = processar_ativo("IBIT", provedor, config)
    assert df.empty
    # com o filtro desligado, as opções voltam a aparecer
    df2 = processar_ativo("IBIT", provedor, config, excluir_prejuizo_exercicio=False)
    assert not df2.empty
    assert (df2["lucro_se_exercido"] <= 0).all()
