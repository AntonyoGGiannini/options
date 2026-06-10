"""Filtros, score e ranking de venda de puts cash-secured por ativo.

Estratégia espelho das covered calls: venda de put OTM com probabilidade de
exercício controlada. Combinada com opcoes/calls.py forma o Wheel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado, ProvedorDados
from allocation.data.mock_provider import salvar_dados_mock
from allocation.logging_setup import obter_logger
from allocation.opcoes.pipeline import preparar_puts_para_modelo

logger = obter_logger(__name__)


def rankear_puts(
    df: pd.DataFrame,
    config: Config,
    preco_atual: float,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Aplica custos, filtros e score à cadeia de puts, retornando o top-N.

    Economia da put vendida cash-secured (mesmas convenções de custo das calls):
    o prêmio líquido desconta o custo de venda e o custo de exercício (compra
    das ações pelo strike) ponderado pela probabilidade de exercício. O retorno
    é medido sobre o colateral (strike), o capital efetivamente reservado.

    matriz_out: se fornecido, recebe (append) o DataFrame completo de candidatas
    com a coluna ``status`` — mesmo contrato da matriz de calls.
    """
    custo_venda_por_acao = config.custo_venda / config.tamanho_contrato

    # custo de exercício (atribuição) por contrato: na put exercida as ações são
    # compradas pelo strike — mesma base de cálculo do exercício da call.
    custo_exerc_contrato = (
        np.maximum(
            config.custo_exercicio_pct * df["strike"] * config.tamanho_contrato,
            config.custo_exercicio_min,
        )
        + config.custo_exercicio
    )
    custo_exerc_por_acao = custo_exerc_contrato / config.tamanho_contrato
    df["custo_exercicio_contrato"] = custo_exerc_contrato

    df["premio_liquido"] = (
        df["premio"] - custo_venda_por_acao - custo_exerc_por_acao * df["prob_exercicio_final"]
    )

    # colateral: caixa reservado para comprar as ações se exercido
    df["colateral_por_acao"] = df["strike"]
    df["colateral_por_contrato"] = df["strike"] * config.tamanho_contrato
    df["rendimento_liquido"] = df["premio_liquido"] / df["strike"]
    df["retorno_anualizado_liquido"] = df["rendimento_liquido"] / df["T"]

    # preço efetivo de compra se exercido: condicional ao exercício, o custo de
    # atribuição incide integral (não ponderado pela probabilidade) — mesma
    # convenção do lucro_se_exercido das calls.
    premio_se_exercido = df["premio"] - custo_venda_por_acao - custo_exerc_por_acao
    df["preco_efetivo_se_exercido"] = df["strike"] - premio_se_exercido
    df["desconto_vs_spot"] = 1 - df["preco_efetivo_se_exercido"] / preco_atual

    passou_liquidez = (
        df["passou_liquidez"]
        if "passou_liquidez" in df.columns
        else pd.Series(True, index=df.index)
    )

    cond_prob = df["prob_exercicio_final"] <= config.prob_exerc_max
    cond_strike = df["distancia_strike_pct"] >= config.min_distancia_strike_pct
    cond_retorno = df["retorno_anualizado_liquido"] > config.min_retorno_anualizado_liquido

    condicoes = passou_liquidez & cond_prob & cond_strike & cond_retorno

    # status por precedência (mesmos rótulos da matriz de calls)
    df["status"] = np.select(
        [
            ~passou_liquidez,
            ~cond_prob,
            ~(cond_strike & cond_retorno),
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

    # put vendida: o decaimento do prêmio (theta) beneficia o vendedor — mesma
    # construção do score das calls.
    theta_eff = (
        (-df_filtrado["theta"] / config.dias_ano) / df_filtrado["premio_liquido"].clip(lower=1e-6)
    ).clip(lower=0)

    vega_risk = (
        (df_filtrado["vega"] * 0.01) / df_filtrado["premio_liquido"].clip(lower=1e-6)
    ).clip(lower=0)

    df_filtrado["score_venda"] = (
        df_filtrado["retorno_anualizado_liquido"]
        * (1 - df_filtrado["prob_exercicio_final"])
        * (1 + config.peso_theta * theta_eff)
        / (1 + config.peso_vega * vega_risk)
    )

    df_filtrado = df_filtrado.sort_values("score_venda", ascending=False)
    df_filtrado["ranking_ativo"] = range(1, len(df_filtrado) + 1)
    df_filtrado["preco_atual_ativo"] = preco_atual
    return df_filtrado.head(config.top_n)


def processar_ativo_puts(
    ativo: str,
    provedor: ProvedorDados,
    config: Config,
    salvar_mock: bool = False,
    matriz_out: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Obtém dados, calcula probabilidades, filtra e ranqueia puts de um ativo.

    Retorna DataFrame vazio (com aviso em log) em caso de erro ou ausência de
    puts, para não interromper o processamento dos demais ativos.
    """
    try:
        dados: DadosMercado = provedor.obter(ativo, config.periodo_historico)

        if salvar_mock:
            salvar_dados_mock(
                ativo,
                dados.df_calls,
                dados.preco_atual,
                dados.historico_precos,
                config.pasta_mock,
                df_puts=dados.df_puts,
            )

        if dados.df_puts.empty:
            logger.info("[%s] Nenhuma put disponível na fonte de dados.", ativo)
            return pd.DataFrame()

        historico = dados.historico_precos if config.usar_prob_empirica else None

        df = preparar_puts_para_modelo(
            dados.df_puts,
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

        matriz_local: list[pd.DataFrame] = []
        df_top = rankear_puts(
            df,
            config,
            dados.preco_atual,
            matriz_out=matriz_local if matriz_out is not None else None,
        )
        if matriz_out is not None:
            for m in matriz_local:
                m["ativo"] = ativo
            matriz_out.extend(matriz_local)
        if df_top.empty:
            logger.info("[%s] Nenhuma put passou nos filtros (prob/prazo/retorno).", ativo)
            return pd.DataFrame()

        df_top["ativo"] = ativo
        return df_top

    except Exception as exc:  # noqa: BLE001 — isola falha por ativo
        logger.error("[%s] Erro ao processar puts: %s", ativo, exc)
        return pd.DataFrame()
