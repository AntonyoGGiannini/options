"""Orquestração de alto nível: roda a análise completa a partir de uma Config."""

from __future__ import annotations

import pandas as pd

from allocation.config import Config
from allocation.data.base import ProvedorDados
from allocation.data.cache import CacheDisco
from allocation.data.chains_historicas import StoreChainsHistoricas
from allocation.data.mock_provider import ProvedorMock
from allocation.data.yfinance_provider import ProvedorYFinance
from allocation.logging_setup import obter_logger
from allocation.opcoes.backtest import backtest_covered_call
from allocation.opcoes.backtest_chains import (
    calibracao_probabilidade,
    replay_screener_chains,
    validar_parametros_grid,
)
from allocation.opcoes.calls import processar_ativo
from allocation.opcoes.hedge import avaliar_collar, avaliar_protective_put
from allocation.opcoes.puts import processar_ativo_puts
from allocation.opcoes.spreads import avaliar_bull_call_spreads, avaliar_iron_condors
from allocation.opcoes.volatilidade import analisar_volatilidade
from allocation.report import (
    gerar_grafico_melhor,
    montar_matriz_output,
    montar_output,
    montar_output_puts,
    salvar_excel,
    salvar_matriz_completa,
)

logger = obter_logger(__name__)


def construir_provedor(config: Config) -> ProvedorDados:
    """Seleciona o provedor de dados conforme a configuração."""
    if config.modo_offline:
        return ProvedorMock(config.pasta_mock)
    cache = CacheDisco(config.pasta_cache, config.cache_ttl_horas) if config.usar_cache else None
    return ProvedorYFinance(cache=cache)


