"""Testes da análise de volatilidade (term structure, cone, rank, skew)."""

from __future__ import annotations

import pandas as pd

from allocation.config import Config
from allocation.opcoes.volatilidade import (
    analisar_volatilidade,
    cone_volatilidade,
    rank_percentile_vol,
    skew_por_vencimento,
    term_structure_iv,
)


def test_term_structure_uma_linha_por_vencimento(dados_ibit):
    term = term_structure_iv(dados_ibit.df_calls, dados_ibit.preco_atual)
    df = dados_ibit.df_calls.copy()
    hoje = pd.Timestamp.today().normalize()
    futuros = df[pd.to_datetime(df["expiration"]).dt.normalize() > hoje]
    assert len(term) == futuros["expiration"].nunique()
    assert term["dias_vencimento"].is_monotonic_increasing
    assert (term["iv_atm"].dropna() > 0).all()
    assert (term["n_opcoes"] > 0).all()


def test_term_structure_cadeia_vazia():
    term = term_structure_iv(pd.DataFrame(), 100.0)
    assert term.empty
    assert "iv_atm" in term.columns


def test_cone_janelas_insuficientes_dao_nan(dados_ibit):
    # histórico curto: só a janela de 21 pregões tem dados suficientes
    historico_curto = dados_ibit.historico_precos.iloc[-30:]
    cone = cone_volatilidade(historico_curto)
    assert len(cone) == 4
    assert cone.loc[cone["janela"] == 21, "vol_realizada"].notna().all()
    assert cone.loc[cone["janela"] == 252, "vol_realizada"].isna().all()


def test_rank_percentile_vol_em_faixas(dados_ibit):
    rank = rank_percentile_vol(dados_ibit.historico_precos)
    assert 0.0 <= rank["vol_rank"] <= 1.0
    assert 0.0 <= rank["vol_percentile"] <= 1.0
    assert rank["vol_atual"] > 0


def test_rank_percentile_vol_historico_insuficiente():
    rank = rank_percentile_vol(pd.Series([100.0, 101.0, 102.0]))
    assert pd.isna(rank["vol_rank"])
    assert pd.isna(rank["vol_percentile"])


def test_skew_com_puts_por_paridade_aprox_zero(dados_ibit):
    """Puts sintéticas por paridade têm a mesma IV das calls → skew ≈ 0."""
    skew = skew_por_vencimento(
        dados_ibit.df_calls, dados_ibit.df_puts, dados_ibit.preco_atual
    )
    assert not skew.empty
    assert (skew["fonte_skew"] == "puts_e_calls").all()
    validos = skew["skew_put_call"].dropna()
    assert (validos.abs() < 0.05).all()


def test_skew_sem_puts_usa_fallback(dados_ibit):
    skew = skew_por_vencimento(dados_ibit.df_calls, pd.DataFrame(), dados_ibit.preco_atual)
    assert not skew.empty
    assert (skew["fonte_skew"] == "apenas_calls").all()
    assert skew["skew_put_call"].isna().all()
    assert skew["skew_otm_atm"].notna().any()


def test_analisar_volatilidade_retorna_quatro_chaves(dados_ibit):
    config = Config(lista_ativos=["IBIT"], modo_offline=True)
    analise = analisar_volatilidade(dados_ibit, config)
    assert set(analise) == {"resumo", "term_structure", "cone", "skew"}
    resumo = analise["resumo"]
    assert len(resumo) == 1
    for col in ["iv_atm_curta", "vol_21d", "premio_vol", "vol_rank",
                "vol_percentile", "skew_curto"]:
        assert col in resumo.columns
