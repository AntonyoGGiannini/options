"""Probabilidade empírica histórica de exercício."""

from __future__ import annotations

import numpy as np


def calcular_probabilidade_empirica_batch(precos, preco_atual_arr, strike_arr,
                                          dias_janela_arr, min_amostras=30):
    """
    Calcula historicamente quantas vezes o ativo superou o strike em janelas
    equivalentes ao prazo de cada opção. Agrupa por janela para eficiência.

    Usa janelas não-sobrepostas (passo = janela) para evitar autocorrelação entre
    amostras. Com 5 anos de histórico (≈1260 pregões) e janelas de 7–20 dias,
    produz 63–180 amostras independentes, sempre acima de min_amostras=30.

    Retorna: (probs array, usa_empirica bool array)
    """
    n = len(strike_arr)
    probs = np.full(n, np.nan, dtype=float)
    usa_empirica = np.zeros(n, dtype=bool)

    for janela in np.unique(dias_janela_arr):
        mask = dias_janela_arr == janela
        # janelas não-sobrepostas: passo = janela
        retornos_futuros = (precos.shift(-int(janela)) / precos - 1).iloc[::int(janela)]
        retornos_validos = retornos_futuros.dropna()
        if len(retornos_validos) < min_amostras:
            continue
        for i in np.where(mask)[0]:
            ret_nec = (strike_arr[i] / preco_atual_arr[i]) - 1
            probs[i] = float((retornos_validos >= ret_nec).mean())
            usa_empirica[i] = True

    return probs, usa_empirica
