"""Backtest da estratégia de covered call sobre o histórico de preços.

Sem dados históricos de cadeias de opções, o prêmio é estimado por Black-Scholes
usando a **volatilidade realizada** disponível em cada data de entrada. É,
portanto, um backtest *baseado em modelo*: valida a lógica de seleção de strike e
horizonte (e o trade-off retorno × probabilidade de exercício), não eventuais
desvios de preço do mercado de opções.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from allocation.models.black_scholes import preco_call_bs
from allocation.models.volatility import DIAS_PREGAO_ANO, volatilidade_realizada


@dataclass
class ResumoBacktest:
    ativo: str
    n_trades: int
    distancia_strike_pct: float
    dias_vencimento: int
    retorno_medio_cc: float
    retorno_anualizado_cc: float
    taxa_exercicio: float
    taxa_acerto: float
    retorno_medio_buy_hold: float
    vol_retorno_cc: float

    def as_dict(self) -> dict:
        return asdict(self)


def backtest_covered_call(
    precos: pd.Series,
    ativo: str = "?",
    distancia_strike_pct: float = 0.05,
    dias_vencimento: int = 14,
    taxa_livre_risco: float = 0.045,
    dividend_yield: float = 0.0,
    janela_vol: int = 60,
    passo: int | None = None,
) -> tuple[pd.DataFrame, ResumoBacktest]:
    """Simula vendas sucessivas de covered call no histórico.

    Em cada data de entrada: estima a vol realizada (últimos ``janela_vol``
    pregões), define o strike ``S0 * (1 + distancia)``, precifica o prêmio por
    Black-Scholes e mantém até o vencimento (``dias_vencimento`` pregões).

    Retorna (df_trades, resumo).
    """
    precos = precos.dropna().reset_index(drop=True)
    h = dias_vencimento
    passo = passo if passo is not None else h
    T = h / DIAS_PREGAO_ANO

    registros = []
    inicio = max(janela_vol, 1)
    for t in range(inicio, len(precos) - h, passo):
        vol = volatilidade_realizada(precos.iloc[: t + 1], janela=janela_vol)
        if not np.isfinite(vol) or vol <= 0:
            continue
        s0 = float(precos.iloc[t])
        k = s0 * (1 + distancia_strike_pct)
        premio = preco_call_bs(s0, k, T, taxa_livre_risco, dividend_yield, vol)
        if not np.isfinite(premio):
            continue
        s_final = float(precos.iloc[t + h])

        exercido = s_final > k
        valor_acao = min(s_final, k)
        retorno_cc = (valor_acao - s0 + premio) / s0
        retorno_bh = (s_final - s0) / s0

        registros.append(
            {
                "idx": t,
                "S0": s0,
                "strike": k,
                "vol": vol,
                "premio": premio,
                "S_final": s_final,
                "exercido": exercido,
                "retorno_cc": retorno_cc,
                "retorno_buy_hold": retorno_bh,
            }
        )

    df = pd.DataFrame(registros)
    if df.empty:
        resumo = ResumoBacktest(
            ativo,
            0,
            distancia_strike_pct,
            dias_vencimento,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
        )
        return df, resumo

    retorno_medio = float(df["retorno_cc"].mean())
    resumo = ResumoBacktest(
        ativo=ativo,
        n_trades=len(df),
        distancia_strike_pct=distancia_strike_pct,
        dias_vencimento=dias_vencimento,
        retorno_medio_cc=retorno_medio,
        retorno_anualizado_cc=retorno_medio * (DIAS_PREGAO_ANO / h),
        taxa_exercicio=float(df["exercido"].mean()),
        taxa_acerto=float((df["retorno_cc"] > 0).mean()),
        retorno_medio_buy_hold=float(df["retorno_buy_hold"].mean()),
        vol_retorno_cc=float(df["retorno_cc"].std(ddof=1)) if len(df) > 1 else float("nan"),
    )
    return df, resumo
