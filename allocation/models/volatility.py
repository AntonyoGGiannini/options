"""Volatilidade realizada (histórica) anualizada."""

from __future__ import annotations

import numpy as np
import pandas as pd

DIAS_PREGAO_ANO = 252


def volatilidade_realizada(precos: pd.Series, janela: int | None = None,
                           dias_ano: int = DIAS_PREGAO_ANO) -> float:
    """Volatilidade anualizada a partir dos log-retornos diários.

    janela: usa apenas os últimos N pregões (None = série inteira).
    Retorna NaN se não houver dados suficientes.
    """
    if precos is None or len(precos) < 3:
        return float("nan")
    valores = precos.to_numpy(dtype=float)
    log_ret = np.log(valores[1:] / valores[:-1])
    log_ret = log_ret[np.isfinite(log_ret)]
    if janela is not None:
        log_ret = log_ret[-janela:]
    if len(log_ret) < 2:
        return float("nan")
    return float(np.std(log_ret, ddof=1) * np.sqrt(dias_ano))
