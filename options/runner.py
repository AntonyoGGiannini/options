"""Orquestração de alto nível: roda a análise completa a partir de uma Config."""

from __future__ import annotations

import pandas as pd

from options.backtest import backtest_covered_call
from options.config import Config
from options.data.base import ProvedorDados
from options.data.cache import CacheDisco
from options.data.mock_provider import ProvedorMock
from options.data.yfinance_provider import ProvedorYFinance
from options.logging_setup import obter_logger
from options.ranking import processar_ativo
from options.report import gerar_grafico_melhor, montar_output, salvar_excel

logger = obter_logger(__name__)


def construir_provedor(config: Config) -> ProvedorDados:
    """Seleciona o provedor de dados conforme a configuração."""
    if config.modo_offline:
        return ProvedorMock(config.pasta_mock)
    cache = (
        CacheDisco(config.pasta_cache, config.cache_ttl_horas)
        if config.usar_cache
        else None
    )
    return ProvedorYFinance(cache=cache)


def executar(config: Config, provedor: ProvedorDados | None = None) -> pd.DataFrame:
    """Processa todos os ativos da config e retorna o ranking consolidado."""
    if provedor is None:
        provedor = construir_provedor(config)

    resultados = []
    for ativo in config.lista_ativos:
        logger.info(">>> Processando %s...", ativo)
        df_top = processar_ativo(
            ativo, provedor, config,
            salvar_mock=config.salvar_mock and not config.modo_offline,
        )
        if not df_top.empty:
            resultados.append(df_top)

    if not resultados:
        logger.warning("Nenhuma opção encontrada para os ativos analisados.")
        return pd.DataFrame()

    return pd.concat(resultados, ignore_index=True)


def executar_e_reportar(config: Config, provedor: ProvedorDados | None = None) -> pd.DataFrame:
    """Executa a análise, imprime o resumo, salva Excel e gera o gráfico."""
    df_final = executar(config, provedor)
    if df_final.empty:
        return df_final

    df_output = montar_output(df_final)
    print("\n" + "=" * 80)
    print(f"TOP {config.top_n} COVERED CALLS POR ATIVO")
    print("=" * 80)
    print(df_output.to_string(index=False))

    salvar_excel(df_output, config.arquivo_excel)
    gerar_grafico_melhor(df_final, config)
    return df_final


def executar_backtest(
    config: Config,
    distancia_strike_pct: float = 0.05,
    dias_vencimento: int = 14,
    janela_vol: int = 60,
    provedor: ProvedorDados | None = None,
) -> pd.DataFrame:
    """Roda o backtest de covered call para cada ativo e retorna os resumos."""
    if provedor is None:
        provedor = construir_provedor(config)

    resumos = []
    for ativo in config.lista_ativos:
        try:
            dados = provedor.obter(ativo, config.periodo_historico)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] Erro ao obter histórico para backtest: %s", ativo, exc)
            continue
        if dados.historico_precos is None or len(dados.historico_precos) <= janela_vol + dias_vencimento:
            logger.info("[%s] Histórico insuficiente para backtest.", ativo)
            continue
        _, resumo = backtest_covered_call(
            dados.historico_precos,
            ativo=ativo,
            distancia_strike_pct=distancia_strike_pct,
            dias_vencimento=dias_vencimento,
            taxa_livre_risco=config.taxa_livre_risco,
            dividend_yield=config.dividend_para(ativo),
            janela_vol=janela_vol,
        )
        resumos.append(resumo.as_dict())

    return pd.DataFrame(resumos)
