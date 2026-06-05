"""Camada de dados: provedores de mercado intercambiáveis."""

from allocation.data.base import DadosMercado, ProvedorDados
from allocation.data.mock_provider import ProvedorMock, salvar_dados_mock
from allocation.data.yfinance_provider import ProvedorYFinance

__all__ = [
    "DadosMercado",
    "ProvedorDados",
    "ProvedorMock",
    "ProvedorYFinance",
    "salvar_dados_mock",
]
