"""Modelos quantitativos: probabilidades de exercício e payoff."""

from options.models.black_scholes import (
    calcular_prob_exercicio_risk_neutral,
    calcular_prob_exercicio_risk_neutral_vetor,
    preco_call_bs,
)
from options.models.empirical import calcular_probabilidade_empirica_batch
from options.models.greeks import calcular_greeks_call
from options.models.monte_carlo import (
    calcular_prob_acima_strike_monte_carlo,
    calcular_prob_acima_strike_monte_carlo_batch,
)
from options.models.payoff import gerar_grafico_payoff_covered_call
from options.models.pipeline import calcular_premio_vetor, preparar_calls_para_modelo
from options.models.volatility import volatilidade_realizada

__all__ = [
    "calcular_prob_exercicio_risk_neutral",
    "calcular_prob_exercicio_risk_neutral_vetor",
    "preco_call_bs",
    "calcular_prob_acima_strike_monte_carlo",
    "calcular_prob_acima_strike_monte_carlo_batch",
    "calcular_probabilidade_empirica_batch",
    "calcular_greeks_call",
    "volatilidade_realizada",
    "calcular_premio_vetor",
    "preparar_calls_para_modelo",
    "gerar_grafico_payoff_covered_call",
]
