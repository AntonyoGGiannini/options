"""Compatibilidade retroativa.

O código foi reorganizado no pacote ``options/``. Este módulo reexporta as
funções na sua localização antiga para não quebrar imports existentes.
Prefira importar diretamente de ``options.*`` em código novo.
"""

from __future__ import annotations

from options.data.mock_provider import salvar_dados_mock
from options.data.yfinance_provider import ProvedorYFinance as _Prov
from options.models import (
    calcular_premio_vetor,
    calcular_prob_acima_strike_monte_carlo,
    calcular_prob_acima_strike_monte_carlo_batch,
    calcular_prob_exercicio_risk_neutral,
    calcular_prob_exercicio_risk_neutral_vetor,
    calcular_probabilidade_empirica_batch,
    gerar_grafico_payoff_covered_call,
    preparar_calls_para_modelo,
)

_PROVEDOR = _Prov()


def calcular_preco_atual(ativo):
    return _PROVEDOR.calcular_preco_atual(ativo)


def carregar_historico_ativo(ativo, periodo="5y"):
    return _PROVEDOR.carregar_historico_ativo(ativo, periodo)


def obter_calls(ativo):
    return _PROVEDOR.obter_calls(ativo)


__all__ = [
    "calcular_preco_atual",
    "carregar_historico_ativo",
    "obter_calls",
    "salvar_dados_mock",
    "calcular_premio_vetor",
    "calcular_prob_acima_strike_monte_carlo",
    "calcular_prob_acima_strike_monte_carlo_batch",
    "calcular_prob_exercicio_risk_neutral",
    "calcular_prob_exercicio_risk_neutral_vetor",
    "calcular_probabilidade_empirica_batch",
    "gerar_grafico_payoff_covered_call",
    "preparar_calls_para_modelo",
]
