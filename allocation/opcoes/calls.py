"""Filtros, score e ranking de covered calls por ativo."""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado, ProvedorDados
from allocation.data.mock_provider import salvar_dados_mock
from allocation.logging_setup import obter_logger
from allocation.opcoes.pipeline import preparar_calls_para_modelo

logger = obter_logger(__name__)


def rankear_calls(
    df: pd.DataFrame,
    config: Config,
    preco_atual: float,
    preco_custo: float | None = None,
    excluir_prejuizo_exercicio: bool = True,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Aplica custos, filtros e score, retornando as top-N opções ranqueadas.

    preco_custo: preço médio de aquisição do ativo pelo cliente. É opcional e
    irrelevante para o screener (varredura de oportunidades). Quando fornecido —
    ao analisar uma posição já existente — adiciona colunas de custo
    (retorno_sobre_custo, capital_por_contrato, alerta_abaixo_custo) e sinaliza
    contratos cujo strike trancaria prejuízo. Sem ele, a saída fica enxuta.

    excluir_prejuizo_exercicio: quando True (padrão), descarta operações que
    dariam prejuízo se a call fosse exercida — i.e. ``lucro_se_exercido <= 0``.
    O lucro no exercício considera a venda das ações pelo strike, o prêmio e os
    custos de venda e de exercício (e de compra, no buy-write). A base de custo é
    o preço médio do cliente (se informado) ou o preço de mercado (buy-write).

    matriz_out: se fornecido, recebe (append) o DataFrame completo de candidatas
    — todas as opções da janela, com a coluna ``status`` indicando o motivo de
    reprovação ou ``"ok"``. Coletado antes de qualquer recorte, inclusive quando
    nenhuma opção passa nos filtros.
    """
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato

    # custo de exercício por contrato depende do strike: max(pct * valor de
    # venda, mínimo) + taxa fixa. Convertido para base por ação.
    custo_exerc_contrato = np.maximum(
        config.custo_exercicio_pct * df["strike"] * config.tamanho_contrato,
        config.custo_exercicio_min,
    ) + config.custo_exercicio
    custo_exerc_por_acao = custo_exerc_contrato / config.tamanho_contrato
    df["custo_exercicio_contrato"] = custo_exerc_contrato

    # prêmio líquido esperado: desconta o custo de venda e o custo de exercício
    # ponderado pela probabilidade de a call ser exercida.
    df["premio_liquido"] = (
        df["premio"]
        - custo_venda_por_acao
        - custo_exerc_por_acao * df["prob_exercicio_final"]
    )
    df["rendimento_liquido"] = df["premio_liquido"] / df["preco_atual"]
    df["retorno_anualizado_liquido"] = df["rendimento_liquido"] / df["T"]

    # lucro por ação se a call for exercida (ações entregues pelo strike):
    # (strike - base de custo) + prêmio - custos. No buy-write inclui o custo de
    # compra; numa posição já existente o custo de compra é afundado.
    base_custo = preco_custo if preco_custo is not None else preco_atual
    custo_compra_por_acao = (
        config.custo_compra / config.tamanho_contrato if preco_custo is None else 0.0
    )
    df["lucro_se_exercido"] = (
        (df["strike"] - base_custo)
        + df["premio"]
        - custo_venda_por_acao
        - custo_exerc_por_acao
        - custo_compra_por_acao
    )

    # retorno se a call for exercida e as ações entregues ao strike, anualizado
    df["retorno_se_exercido_anualizado"] = df["lucro_se_exercido"] / df["preco_atual"] / df["T"]

    # downside protection: quanto o ativo pode cair antes do break-even (não anualizado)
    df["downside_protection"] = df["premio"] / df["preco_atual"]

    # liquidez vira condição do ranking (antes as ilíquidas eram descartadas no
    # provedor). Mocks/dados sem a coluna são tratados como líquidos.
    passou_liquidez = (
        df["passou_liquidez"]
        if "passou_liquidez" in df.columns
        else pd.Series(True, index=df.index)
    )

    cond_prob = df["prob_exercicio_final"] <= config.prob_exerc_max
    cond_strike = df["distancia_strike_pct"] >= config.min_distancia_strike_pct
    cond_retorno = df["retorno_anualizado_liquido"] > config.min_retorno_anualizado_liquido
    cond_lucro = (
        df["lucro_se_exercido"] > config.min_lucro_se_exercido
        if excluir_prejuizo_exercicio
        else pd.Series(True, index=df.index)
    )

    condicoes = passou_liquidez & cond_prob & cond_strike & cond_retorno & cond_lucro

    # status por precedência (primeiro motivo de reprovação vence)
    df["status"] = np.select(
        [
            ~passou_liquidez,
            ~cond_prob,
            ~(cond_strike & cond_retorno & cond_lucro),
        ],
        [
            "fora do filtro de liquidez",
            "fora do filtro de probabilidade de exercicio",
            "fora dos filtros (retorno/strike/lucro)",
        ],
        default="ok",
    )

    if matriz_out is not None:
        matriz_out.append(df.copy())

    df_filtrado = df[condicoes].copy()

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
        df_filtrado["retorno_se_exercido_anualizado"]
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
    excluir_prejuizo_exercicio: bool = True,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Obtém dados, calcula probabilidades, filtra e ranqueia um ativo.

    preco_custo: preço médio de aquisição da posição. Quando informado
    explicitamente (ex.: pela análise de carteira) tem precedência; caso
    contrário cai no valor da config (None no screener → saída enxuta).

    excluir_prejuizo_exercicio: repassado a ``rankear_calls`` — descarta
    operações que dariam prejuízo se a call fosse exercida (padrão True).

    matriz_out: se fornecido, recebe (extend) a matriz completa de candidatas do
    ativo, já com a coluna ``ativo``. Coletada mesmo quando nada passa nos filtros.

    Retorna DataFrame vazio (com aviso em log) em caso de erro ou ausência de
    opções, para não interromper o processamento dos demais ativos.
    """
    try:
        dados: DadosMercado = provedor.obter(ativo, config.periodo_historico)

        if salvar_mock:
            salvar_dados_mock(
                ativo, dados.df_calls, dados.preco_atual,
                dados.historico_precos, config.pasta_mock,
                df_puts=dados.df_puts,
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
            liquidez_volume_min=config.liquidez_volume_min,
            liquidez_open_interest_min=config.liquidez_open_interest_min,
            liquidez_spread_max=config.liquidez_spread_max,
        )

        if preco_custo is None:
            preco_custo = config.preco_custo_para(ativo)
        matriz_local: list[pd.DataFrame] = []
        df_top = rankear_calls(
            df, config, dados.preco_atual, preco_custo=preco_custo,
            excluir_prejuizo_exercicio=excluir_prejuizo_exercicio,
            matriz_out=matriz_local if matriz_out is not None else None,
        )
        if matriz_out is not None:
            for m in matriz_local:
                m["ativo"] = ativo
            matriz_out.extend(matriz_local)
        if df_top.empty:
            logger.info("[%s] Nenhuma opção passou nos filtros (prob/prazo/retorno).", ativo)
            return pd.DataFrame()

        df_top["ativo"] = ativo
        return df_top

    except Exception as exc:  # noqa: BLE001 — isola falha por ativo
        logger.error("[%s] Erro ao processar: %s", ativo, exc)
        return pd.DataFrame()
