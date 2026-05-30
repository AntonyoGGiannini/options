import pandas as pd
import functions as fn

pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', None)

# ---------------------------------------------------------------------------
# Configuração — edite aqui
# ---------------------------------------------------------------------------

LISTA_ATIVOS = ['IBIT', 'AAPL', 'IVV', 'NVDA', 'SPY', 'META', 
                'AMZN', 'GOOGL', 'TSLA', 'MSFT', 'TFLO', 'AGG',
                'USFR', 'REMX', 'NU', 'TSM', 'GLD', 'AVEM', 
                'VPL', 'BBEU']  # ativos para analisar
TOP_N = 5                      # top N opções por papel

# Preço médio de aquisição por ativo (opcional).
# Usado apenas no gráfico de payoff da melhor opção geral.
# None = usar preço atual de mercado.
PRECO_MEDIO_AQUISICAO = None   # ex: {'IBIT': 55.00, 'AAPL': 180.00}

PROB_EXERC_MAX   = 0.15        # probabilidade máxima de exercício
TAXA_LIVRE_RISCO = 0.045       # taxa anual
DIVIDEND_YIELD   = 0.00        # dividend yield anual (único para todos; ajuste se necessário)

USAR_PROB_D2       = True      # probabilidade risk-neutral Black-Scholes d2
USAR_PROB_MC       = True      # probabilidade Monte Carlo
USAR_PROB_EMPIRICA = True      # probabilidade histórica empírica
PERIODO_HISTORICO  = "5y"      # janela de histórico para prob empírica

USAR_PREMIO = "bid"            # "bid", "ask", "lastPrice" ou "mid"
DIAS_ANO    = 365

MIN_DIAS = 7
MAX_DIAS = 20

TAMANHO_CONTRATO = 100
CUSTO_COMPRA     = 0.00
CUSTO_VENDA      = 0.00
CUSTO_EXERCICIO  = 0.00

# --- Modo offline -----------------------------------------------------------
MODO_OFFLINE = False   # True = lê arquivos mock locais (sem internet)
SALVAR_MOCK  = False   # True = salva arquivos mock ao rodar online
PASTA_MOCK   = "."
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Processamento multi-ativo
# ---------------------------------------------------------------------------

resultados = []

for ativo in LISTA_ATIVOS:
    print(f"\n>>> Processando {ativo}...")
    df_top = fn.processar_ativo(
        ativo=ativo,
        taxa_livre_risco=TAXA_LIVRE_RISCO,
        dividend_yield=DIVIDEND_YIELD,
        usar_premio=USAR_PREMIO,
        mu=0.00,
        n_simulacoes=50000,
        seed=42,
        batch_size=500,
        t_min=MIN_DIAS,
        t_max=MAX_DIAS,
        dias_ano=DIAS_ANO,
        usar_prob_d2=USAR_PROB_D2,
        usar_prob_mc=USAR_PROB_MC,
        usar_prob_empirica=USAR_PROB_EMPIRICA,
        periodo_historico=PERIODO_HISTORICO,
        min_amostras_empirica=30,
        prob_exerc_max=PROB_EXERC_MAX,
        custo_venda=CUSTO_VENDA,
        tamanho_contrato=TAMANHO_CONTRATO,
        top_n=TOP_N,
        modo_offline=MODO_OFFLINE,
        salvar_mock=SALVAR_MOCK,
        pasta_mock=PASTA_MOCK,
    )
    resultados.append(df_top)

df_final = pd.concat([r for r in resultados if not r.empty], ignore_index=True)

# ---------------------------------------------------------------------------
# Colunas do output
# ---------------------------------------------------------------------------

COLUNAS_OUTPUT = [
    "ativo",
    "ranking_ativo",
    "strike",
    "premio",
    "expiration",
    "dias_uteis_ate_vencimento",
    "prob_exercicio",
    "prob_empirica",
    "prob_exercicio_final",
    "retorno_anualizado_pct",
    "retorno_anualizado_liquido",
    "bid",
    "ask",
    "volume",
    "openInterest",
    "preco_atual_ativo",
    "score_venda",
]

# Mantém apenas colunas que existem (tolerante a ativos sem MC ou empírica)
colunas_presentes = [c for c in COLUNAS_OUTPUT if c in df_final.columns]
df_output = df_final[colunas_presentes].copy()

# ---------------------------------------------------------------------------
# Print e Excel
# ---------------------------------------------------------------------------

print("\n" + "=" * 80)
print(f"TOP {TOP_N} COVERED CALLS POR ATIVO")
print("=" * 80)
print(df_output.to_string(index=False))

df_output.to_excel("top_opcoes_covered_call.xlsx", index=False)
print(f"\nResultados salvos em: top_opcoes_covered_call.xlsx")

# ---------------------------------------------------------------------------
# Gráfico da melhor opção geral
# ---------------------------------------------------------------------------

if not df_final.empty:
    melhor = df_final.sort_values("score_venda", ascending=False).iloc[0]
    ativo_melhor = melhor["ativo"]

    preco_custo = None
    if isinstance(PRECO_MEDIO_AQUISICAO, dict):
        preco_custo = PRECO_MEDIO_AQUISICAO.get(ativo_melhor)
    elif isinstance(PRECO_MEDIO_AQUISICAO, (int, float)):
        preco_custo = PRECO_MEDIO_AQUISICAO

    prob_emp_str = f"{melhor['prob_empirica']:.2%}" if not pd.isna(melhor['prob_empirica']) else "N/A"
    print(
        f"\nMelhor opção geral: {ativo_melhor} | Strike {melhor['strike']} | "
        f"Venc. {melhor['expiration']} | Score {melhor['score_venda']:.4f} | "
        f"Prob. final {melhor['prob_exercicio_final']:.2%} "
        f"(d2={melhor['prob_exercicio']:.2%}, empírica={prob_emp_str})"
    )

    arquivo = fn.gerar_grafico_payoff_covered_call(
        preco_atual=melhor["preco_atual_ativo"],
        strike=melhor["strike"],
        premio=melhor["premio"],
        expiration=melhor["expiration"],
        preco_custo=preco_custo,
        arquivo_saida=f"payoff_{ativo_melhor}.png",
    )
    print(f"Gráfico de payoff salvo em: {arquivo}")
