"""Modelos quantitativos: probabilidades de exercício e payoff."""

from allocation.models.black_scholes import (
    calcular_prob_exercicio_risk_neutral,
    calcular_prob_exercicio_risk_neutral_vetor,
    preco_call_bs,
)
from allocation.models.empirical import calcular_probabilidade_empirica_batch
from allocation.models.greeks import calcular_greeks_call
from allocation.models.payoff import gerar_grafico_payoff_covered_call
from allocation.opcoes.pipeline import calcular_premio_vetor, preparar_calls_para_modelo
from allocation.models.volatility import volatilidade_realizada

__all__ = [
    "calcular_prob_exercicio_risk_neutral",
    "calcular_prob_exercicio_risk_neutral_vetor",
    "preco_call_bs",
    "calcular_probabilidade_empirica_batch",
    "calcular_greeks_call",
    "volatilidade_realizada",
    "calcular_premio_vetor",
    "preparar_calls_para_modelo",
    "gerar_grafico_payoff_covered_call",
]
