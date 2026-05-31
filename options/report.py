"""Geração de relatórios: tabela, Excel e gráfico de payoff."""

from __future__ import annotations

import pandas as pd

from options.config import Config
from options.logging_setup import obter_logger
from options.models.payoff import gerar_grafico_payoff_covered_call

logger = obter_logger(__name__)

COLUNAS_OUTPUT = [
    "ativo",
    "ranking_ativo",
    "strike",
    "premio",
    "expiration",
    "dias_uteis_ate_vencimento",
    "prob_exercicio",
    "prob_empirica",
    "prob_exercicio_final",
    "retorno_anualizado_pct",
    "retorno_anualizado_liquido",
    "bid",
    "ask",
    "volume",
    "openInterest",
    "preco_atual_ativo",
    "score_venda",
]


def montar_output(df_final: pd.DataFrame) -> pd.DataFrame:
    """Seleciona as colunas de saída presentes no DataFrame."""
    colunas = [c for c in COLUNAS_OUTPUT if c in df_final.columns]
    return df_final[colunas].copy()


def salvar_excel(df_output: pd.DataFrame, caminho: str) -> str:
    """Salva o ranking em Excel."""
    df_output.to_excel(caminho, index=False)
    logger.info("Resultados salvos em: %s", caminho)
    return caminho


def _preco_custo_para(config: Config, ativo: str) -> float | None:
    pma = config.preco_medio_aquisicao
    if isinstance(pma, dict):
        return pma.get(ativo)
    if isinstance(pma, (int, float)):
        return float(pma)
    return None


def gerar_grafico_melhor(df_final: pd.DataFrame, config: Config) -> str | None:
    """Gera o gráfico de payoff da melhor opção geral (maior score)."""
    if df_final.empty:
        return None

    melhor = df_final.sort_values("score_venda", ascending=False).iloc[0]
    ativo_melhor = melhor["ativo"]
    preco_custo = _preco_custo_para(config, ativo_melhor)

    prob_emp = melhor.get("prob_empirica")
    prob_emp_str = f"{prob_emp:.2%}" if prob_emp is not None and not pd.isna(prob_emp) else "N/A"
    logger.info(
        "Melhor opção geral: %s | Strike %s | Venc. %s | Score %.4f | "
        "Prob. final %.2f%% (d2=%.2f%%, empírica=%s)",
        ativo_melhor, melhor["strike"], melhor["expiration"], melhor["score_venda"],
        melhor["prob_exercicio_final"] * 100, melhor["prob_exercicio"] * 100, prob_emp_str,
    )

    arquivo = gerar_grafico_payoff_covered_call(
        preco_atual=melhor["preco_atual_ativo"],
        strike=melhor["strike"],
        premio=melhor["premio"],
        expiration=melhor["expiration"],
        preco_custo=preco_custo,
        arquivo_saida=f"payoff_{ativo_melhor}.png",
    )
    logger.info("Gráfico de payoff salvo em: %s", arquivo)
    return arquivo
