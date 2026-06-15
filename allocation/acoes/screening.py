"""Screening fundamentalista e técnico de ações/ETFs.

Dados do yfinance .info: P/L, P/VP, ROE, dividend yield, crescimento.
Momentum (retorno 12-1m), força relativa vs. SPY.
Output: ranking de candidatos a compor carteira de covered calls.

TODO: implementar via allocation.data.ProvedorDados (histórico + .info)
"""
from __future__ import annotations
