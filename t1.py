import pandas as pd
import functions as fn

pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)

ATIVO = "IBIT"

# Preço médio de aquisição da ação (opcional).
# Preencher se quiser que o gráfico de payoff reflita o custo real da posição.
# Se None, o gráfico usa o preço atual de mercado como referência.
PRECO_MEDIO_AQUISICAO = None   # ex: 55.00

PROB_EXERC_MAX = 0.80          # probabilidade máxima de exercício aceita pelo usuário
TAXA_LIVRE_RISCO = 0.045       # taxa anual
DIVIDEND_YIELD = 0.00          # dividend yield anual

USAR_PROB_D2       = True      # usar probabilidade risk-neutral Black-Scholes d2
USAR_PROB_MC       = True      # usar probabilidade Monte Carlo
USAR_PROB_EMPIRICA = True      # usar probabilidade histórica empírica
PERIODO_HISTORICO  = "5y"      # período de histórico para probabilidade empírica

USAR_PREMIO = "bid"            # "bid", "ask", "lastPrice" ou "mid"
DIAS_ANO = 365                 # dias corridos; coerente com Black-Scholes e renda fixa

#MIN_VOLUME = 100
#MIN_OPEN_INTEREST = 100
MIN_DIAS = 7
MAX_DIAS = 45

TAMANHO_CONTRATO = 100         # unidades por contrato (padrão EUA)
CUSTO_COMPRA = 0.00            # custo de compra por contrato (USD)
CUSTO_VENDA = 0.00             # custo de venda por contrato (USD)
CUSTO_EXERCICIO = 0.00         # custo de exercício por contrato (USD)

df_calls = fn.obter_calls(ATIVO)

preco_atual = fn.calcular_preco_atual(ATIVO)

historico = fn.carregar_historico_ativo(ATIVO, periodo=PERIODO_HISTORICO) if USAR_PROB_EMPIRICA else None

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
    usar_prob_d2=USAR_PROB_D2,
    usar_prob_mc=USAR_PROB_MC,
    usar_prob_empirica=USAR_PROB_EMPIRICA,
)

df_calls_ajustado = df_calls[
    [
        "expiration",
        "strike",
        "T",
        "bid",
        "ask",
        "lastPrice",
        "volume",
        "openInterest",
        "premio",
        "impliedVolatility",
        "prob_exercicio",
        "prob_exercicio_mc",
        "prob_empirica",
        "usa_prob_empirica",
        "prob_exercicio_final",
        "retorno_necessario",
        "dias_uteis_ate_vencimento",
    ]
].copy()

df_calls_ajustado["preco_atual"] = preco_atual
df_calls_ajustado["rendimento"] = df_calls_ajustado["premio"] / preco_atual
df_calls_ajustado["distancia_strike_pct"] = df_calls["distancia_strike_pct"]
df_calls_ajustado["retorno_anualizado_pct"] = df_calls["retorno_anualizado_pct"]

# Custos por ação (contrato = TAMANHO_CONTRATO ações)
custo_venda_por_acao = CUSTO_VENDA / TAMANHO_CONTRATO
custo_exercicio_por_acao = CUSTO_EXERCICIO / TAMANHO_CONTRATO

df_calls_ajustado["premio_liquido"] = df_calls_ajustado["premio"] - custo_venda_por_acao
df_calls_ajustado["rendimento_liquido"] = df_calls_ajustado["premio_liquido"] / preco_atual
df_calls_ajustado["retorno_anualizado_liquido"] = (
    df_calls_ajustado["rendimento_liquido"] / df_calls_ajustado["T"]
)

# Ranking para venda de call
df_venda = df_calls_ajustado[
    (df_calls_ajustado["distancia_strike_pct"] > 0) &                    # apenas OTM
    (df_calls_ajustado["prob_exercicio_final"] <= PROB_EXERC_MAX) &       # risco de exercício controlado
    (df_calls_ajustado["retorno_anualizado_pct"] > 0)                     # prêmio positivo
].copy()

# Score: retorno anualizado esperado ajustado pela probabilidade de expirar sem valor
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
        f"Prob. exercício final {melhor['prob_exercicio_final']:.2%} "
        f"(d2={melhor['prob_exercicio']:.2%}, empírica={melhor['prob_empirica']:.2%} se disponível)"
    )

    arquivo = fn.gerar_grafico_payoff_covered_call(
        preco_atual=preco_atual,
        strike=melhor["strike"],
        premio=melhor["premio"],
        expiration=melhor["expiration"],
        preco_custo=PRECO_MEDIO_AQUISICAO,
    )
    print(f"Gráfico de payoff salvo em: {arquivo}")
