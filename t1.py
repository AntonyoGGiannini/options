import pandas as pd
import functions as fn

pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)

ATIVO = "IBIT"

PROB_EXERC_MAX = 0.80          # probabilidade máxima de exercício aceita pelo usuário
TAXA_LIVRE_RISCO = 0.045       # taxa anual
DIVIDEND_YIELD = 0.00          # dividend yield anual
#MULTIPLIER = 100               # padrão opções EUA

USAR_PREMIO = "bid"            # "bid", "ask", "lastPrice" ou "mid"
DIAS_ANO = 365                 # dias corridos; coerente com Black-Scholes e renda fixa
PERIODO_HISTORICO = "5y"       # janela de histórico para probabilidade empírica
MIN_AMOSTRAS_EMPIRICA = 30     # mínimo de amostras históricas para calcular prob empírica

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
historico = fn.obter_historico_precos(ATIVO, PERIODO_HISTORICO)

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
    t_max=MAX_DIAS,
    dias_ano=DIAS_ANO,
    historico_precos=historico,
    min_amostras_empirica=MIN_AMOSTRAS_EMPIRICA,
)

df_calls_ajustado = df_calls[
    [
        "expiration",
        "strike",
        "T",
        "dias_uteis_ate_vencimento",
        "bid",
        "ask",
        "lastPrice",
        "volume",
        "openInterest",
        "premio",
        "impliedVolatility",
        "retorno_necessario",
        "prob_d2",
        "prob_empirica",
        "usa_prob_empirica",
        "prob_exercicio_final",
        "prob_exercicio_mc",
    ]
].copy()

df_calls_ajustado["preco_atual"] = preco_atual
df_calls_ajustado["rendimento"] = df_calls_ajustado["premio"] / preco_atual
df_calls_ajustado["distancia_strike_pct"] = df_calls["distancia_strike_pct"]
df_calls_ajustado["retorno_anualizado_pct"] = df_calls["retorno_anualizado_pct"]

# Ranking para venda de call
df_venda = df_calls_ajustado[
    (df_calls_ajustado["distancia_strike_pct"] > 0) &              # apenas OTM
    (df_calls_ajustado["prob_exercicio_final"] <= PROB_EXERC_MAX) & # probabilidade final conservadora
    (df_calls_ajustado["retorno_anualizado_pct"] > 0)               # prêmio positivo
].copy()

# Score: retorno anualizado esperado ajustado pela probabilidade final de expirar sem valor
df_venda["score_venda"] = df_venda["retorno_anualizado_pct"] * (1 - df_venda["prob_exercicio_final"])
df_venda = df_venda.sort_values("score_venda", ascending=False)
df_venda["ranking"] = range(1, len(df_venda) + 1)

print(df_venda)
df_venda.to_excel("df_calls_ajustado.xlsx", index=False)

if not df_venda.empty:
    melhor = df_venda.iloc[0]
    print(
        f"\nMelhor call para vender: Strike {melhor['strike']} | "
        f"Venc. {melhor['expiration']} | "
        f"Score {melhor['score_venda']:.4f} | "
        f"Prob. final {melhor['prob_exercicio_final']:.2%} "
        f"(D2: {melhor['prob_d2']:.2%} | "
        f"Empírica: {melhor['prob_empirica']:.2%} | "
        f"Usa empírica: {melhor['usa_prob_empirica']})"
    )
