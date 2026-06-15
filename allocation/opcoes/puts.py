"""Análise e ranking de venda de puts (cash-secured / naked).

Estratégia espelho das covered calls: venda de put OTM com probabilidade
de exercício controlada. Combinada com opcoes/calls.py forma o Wheel.

TODO: implementar pipeline de puts reutilizando allocation.models.*
"""
from __future__ import annotations
