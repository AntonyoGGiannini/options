"""Camada de dados: provedores de mercado intercambiáveis."""

from options.data.base import DadosMercado, ProvedorDados
from options.data.mock_provider import ProvedorMock, salvar_dados_mock
from options.data.yfinance_provider import ProvedorYFinance

__all__ = [
    "DadosMercado",
    "ProvedorDados",
    "ProvedorMock",
    "ProvedorYFinance",
    "salvar_dados_mock",
]
