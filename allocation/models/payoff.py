"""Gráfico de payoff ao vencimento de uma covered call."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def gerar_grafico_payoff_covered_call(
    preco_atual,
    strike,
    premio,
    expiration,
    preco_custo=None,
    arquivo_saida="payoff_covered_call.png",
    custo_exercicio_contrato=0.0,
    custo_venda_contrato=0.0,
    tamanho_contrato=100,
):
    """
    Gera gráfico de payoff ao vencimento de uma covered call.
    preco_custo: preço médio de aquisição; se None, usa preco_atual.
    custo_exercicio_contrato: custo de atribuição por contrato, aplicado por ação
        apenas quando a call é exercida (ST >= strike).
    custo_venda_contrato: custo de venda da call por contrato (sempre aplicado).
    """
    custo = preco_custo if preco_custo is not None else preco_atual
    custo_venda_acao = custo_venda_contrato / tamanho_contrato
    custo_exerc_acao = custo_exercicio_contrato / tamanho_contrato

    s_min = preco_atual * 0.5
    s_max = preco_atual * 1.5
    ST = np.linspace(s_min, s_max, 300)

    ganho_acao = ST - custo
    # custo de exercício incide só na região atribuída (ST >= strike)
    custo_exerc_aplicado = np.where(ST >= strike, custo_exerc_acao, 0.0)
    payoff_call_vendida = (
        -np.maximum(ST - strike, 0) + premio - custo_venda_acao - custo_exerc_aplicado
    )
    payoff_total = ganho_acao + payoff_call_vendida

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(ST, ganho_acao, color="#5B9BD5", linewidth=1.5, linestyle="--", label="Ação isolada")
    ax.plot(ST, payoff_total, color="#ED7D31", linewidth=2.5, label="Covered Call")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(
        preco_atual,
        color="#5B9BD5",
        linewidth=1.0,
        linestyle=":",
        alpha=0.8,
        label=f"Preço atual  ${preco_atual:.2f}",
    )
    ax.axvline(
        strike,
        color="#ED7D31",
        linewidth=1.0,
        linestyle=":",
        alpha=0.8,
        label=f"Strike  ${strike:.2f}",
    )

    if preco_custo is not None and abs(preco_custo - preco_atual) > 0.01:
        ax.axvline(
            preco_custo,
            color="#70AD47",
            linewidth=1.0,
            linestyle=":",
            alpha=0.8,
            label=f"Preço médio  ${preco_custo:.2f}",
        )

    ax.annotate(
        f"Prêmio recebido: ${premio:.2f}",
        xy=(s_min + (s_max - s_min) * 0.04, premio),
        fontsize=9,
        color="#ED7D31",
        va="bottom",
    )

    breakeven = custo - premio + custo_venda_acao
    if s_min < breakeven < s_max:
        ax.axvline(breakeven, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.annotate(
            f"Breakeven ${breakeven:.2f}",
            xy=(breakeven, -premio * 2),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
            color="gray",
        )

    ax.set_xlabel("Preço do ativo no vencimento (USD)")
    ax.set_ylabel("Lucro / Prejuízo por ação (USD)")
    ax.set_title(
        f"Payoff — Covered Call | Strike ${strike:.2f} | Venc. {expiration} | Prêmio ${premio:.2f}"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(arquivo_saida, dpi=150)
    plt.close(fig)

    return arquivo_saida
