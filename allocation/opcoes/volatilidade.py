"""Análise de volatilidade: term structure, cone, rank/percentile e skew.

Sem histórico de IV na fonte de dados, o IV rank verdadeiro é inviável; o
rank/percentile aqui é um proxy calculado sobre a volatilidade realizada
rolante (janela curta vs. distribuição de lookback). O prêmio de volatilidade
(iv_atm − vol realizada) complementa a leitura de prêmio caro/barato.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado
from allocation.logging_setup import obter_logger
from allocation.models.volatility import volatilidade_realizada

logger = obter_logger(__name__)

JANELAS_CONE = (21, 63, 126, 252)


def _dias_ate(expiration: pd.Series) -> pd.Series:
    hoje = pd.Timestamp.today().normalize()
    return (pd.to_datetime(expiration).dt.normalize() - hoje).dt.days


def _iv_atm(grupo: pd.DataFrame, preco_atual: float) -> float:
    """IV do strike mais próximo do spot dentro de um vencimento."""
    ivs = grupo.dropna(subset=["impliedVolatility"])
    ivs = ivs[ivs["impliedVolatility"] > 0]
    if ivs.empty:
        return float("nan")
    idx = (ivs["strike"] - preco_atual).abs().idxmin()
    return float(ivs["impliedVolatility"].loc[idx])


def term_structure_iv(df_opcoes: pd.DataFrame, preco_atual: float) -> pd.DataFrame:
    """Estrutura a termo da IV: uma linha por vencimento (futuro).

    Colunas: expiration, dias_vencimento, iv_atm, iv_media, n_opcoes.
    """
    if df_opcoes.empty:
        return pd.DataFrame(
            columns=["expiration", "dias_vencimento", "iv_atm", "iv_media", "n_opcoes"]
        )

    df = df_opcoes.copy()
    df["dias_vencimento"] = _dias_ate(df["expiration"])
    df = df[df["dias_vencimento"] > 0]

    linhas = []
    for expiration, grupo in df.groupby("expiration", sort=True):
        ivs_validas = grupo["impliedVolatility"].dropna()
        ivs_validas = ivs_validas[ivs_validas > 0]
        linhas.append({
            "expiration": expiration,
            "dias_vencimento": int(grupo["dias_vencimento"].iloc[0]),
            "iv_atm": _iv_atm(grupo, preco_atual),
            "iv_media": float(ivs_validas.mean()) if not ivs_validas.empty else float("nan"),
            "n_opcoes": len(grupo),
        })
    return pd.DataFrame(linhas).sort_values("dias_vencimento", ignore_index=True)


def cone_volatilidade(
    historico: pd.Series, janelas: tuple[int, ...] = JANELAS_CONE
) -> pd.DataFrame:
    """Cone de volatilidade realizada: vol anualizada por janela de pregões.

    Janelas maiores que o histórico disponível produzem NaN.
    """
    linhas = []
    for janela in janelas:
        n_retornos = max(len(historico) - 1, 0) if historico is not None else 0
        vol = (
            volatilidade_realizada(historico, janela=janela)
            if n_retornos >= janela
            else float("nan")
        )
        linhas.append({"janela": janela, "vol_realizada": vol})
    return pd.DataFrame(linhas)


def rank_percentile_vol(
    historico: pd.Series, janela: int = 21, lookback: int = 252
) -> dict[str, float]:
    """Rank e percentile da vol realizada corrente vs. a distribuição rolante.

    Proxy de IV rank: posição da vol de ``janela`` pregões de hoje dentro da
    série de vols rolantes dos últimos ``lookback`` pregões.
    rank = (atual − min) / (max − min); percentile = fração de vols <= atual.
    """
    resultado = {"vol_atual": float("nan"), "vol_rank": float("nan"),
                 "vol_percentile": float("nan")}
    if historico is None or len(historico) < janela + 2:
        return resultado

    log_ret = np.log(historico.to_numpy(dtype=float)[1:]
                     / historico.to_numpy(dtype=float)[:-1])
    serie_ret = pd.Series(log_ret).dropna()
    vols = serie_ret.rolling(janela).std(ddof=1) * np.sqrt(252)
    vols = vols.dropna().iloc[-lookback:]
    if len(vols) < 2:
        return resultado

    atual = float(vols.iloc[-1])
    v_min, v_max = float(vols.min()), float(vols.max())
    resultado["vol_atual"] = atual
    resultado["vol_rank"] = (
        (atual - v_min) / (v_max - v_min) if v_max > v_min else float("nan")
    )
    resultado["vol_percentile"] = float((vols <= atual).mean())
    return resultado


def skew_por_vencimento(
    df_calls: pd.DataFrame, df_puts: pd.DataFrame, preco_atual: float
) -> pd.DataFrame:
    """Skew por vencimento, medido por moneyness (sem depender de greeks).

    skew_put_call: IV da put a 95% do spot − IV da call a 105% do spot
    (positivo = puts OTM mais caras, o padrão em equities).
    skew_otm_atm: IV OTM (call 105%) − IV ATM.
    Sem puts na fonte, calcula apenas o skew de calls e marca fonte_skew.
    """
    colunas = ["expiration", "dias_vencimento", "skew_put_call",
               "skew_otm_atm", "fonte_skew"]
    if df_calls.empty:
        return pd.DataFrame(columns=colunas)

    tem_puts = df_puts is not None and not df_puts.empty

    def _iv_no_moneyness(grupo: pd.DataFrame, alvo: float) -> float:
        ivs = grupo.dropna(subset=["impliedVolatility"])
        ivs = ivs[ivs["impliedVolatility"] > 0]
        if ivs.empty:
            return float("nan")
        idx = (ivs["strike"] - alvo).abs().idxmin()
        return float(ivs["impliedVolatility"].loc[idx])

    calls = df_calls.copy()
    calls["dias_vencimento"] = _dias_ate(calls["expiration"])
    calls = calls[calls["dias_vencimento"] > 0]
    puts = pd.DataFrame()
    if tem_puts:
        puts = df_puts.copy()
        puts["dias_vencimento"] = _dias_ate(puts["expiration"])
        puts = puts[puts["dias_vencimento"] > 0]

    linhas = []
    for expiration, grupo_calls in calls.groupby("expiration", sort=True):
        iv_atm = _iv_no_moneyness(grupo_calls, preco_atual)
        iv_call_otm = _iv_no_moneyness(grupo_calls, preco_atual * 1.05)

        if tem_puts:
            grupo_puts = puts[puts["expiration"] == expiration]
            iv_put_otm = (
                _iv_no_moneyness(grupo_puts, preco_atual * 0.95)
                if not grupo_puts.empty else float("nan")
            )
            skew_put_call = iv_put_otm - iv_call_otm
            fonte = "puts_e_calls"
        else:
            skew_put_call = float("nan")
            fonte = "apenas_calls"

        linhas.append({
            "expiration": expiration,
            "dias_vencimento": int(grupo_calls["dias_vencimento"].iloc[0]),
            "skew_put_call": skew_put_call,
            "skew_otm_atm": iv_call_otm - iv_atm,
            "fonte_skew": fonte,
        })
    return pd.DataFrame(linhas).sort_values("dias_vencimento", ignore_index=True)


def analisar_volatilidade(dados: DadosMercado, config: Config) -> dict[str, pd.DataFrame]:
    """Consolida a análise de volatilidade de um ativo.

    Retorna dict com 4 DataFrames: ``resumo`` (1 linha), ``term_structure``,
    ``cone`` e ``skew``.
    """
    term = term_structure_iv(dados.df_calls, dados.preco_atual)
    cone = cone_volatilidade(dados.historico_precos)
    rank = rank_percentile_vol(dados.historico_precos)
    skew = skew_por_vencimento(dados.df_calls, dados.df_puts, dados.preco_atual)

    iv_atm_curta = float(term["iv_atm"].iloc[0]) if not term.empty else float("nan")
    vol_21d = float(
        cone.loc[cone["janela"] == 21, "vol_realizada"].iloc[0]
    ) if not cone.empty else float("nan")
    skew_curto = float(skew["skew_put_call"].iloc[0]) if not skew.empty else float("nan")

    resumo = pd.DataFrame([{
        "ativo": dados.ativo,
        "preco_atual": dados.preco_atual,
        "iv_atm_curta": iv_atm_curta,
        "vol_21d": vol_21d,
        "premio_vol": iv_atm_curta - vol_21d,
        "vol_atual": rank["vol_atual"],
        "vol_rank": rank["vol_rank"],
        "vol_percentile": rank["vol_percentile"],
        "skew_curto": skew_curto,
    }])
    return {"resumo": resumo, "term_structure": term, "cone": cone, "skew": skew}
