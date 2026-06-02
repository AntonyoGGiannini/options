"""Filtros, score e ranking de covered calls por ativo."""

from __future__ import annotations

import pandas as pd

from options.config import Config
from options.data.base import DadosMercado, ProvedorDados
from options.data.mock_provider import salvar_dados_mock
from options.logging_setup import obter_logger
from options.models.pipeline import preparar_calls_para_modelo

logger = obter_logger(__name__)


def rankear_calls(
    df: pd.DataFrame,
    config: Config,
    preco_atual: float,
    preco_custo: float | None = None,
) -> pd.DataFrame:
    """Aplica custos, filtros e score, retornando as top-N opções ranqueadas.

    preco_custo: preço médio de aquisição do ativo pelo cliente. É opcional e
    irrelevante para o screener (varredura de oportunidades). Quando fornecido —
    ao analisar uma posição já existente — adiciona colunas de custo
    (retorno_sobre_custo, capital_por_contrato, alerta_abaixo_custo) e sinaliza
    contratos cujo strike trancaria prejuízo. Sem ele, a saída fica enxuta.
    """
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato
    df["premio_liquido"] = df["premio"] - custo_venda_por_acao
    df["rendimento_liquido"] = df["premio_liquido"] / df["preco_atual"]
    df["retorno_anualizado_liquido"] = df["rendimento_liquido"] / df["T"]

    df_filtrado = df[
        (df["distancia_strike_pct"] >= config.min_distancia_strike_pct)
        & (df["prob_exercicio_final"] <= config.prob_exerc_max)
        & (df["retorno_anualizado_liquido"] > 0)
    ].copy()

    if df_filtrado.empty:
        return df_filtrado

    theta_eff = (
        (-df_filtrado["theta"] / config.dias_ano)
        / df_filtrado["premio_liquido"].clip(lower=1e-6)
    ).clip(lower=0)

    vega_risk = (
        (df_filtrado["vega"] * 0.01)
        / df_filtrado["premio_liquido"].clip(lower=1e-6)
    ).clip(lower=0)

    df_filtrado["score_venda"] = (
        df_filtrado["retorno_anualizado_liquido"]
        * (1 - df_filtrado["prob_exercicio_final"])
        * (1 + config.peso_theta * theta_eff)
        / (1 + config.peso_vega * vega_risk)
    )

    # --- métricas de custo: só ao analisar uma posição existente ---
    # No screener (sem preco_custo) essas colunas seriam constantes/irrelevantes,
    # então são omitidas para manter a saída enxuta.
    if preco_custo is not None:
        df_filtrado["capital_por_contrato"] = preco_custo * config.tamanho_contrato
        # retorno sobre o custo real da posição existente
        df_filtrado["retorno_sobre_custo"] = (
            df_filtrado["premio_liquido"] / preco_custo
        )
        # alerta: vender strike abaixo do custo trava prejuízo se exercido
        df_filtrado["alerta_abaixo_custo"] = df_filtrado["strike"] < preco_custo

    df_filtrado = df_filtrado.sort_values("score_venda", ascending=False)
    df_filtrado["ranking_ativo"] = range(1, len(df_filtrado) + 1)
    df_filtrado["preco_atual_ativo"] = preco_atual
    return df_filtrado.head(config.top_n)


def processar_ativo(
    ativo: str,
    provedor: ProvedorDados,
    config: Config,
    salvar_mock: bool = False,
    preco_custo: float | None = None,
) -> pd.DataFrame:
    """Obtém dados, calcula probabilidades, filtra e ranqueia um ativo.

    preco_custo: preço médio de aquisição da posição. Quando informado
    explicitamente (ex.: pela análise de carteira) tem precedência; caso
    contrário cai no valor da config (None no screener → saída enxuta).

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
            dividend_yield=config.dividend_para(ativo),
            usar_premio=config.usar_premio,
            t_min=config.min_dias,
            t_max=config.max_dias,
            dias_ano=config.dias_ano,
            historico_precos=historico,
            usar_prob_d2=config.usar_prob_d2,
            usar_prob_empirica=config.usar_prob_empirica,
            min_amostras_empirica=config.min_amostras_empirica,
        )

        if preco_custo is None:
            preco_custo = config.preco_custo_para(ativo)
        df_top = rankear_calls(df, config, dados.preco_atual, preco_custo=preco_custo)
        if df_top.empty:
            logger.info("[%s] Nenhuma opção passou nos filtros (prob/prazo/retorno).", ativo)
            return pd.DataFrame()

        df_top["ativo"] = ativo
        return df_top

    except Exception as exc:  # noqa: BLE001 — isola falha por ativo
        logger.error("[%s] Erro ao processar: %s", ativo, exc)
        return pd.DataFrame()
