import pandas as pd
import functions as fn

pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)

ATIVO = "IBIT"

#PROB_EXERC_MAX = 0.20          # probabilidade máxima de exercício
TAXA_LIVRE_RISCO = 0.045       # taxa anual
DIVIDEND_YIELD = 0.00          # dividend yield anual
#MULTIPLIER = 100               # padrão opções EUA

USAR_PREMIO = "bid"            # "bid", "ask", "lastPrice" ou "mid"

#MIN_VOLUME = 100
#MIN_OPEN_INTEREST = 100
MIN_DIAS = 7
MAX_DIAS = 45

#CUSTO_ABERTURA = 1.00          # custo por contrato
#SLIPPAGE_PREMIO = 0.02         # 2% do prêmio
#CUSTO_FIXO_EXERCICIO = 5.00
#CUSTO_VAR_EXERCICIO = 0.00     # percentual sobre notional em caso de exercício

df_calls = fn.obter_calls(ATIVO)

preco_atual = fn.calcular_preco_atual(ATIVO)

df_calls = fn.preparar_calls_para_modelo(
    df_calls=df_calls,
    preco_atual=preco_atual,
    taxa_livre_risco=TAXA_LIVRE_RISCO,
    dividend_yield=DIVIDEND_YIELD,
    usar_premio=USAR_PREMIO,
    mu=0.00, # depois quando tiver back-test pode testar usar retorno_historico_anualizado
    n_simulacoes=50000,
    seed=42,
    batch_size=500,
    t_min=MIN_DIAS,
    t_max=MAX_DIAS
)

df_calls_ajustado = df_calls[
    [
        "expiration",
        "strike",
        "T",
        "bid",
        "ask",
        "lastPrice",
        "premio",
        "impliedVolatility",
        "prob_exercicio",
        "prob_exercicio_mc",
    ]
].copy()

df_calls_ajustado["preco_atual"] = preco_atual
df_calls_ajustado["rendimento"] = df_calls_ajustado["premio"] / preco_atual

print(df_calls_ajustado)
df_calls_ajustado.to_excel("df_calls_ajustado.xlsx", index=False)

# Fase por cliente: aplicar regras de suitability e ranking em cima do
# catalogo de contratos ja calculado por ativo.

# df_selecao = df_calls[
#     (df_calls["dias_vencimento"] >= 15) &
#     (df_calls["dias_vencimento"] <= 60) &
#     (df_calls["distancia_strike_pct"] > 0) &
#     (df_calls["prob_exercicio"] <= 0.20) &
#     (df_calls["premio"] > 0)
# ].copy()

# df_selecao = df_selecao.sort_values(
#     by=["retorno_anualizado_pct", "prob_exercicio"],
#     ascending=[False, True]
# )

# print(df_selecao)
