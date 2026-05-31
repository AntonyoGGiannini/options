"""Filtros, score e ranking de covered calls por ativo."""

from __future__ import annotations

import pandas as pd

from options.config import Config
from options.data.base import DadosMercado, ProvedorDados
from options.data.mock_provider import salvar_dados_mock
from options.logging_setup import obter_logger
from options.models.pipeline import preparar_calls_para_modelo

logger = obter_logger(__name__)


def rankear_calls(df: pd.DataFrame, config: Config, preco_atual: float) -> pd.DataFrame:
    """Aplica custos, filtros e score, retornando as top-N opções ranqueadas."""
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato
    df["premio_liquido"] = df["premio"] - custo_venda_por_acao
    df["rendimento_liquido"] = df["premio_liquido"] / df["preco_atual"]
    df["retorno_anualizado_liquido"] = df["rendimento_liquido"] / df["T"]

    df_filtrado = df[
        (df["distancia_strike_pct"] > 0)
        & (df["prob_exercicio_final"] <= config.prob_exerc_max)
        & (df["retorno_anualizado_pct"] > 0)
    ].copy()

    if df_filtrado.empty:
        return df_filtrado

    df_filtrado["score_venda"] = (
        df_filtrado["retorno_anualizado_pct"] * (1 - df_filtrado["prob_exercicio_final"])
    )
    df_filtrado = df_filtrado.sort_values("score_venda", ascending=False)
    df_filtrado["ranking_ativo"] = range(1, len(df_filtrado) + 1)
    df_filtrado["preco_atual_ativo"] = preco_atual
    return df_filtrado.head(config.top_n)


def processar_ativo(
    ativo: str,
    provedor: ProvedorDados,
    config: Config,
    salvar_mock: bool = False,
) -> pd.DataFrame:
    """Obtém dados, calcula probabilidades, filtra e ranqueia um ativo.

    Retorna DataFrame vazio (com aviso em log) em caso de erro ou ausência de
    opções, para não interromper o processamento dos demais ativos.
    """
    try:
        dados: DadosMercado = provedor.obter(ativo, config.periodo_historico)

        if salvar_mock:
            salvar_dados_mock(
                ativo, dados.df_calls, dados.preco_atual,
                dados.historico_precos, config.pasta_mock,
            )

        if dados.df_calls.empty:
            logger.info("[%s] Nenhuma opção disponível após filtros de liquidez.", ativo)
            return pd.DataFrame()

        historico = dados.historico_precos if config.usar_prob_empirica else None

        df = preparar_calls_para_modelo(
            df_calls=dados.df_calls,
            preco_atual=dados.preco_atual,
            taxa_livre_risco=config.taxa_livre_risco,
            dividend_yield=config.dividend_yield,
            usar_premio=config.usar_premio,
            mu=config.mu,
            n_simulacoes=config.n_simulacoes,
            seed=config.seed,
            batch_size=config.batch_size,
            t_min=config.min_dias,
            t_max=config.max_dias,
            dias_ano=config.dias_ano,
            historico_precos=historico,
            usar_prob_d2=config.usar_prob_d2,
            usar_prob_mc=config.usar_prob_mc,
            usar_prob_empirica=config.usar_prob_empirica,
            min_amostras_empirica=config.min_amostras_empirica,
        )

        df_top = rankear_calls(df, config, dados.preco_atual)
        if df_top.empty:
            logger.info("[%s] Nenhuma opção passou nos filtros (prob/prazo/retorno).", ativo)
            return pd.DataFrame()

        df_top["ativo"] = ativo
        return df_top

    except Exception as exc:  # noqa: BLE001 — isola falha por ativo
        logger.error("[%s] Erro ao processar: %s", ativo, exc)
        return pd.DataFrame()