def executar(
    config: Config,
    provedor: ProvedorDados | None = None,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Processa todos os ativos da config e retorna o ranking consolidado.

    matriz_out: se fornecido, recebe (extend) a matriz completa de candidatas de
    todos os ativos, com a coluna ``status`` por opção.
    """
    if provedor is None:
        provedor = construir_provedor(config)

    resultados = []
    for ativo in config.lista_ativos:
        logger.info(">>> Processando %s...", ativo)
        df_top = processar_ativo(
            ativo,
            provedor,
            config,
            salvar_mock=config.salvar_mock and not config.modo_offline,
            matriz_out=matriz_out,
        )
        if not df_top.empty:
            resultados.append(df_top)

    if not resultados:
        logger.warning("Nenhuma opção encontrada para os ativos analisados.")
        return pd.DataFrame()

    return pd.concat(resultados, ignore_index=True)


def executar_e_reportar(config: Config, provedor: ProvedorDados | None = None) -> pd.DataFrame:
    """Executa a análise, imprime o resumo, salva Excel e gera o gráfico."""
    matriz: list[pd.DataFrame] = []
    df_final = executar(config, provedor, matriz_out=matriz)

    # matriz completa (todas as candidatas, com status) — gerada mesmo quando
    # nenhuma opção é selecionada.
    if matriz:
        df_matriz = montar_matriz_output(pd.concat(matriz, ignore_index=True))
        salvar_matriz_completa(df_matriz, config.arquivo_matriz)

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


def executar_puts(
    config: Config,
    provedor: ProvedorDados | None = None,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Processa puts cash-secured de todos os ativos e consolida o ranking.

    matriz_out: se fornecido, recebe (extend) a matriz completa de candidatas de
    todos os ativos, com a coluna ``status`` por opção.
    """
    if provedor is None:
        provedor = construir_provedor(config)

    resultados = []
    for ativo in config.lista_ativos:
        logger.info(">>> Processando puts de %s...", ativo)
        df_top = processar_ativo_puts(
            ativo,
            provedor,
            config,
            salvar_mock=config.salvar_mock and not config.modo_offline,
            matriz_out=matriz_out,
        )
        if not df_top.empty:
            resultados.append(df_top)

    if not resultados:
        logger.warning("Nenhuma put encontrada para os ativos analisados.")
        return pd.DataFrame()

    return pd.concat(resultados, ignore_index=True)


def executar_e_reportar_puts(config: Config, provedor: ProvedorDados | None = None) -> pd.DataFrame:
    """Executa a análise de puts, imprime o resumo e salva os Excel."""
    matriz: list[pd.DataFrame] = []
    df_final = executar_puts(config, provedor, matriz_out=matriz)

    if matriz:
        df_matriz = montar_matriz_output(pd.concat(matriz, ignore_index=True))
        salvar_matriz_completa(df_matriz, config.arquivo_matriz_puts)

    if df_final.empty:
        return df_final

    df_output = montar_output_puts(df_final)
    print("\n" + "=" * 80)
    print(f"TOP {config.top_n} PUTS CASH-SECURED POR ATIVO")
    print("=" * 80)
    print(df_output.to_string(index=False))

    salvar_excel(df_output, config.arquivo_excel_puts)
    return df_final


def executar_volatilidade(
    config: Config,
    provedor: ProvedorDados | None = None,
    arquivo_saida: str | None = None,
) -> pd.DataFrame:
    """Analisa a volatilidade de cada ativo e consolida o resumo (1 linha/ativo).

    Imprime o resumo e a term structure por ativo; se ``arquivo_saida`` for
    informado, salva um Excel com abas resumo / term_structure / cone / skew.
    """
    if provedor is None:
        provedor = construir_provedor(config)

    resumos = []
    detalhes: dict[str, list[pd.DataFrame]] = {
        "term_structure": [],
        "cone": [],
        "skew": [],
    }
    for ativo in config.lista_ativos:
        logger.info(">>> Analisando volatilidade de %s...", ativo)
        try:
            dados = provedor.obter(ativo, config.periodo_historico)
        except Exception as exc:  # noqa: BLE001 — isola falha por ativo
            logger.error("[%s] Erro ao obter dados: %s", ativo, exc)
            continue
        analise = analisar_volatilidade(dados, config)
        resumos.append(analise["resumo"])
        for chave in detalhes:
            df_detalhe = analise[chave].copy()
            df_detalhe.insert(0, "ativo", ativo)
            detalhes[chave].append(df_detalhe)

        print(f"\n=== {ativo} — term structure de IV ===")
        print(analise["term_structure"].to_string(index=False))

    if not resumos:
        logger.warning("Nenhum ativo analisado.")
        return pd.DataFrame()

    df_resumo = pd.concat(resumos, ignore_index=True)
    print("\n" + "=" * 80)
    print("RESUMO DE VOLATILIDADE POR ATIVO")
    print("=" * 80)
    print(df_resumo.to_string(index=False))

    if arquivo_saida:
        with pd.ExcelWriter(arquivo_saida) as writer:
            df_resumo.to_excel(writer, sheet_name="resumo", index=False)
            for chave, dfs in detalhes.items():
                if dfs:
                    pd.concat(dfs, ignore_index=True).to_excel(
                        writer, sheet_name=chave, index=False
                    )
        logger.info("Análise de volatilidade salva em: %s", arquivo_saida)

    return df_resumo


def executar_hedge(
    config: Config,
    ativo: str,
    preco_custo: float | None = None,
    top_n: int | None = None,
    provedor: ProvedorDados | None = None,
    arquivo_saida: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Avalia protective puts e collars para uma posição em um ativo.

    Imprime os melhores candidatos de cada estratégia; se ``arquivo_saida`` for
    informado, salva um Excel com abas protective_put / collar.
    """
    if provedor is None:
        provedor = construir_provedor(config)
    n = top_n if top_n is not None else config.top_n

    dados = provedor.obter(ativo, config.periodo_historico)
    df_pp = avaliar_protective_put(dados, config, preco_custo=preco_custo)
    df_collar = avaliar_collar(dados, config, preco_custo=preco_custo)

    if not df_pp.empty:
        print(f"\n=== {ativo} — protective puts (menor perda máxima) ===")
        print(df_pp.head(n).to_string(index=False))
    if not df_collar.empty:
        print(f"\n=== {ativo} — collars (proteção por unidade de custo) ===")
        print(df_collar.head(n).to_string(index=False))
    if df_pp.empty and df_collar.empty:
        logger.warning("[%s] Nenhuma estrutura de hedge viável.", ativo)

    if arquivo_saida and (not df_pp.empty or not df_collar.empty):
        with pd.ExcelWriter(arquivo_saida) as writer:
            if not df_pp.empty:
                df_pp.to_excel(writer, sheet_name="protective_put", index=False)
            if not df_collar.empty:
                df_collar.to_excel(writer, sheet_name="collar", index=False)
        logger.info("Análise de hedge salva em: %s", arquivo_saida)

    return {"protective_put": df_pp, "collar": df_collar}


def executar_spreads(
    config: Config,
    estrategia: str = "bull_call",
    top_n: int | None = None,
    provedor: ProvedorDados | None = None,
    arquivo_saida: str | None = None,
) -> pd.DataFrame:
    """Avalia spreads (bull_call ou iron_condor) para cada ativo da config.

    Imprime os melhores candidatos por ativo e retorna o consolidado; se
    ``arquivo_saida`` for informado, salva o resultado completo em Excel.
    """
    if estrategia not in {"bull_call", "iron_condor"}:
        raise ValueError("estrategia deve ser: bull_call ou iron_condor")
    if provedor is None:
        provedor = construir_provedor(config)
    n = top_n if top_n is not None else config.top_n
    avaliar = avaliar_bull_call_spreads if estrategia == "bull_call" else avaliar_iron_condors

    resultados = []
    for ativo in config.lista_ativos:
        logger.info(">>> Avaliando %s de %s...", estrategia, ativo)
        try:
            dados = provedor.obter(ativo, config.periodo_historico)
        except Exception as exc:  # noqa: BLE001 — isola falha por ativo
            logger.error("[%s] Erro ao obter dados: %s", ativo, exc)
            continue
        df = avaliar(dados, config)
        if df.empty:
            continue
        resultados.append(df)
        print(f"\n=== {ativo} — {estrategia} (melhores por score) ===")
        print(df.head(n).to_string(index=False))

    if not resultados:
        logger.warning("Nenhum spread viável para os ativos analisados.")
        return pd.DataFrame()

    df_final = pd.concat(resultados, ignore_index=True)
    if arquivo_saida:
        df_final.to_excel(arquivo_saida, index=False)
        logger.info("Análise de spreads salva em: %s", arquivo_saida)
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
        if (
            dados.historico_precos is None
            or len(dados.historico_precos) <= janela_vol + dias_vencimento
        ):
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


# grade usada por backtest-chains --grid quando a config não traz
# [grade_validacao]: varre o limite de probabilidade e a janela de prazo.
GRADE_VALIDACAO_DEFAULT: dict[str, list] = {
    "prob_exerc_max": [0.10, 0.15, 0.25],
    "max_dias": [20, 30, 45],
}


def _historico_para_replay(config: Config, ativo: str) -> pd.Series | None:
    """Série longa de fechamentos para prob. empírica/vol do replay."""
    try:
        dados = construir_provedor(config).obter(ativo, config.periodo_historico)
    except Exception as exc:  # noqa: BLE001 — replay funciona sem histórico
        logger.warning("[%s] Sem histórico de preços para o replay: %s", ativo, exc)
        return None
    return dados.historico_precos


def executar_baixar_chains(
    config: Config,
    ativo: str,
    inicio: str,
    fim: str,
    sobrescrever: bool = False,
) -> int:
    """Baixa chains EOD históricas (Theta Data) para o store local."""
    from allocation.data.thetadata import baixar_chains_historicas

    store = StoreChainsHistoricas(config.pasta_chains)
    n = baixar_chains_historicas(ativo, inicio, fim, store, sobrescrever=sobrescrever)
    logger.info("[%s] %d snapshots gravados em %s", ativo, n, config.pasta_chains)
    return n


def executar_backtest_chains(
    config: Config,
    ativo: str,
    inicio: str | None = None,
    fim: str | None = None,
    grid: bool = False,
    arquivo_saida: str | None = None,
    top_n_executar: int = 1,
    passo_dias: int | None = None,
) -> pd.DataFrame:
    """Replay do screener sobre chains históricas reais (validação de parâmetros).

    Sem ``grid``: roda o replay com a config atual, imprime resumo, trades e a
    calibração de probabilidade; Excel opcional com abas trades / resumo /
    calibracao. Com ``grid``: roda uma combinação por linha da grade
    (``[grade_validacao]`` da config, ou a default) e imprime/salva a tabela
    comparativa (aba grid).

    Retorna o DataFrame de trades (ou o do grid).
    """
    store = StoreChainsHistoricas(config.pasta_chains)
    if not store.datas_disponiveis(ativo, inicio, fim):
        logger.warning(
            "[%s] Nenhum snapshot em %s — rode 'allocation baixar-chains' antes.",
            ativo,
            config.pasta_chains,
        )
        return pd.DataFrame()

    historico = _historico_para_replay(config, ativo)

    if grid:
        grade = config.grade_validacao or GRADE_VALIDACAO_DEFAULT
        df_grid = validar_parametros_grid(
            ativo,
            store,
            config,
            grade,
            inicio=inicio,
            fim=fim,
            historico_precos=historico,
            top_n_executar=top_n_executar,
            passo_dias=passo_dias,
        )
        print("\n" + "=" * 80)
        print(f"GRID DE VALIDAÇÃO DE PARÂMETROS | {ativo}")
        print("=" * 80)
        print(df_grid.to_string(index=False))
        if arquivo_saida:
            with pd.ExcelWriter(arquivo_saida) as writer:
                df_grid.to_excel(writer, sheet_name="grid", index=False)
            logger.info("Grid de validação salvo em: %s", arquivo_saida)
        return df_grid

    df_trades, resumo = replay_screener_chains(
        ativo,
        store,
        config,
        inicio=inicio,
        fim=fim,
        historico_precos=historico,
        top_n_executar=top_n_executar,
        passo_dias=passo_dias,
    )
    df_resumo = pd.DataFrame([resumo.as_dict()])
    df_cal = calibracao_probabilidade(df_trades)

    print("\n" + "=" * 80)
    print(f"REPLAY DO SCREENER SOBRE CHAINS REAIS | {ativo}")
    print("=" * 80)
    print(df_resumo.to_string(index=False))
    if not df_trades.empty:
        print(f"\n=== {ativo} — trades executados ===")
        print(df_trades.to_string(index=False))
        print(f"\n=== {ativo} — calibração: prob prevista vs exercício realizado ===")
        print(df_cal.to_string(index=False))
    else:
        logger.warning("[%s] Nenhum trade executado no período.", ativo)

    if arquivo_saida:
        with pd.ExcelWriter(arquivo_saida) as writer:
            df_trades.to_excel(writer, sheet_name="trades", index=False)
            df_resumo.to_excel(writer, sheet_name="resumo", index=False)
            df_cal.to_excel(writer, sheet_name="calibracao", index=False)
        logger.info("Replay salvo em: %s", arquivo_saida)

    return df_trades
