"""Contratos da camada de dados: container e interface de provedor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass
class DadosMercado:
    """Dados de mercado de um ativo, agnósticos à fonte."""

    ativo: str
    df_calls: pd.DataFrame
    preco_atual: float
    historico_precos: pd.Series
    # cadeia de puts (opcional; vazia quando a fonte não fornece)
    df_puts: pd.DataFrame = field(default_factory=pd.DataFrame)


class ProvedorDados(Protocol):
    """Interface para qualquer fonte de dados de mercado.

    Permite trocar yfinance, mock ou qualquer outro provedor sem alterar o
    restante da aplicação.
    """

    def obter(self, ativo: str, periodo_historico: str = "5y") -> DadosMercado:
        """Retorna os dados de mercado de um ativo."""
        ...
