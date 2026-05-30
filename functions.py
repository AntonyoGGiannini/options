from scipy.stats import norm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yfinance as yf
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Dados de mercado
# ---------------------------------------------------------------------------

def calcular_preco_atual(ativo):
    ticker = yf.Ticker(ativo)
    hist = ticker.history(period="5d")
    if hist.empty:
        raise ValueError(f"Não foi possível obter preço atual para {ativo}")
    return float(hist["Close"].dropna().iloc[-1])


def carregar_historico_ativo(ativo, periodo="5y"):
    ticker = yf.Ticker(ativo)
    hist = ticker.history(period=periodo, auto_adjust=True)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"].dropna()


def obter_calls(ativo):
    ticker = yf.Ticker(ativo)
    expirations = ticker.options

    lista_calls = []
    for expiration in expirations:
        try:
            calls = ticker.option_chain(expiration).calls.copy()
            calls["mid"] = (calls["bid"] + calls["ask"]) / 2
            calls["spread_pct"] = (calls["ask"] - calls["bid"]) / calls["mid"]
            calls = calls[
                (calls["volume"] >= 100) &
                (calls["openInterest"] >= 500) &
                (calls["spread_pct"] <= 0.15)
            ].copy()
            calls["ativo"] = ativo
            calls["expiration"] = expiration
            calls["type"] = "CALL"
            lista_calls.append(calls)
        except Exception as e:
            print(f"Erro no vencimento {expiration}: {e}")

    return pd.concat(lista_calls, ignore_index=True) if lista_calls else pd.DataFrame()


# ---------------------------------------------------------------------------
# Mock data (offline)
# ---------------------------------------------------------------------------

def salvar_dados_mock(ativo, df_calls, preco_atual, historico_precos, pasta="."):
    """
    Salva os dados obtidos via yfinance em arquivos locais para uso offline.

    Arquivos gerados:
      mock_{ativo}_calls.csv      — cadeia de opções
      mock_{ativo}_historico.csv  — série histórica de preços
      mock_{ativo}_info.json      — preco_atual e metadados
    """
    import os, json
    from datetime import datetime

    os.makedirs(pasta, exist_ok=True)
    prefixo = os.path.join(pasta, f"mock_{ativo}")

    df_calls.to_csv(f"{prefixo}_calls.csv", index=False)

    if historico_precos is not None and len(historico_precos) > 0:
        historico_precos.to_csv(f"{prefixo}_historico.csv", header=["Close"])
    else:
        pd.Series(dtype=float).to_csv(f"{prefixo}_historico.csv", header=["Close"])

    info = {
        "ativo": ativo,
        "preco_atual": float(preco_atual),
        "gerado_em": datetime.now().isoformat(),
    }
    with open(f"{prefixo}_info.json", "w") as f:
        json.dump(info, f, indent=2)

    print(f"Dados mock salvos em: {prefixo}_calls.csv | _historico.csv | _info.json")


def carregar_dados_mock(ativo, pasta="."):
    """
    Carrega dados salvos localmente, substituindo as chamadas ao yfinance.

    Retorna: (df_calls, preco_atual, historico_precos)
    """
    import os, json

    prefixo = os.path.join(pasta, f"mock_{ativo}")
    arquivo_calls    = f"{prefixo}_calls.csv"
    arquivo_historico = f"{prefixo}_historico.csv"
    arquivo_info     = f"{prefixo}_info.json"

    for arq in [arquivo_calls, arquivo_historico, arquivo_info]:
        if not os.path.exists(arq):
            raise FileNotFoundError(
                f"Arquivo mock não encontrado: {arq}\n"
                f"Execute com MODO_OFFLINE=False e SALVAR_MOCK=True para gerar os arquivos."
            )

    df_calls = pd.read_csv(arquivo_calls)

    historico_df = pd.read_csv(arquivo_historico, index_col=0, parse_dates=True,
                               date_format="mixed")
    historico_precos = historico_df["Close"].dropna()

    with open(arquivo_info) as f:
        info = json.load(f)
    preco_atual = float(info["preco_atual"])

    print(
        f"Dados mock carregados: {ativo} | preco_atual={preco_atual:.2f} | "
        f"calls={len(df_calls)} | historico={len(historico_precos)} pregões | "
        f"gerado em {info.get('gerado_em', '?')}"
    )
    return df_calls, preco_atual, historico_precos


# ---------------------------------------------------------------------------
# Probabilidades
# ---------------------------------------------------------------------------

def calcular_prob_exercicio_risk_neutral(S0, K, T, r, q, iv):
    """Probabilidade risk-neutral (Black-Scholes d2) de a call terminar ITM."""
    if T <= 0 or iv <= 0 or K <= 0 or S0 <= 0:
        return np.nan
    d2 = (np.log(S0 / K) + (r - q - 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    return float(norm.cdf(d2))


def calcular_prob_exercicio_risk_neutral_vetor(S0, K, T, r, q, iv):
    """Versão vetorizada de calcular_prob_exercicio_risk_neutral."""
    S0_arr = np.asarray(S0, dtype=float)
    K_arr  = np.asarray(K,  dtype=float)
    T_arr  = np.asarray(T,  dtype=float)
    iv_arr = np.asarray(iv, dtype=float)
    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, iv_arr)

    probs   = np.full(S0_arr.shape, np.nan, dtype=float)
    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    d2 = (
        np.log(S0_arr[validos] / K_arr[validos])
        + (r - q - 0.5 * iv_arr[validos] ** 2) * T_arr[validos]
    ) / (iv_arr[validos] * np.sqrt(T_arr[validos]))
    probs[validos] = norm.cdf(d2)
    return probs


def calcular_prob_acima_strike_monte_carlo(S0, K, T, mu, sigma, q=0.0,
                                           n_simulacoes=10000, seed=None):
    """Estimativa Monte Carlo da probabilidade de exercício."""
    if T <= 0 or sigma <= 0 or K <= 0 or S0 <= 0 or n_simulacoes <= 0:
        return np.nan
    rng = np.random.default_rng(seed)
    choques = rng.standard_normal(n_simulacoes)
    precos_vencimento = S0 * np.exp(
        (mu - q - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * choques
    )
    return float(np.mean(precos_vencimento > K))


def calcular_prob_acima_strike_monte_carlo_batch(S0, K, T, mu, sigma, q=0.0,
                                                 n_simulacoes=10000, seed=None,
                                                 batch_size=500):
    """Versão vetorizada do Monte Carlo, processa em batches para economizar memória."""
    K_arr     = np.asarray(K,     dtype=float)
    T_arr     = np.asarray(T,     dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)
    S0_arr    = np.asarray(S0,    dtype=float)
    if S0_arr.ndim == 0:
        S0_arr = np.full(K_arr.shape, float(S0_arr))
    S0_arr, K_arr, T_arr, sigma_arr = np.broadcast_arrays(S0_arr, K_arr, T_arr, sigma_arr)

    probs = np.full(K_arr.shape, np.nan, dtype=float)
    if n_simulacoes <= 0 or batch_size <= 0:
        return probs

    validos = (T_arr > 0) & (sigma_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    indices_validos = np.flatnonzero(validos.ravel())
    if len(indices_validos) == 0:
        return probs

    rng        = np.random.default_rng(seed)
    probs_flat = probs.ravel()
    S0_flat    = S0_arr.ravel()
    K_flat     = K_arr.ravel()
    T_flat     = T_arr.ravel()
    sigma_flat = sigma_arr.ravel()

    for inicio in range(0, len(indices_validos), batch_size):
        idx = indices_validos[inicio:inicio + batch_size]
        choques = rng.standard_normal((len(idx), n_simulacoes))
        log_precos = (
            np.log(S0_flat[idx])[:, None]
            + ((mu - q - 0.5 * sigma_flat[idx] ** 2) * T_flat[idx])[:, None]
            + (sigma_flat[idx] * np.sqrt(T_flat[idx]))[:, None] * choques
        )
        probs_flat[idx] = np.mean(log_precos > np.log(K_flat[idx])[:, None], axis=1)

    return probs


def calcular_probabilidade_empirica_batch(precos, preco_atual_arr, strike_arr,
                                          dias_janela_arr, min_amostras=30):
    """
    Calcula historicamente quantas vezes o ativo superou o strike em janelas
    equivalentes ao prazo de cada opção. Agrupa por janela para eficiência.

    Retorna: (probs array, usa_empirica bool array)
    """
    n            = len(strike_arr)
    probs        = np.full(n, np.nan, dtype=float)
    usa_empirica = np.zeros(n, dtype=bool)

    for janela in np.unique(dias_janela_arr):
        mask = dias_janela_arr == janela
        retornos_futuros = precos.shift(-int(janela)) / precos - 1
        retornos_validos = retornos_futuros.dropna()
        if len(retornos_validos) < min_amostras:
            continue
        for i in np.where(mask)[0]:
            ret_nec      = (strike_arr[i] / preco_atual_arr[i]) - 1
            probs[i]     = float((retornos_validos >= ret_nec).mean())
            usa_empirica[i] = True

    return probs, usa_empirica


# ---------------------------------------------------------------------------
# Preparação do modelo
# ---------------------------------------------------------------------------

def calcular_premio_vetor(df, usar_premio):
    if usar_premio == "bid":
        return df["bid"]
    if usar_premio == "ask":
        return df["ask"]
    if usar_premio == "lastPrice":
        return df["lastPrice"]
    if usar_premio == "mid":
        mid_valido = (
            df["bid"].notna() & df["ask"].notna()
            & (df["bid"] > 0) & (df["ask"] > 0)
        )
        return ((df["bid"] + df["ask"]) / 2).where(mid_valido, df["lastPrice"])
    raise ValueError("USAR_PREMIO deve ser: bid, ask, lastPrice ou mid")


def preparar_calls_para_modelo(
    df_calls,
    preco_atual,
    taxa_livre_risco,
    dividend_yield,
    usar_premio,
    mu=0.0,
    n_simulacoes=10000,
    seed=None,
    batch_size=500,
    t_min=0,
    t_max=365,
    dias_ano=365,
    historico_precos=None,
    usar_prob_d2=True,
    usar_prob_mc=True,
    usar_prob_empirica=True,
    min_amostras_empirica=30,
):
    """
    Calcula métricas de contrato por cadeia de opções.
    Flags usar_prob_d2 / usar_prob_mc / usar_prob_empirica permitem ligar/desligar
    cada modelo independentemente.
    prob_exercicio_final = max(prob_exercicio, prob_empirica) — abordagem conservadora.
    """
    if df_calls.empty:
        return df_calls.copy()

    df = df_calls.copy()

    df["preco_atual"] = preco_atual
    df["dias_vencimento"] = (
        pd.to_datetime(df["expiration"]).dt.normalize()
        - pd.Timestamp.today().normalize()
    ).dt.days

    hoje = pd.Timestamp.today().normalize().date()
    df["dias_uteis_ate_vencimento"] = df["expiration"].apply(
        lambda x: int(np.busday_count(hoje, pd.Timestamp(x).date()))
    )

    df["T"] = df["dias_vencimento"] / dias_ano
    df["premio"] = calcular_premio_vetor(df, usar_premio)

    df["distancia_strike_pct"] = (df["strike"] / df["preco_atual"]) - 1
    df["retorno_necessario"]   = df["distancia_strike_pct"]
    df["retorno_premio_pct"]   = df["premio"] / df["preco_atual"]
    df["retorno_anualizado_pct"] = df["retorno_premio_pct"] * (dias_ano / df["dias_vencimento"])
    df["rendimento"] = df["premio"] / preco_atual

    df = df[(df["dias_vencimento"] >= t_min) & (df["dias_vencimento"] <= t_max)].copy()

    # --- prob_exercicio (d2 / risk-neutral) ---
    if usar_prob_d2:
        df["prob_exercicio"] = calcular_prob_exercicio_risk_neutral_vetor(
            df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
            df["T"].to_numpy(), taxa_livre_risco, dividend_yield,
            df["impliedVolatility"].to_numpy()
        )
    else:
        df["prob_exercicio"] = np.nan

    # --- prob_exercicio_mc (Monte Carlo) ---
    if usar_prob_mc:
        df["prob_exercicio_mc"] = calcular_prob_acima_strike_monte_carlo_batch(
            df["preco_atual"].to_numpy(), df["strike"].to_numpy(),
            df["T"].to_numpy(), mu=mu,
            sigma=df["impliedVolatility"].to_numpy(),
            q=dividend_yield, n_simulacoes=n_simulacoes,
            seed=seed, batch_size=batch_size
        )
    else:
        df["prob_exercicio_mc"] = np.nan

    # --- prob_empirica (histórico) ---
    if usar_prob_empirica and historico_precos is not None and len(historico_precos) > 0:
        probs_emp, usa_emp = calcular_probabilidade_empirica_batch(
            historico_precos,
            df["preco_atual"].to_numpy(),
            df["strike"].to_numpy(),
            df["dias_uteis_ate_vencimento"].to_numpy(),
            min_amostras=min_amostras_empirica,
        )
        df["prob_empirica"]     = probs_emp
        df["usa_prob_empirica"] = usa_emp
    else:
        df["prob_empirica"]     = np.nan
        df["usa_prob_empirica"] = False

    # --- prob_exercicio_final = max(d2, empirica) ---
    df["prob_exercicio_final"] = df["prob_exercicio"]
    mascara = df["usa_prob_empirica"] & df["prob_empirica"].notna()
    df.loc[mascara, "prob_exercicio_final"] = np.maximum(
        df.loc[mascara, "prob_exercicio"],
        df.loc[mascara, "prob_empirica"],
    )

    return df


# ---------------------------------------------------------------------------
# Multi-ativo
# ---------------------------------------------------------------------------

def processar_ativo(
    ativo,
    taxa_livre_risco,
    dividend_yield,
    usar_premio,
    mu,
    n_simulacoes,
    seed,
    batch_size,
    t_min,
    t_max,
    dias_ano,
    usar_prob_d2,
    usar_prob_mc,
    usar_prob_empirica,
    periodo_historico,
    min_amostras_empirica,
    prob_exerc_max,
    custo_venda,
    tamanho_contrato,
    top_n=3,
    modo_offline=False,
    salvar_mock=False,
    pasta_mock=".",
):
    """
    Processa um único ativo: obtém calls, calcula probabilidades,
    aplica filtros e retorna as top_n opções ranqueadas por score.
    Retorna DataFrame vazio com aviso em caso de erro.
    """
    try:
        if modo_offline:
            df_calls, preco_atual, historico = carregar_dados_mock(ativo, pasta_mock)
            if not usar_prob_empirica:
                historico = None
        else:
            df_calls   = obter_calls(ativo)
            preco_atual = calcular_preco_atual(ativo)
            historico  = carregar_historico_ativo(ativo, periodo=periodo_historico) if usar_prob_empirica else None
            if salvar_mock:
                salvar_dados_mock(ativo, df_calls, preco_atual, historico, pasta_mock)

        if df_calls.empty:
            print(f"[{ativo}] Nenhuma opção disponível após filtros de liquidez.")
            return pd.DataFrame()

        df = preparar_calls_para_modelo(
            df_calls=df_calls,
            preco_atual=preco_atual,
            taxa_livre_risco=taxa_livre_risco,
            dividend_yield=dividend_yield,
            usar_premio=usar_premio,
            mu=mu,
            n_simulacoes=n_simulacoes,
            seed=seed,
            batch_size=batch_size,
            t_min=t_min,
            t_max=t_max,
            dias_ano=dias_ano,
            historico_precos=historico,
            usar_prob_d2=usar_prob_d2,
            usar_prob_mc=usar_prob_mc,
            usar_prob_empirica=usar_prob_empirica,
            min_amostras_empirica=min_amostras_empirica,
        )

        custo_venda_por_acao = custo_venda / tamanho_contrato
        df["premio_liquido"]           = df["premio"] - custo_venda_por_acao
        df["rendimento_liquido"]       = df["premio_liquido"] / df["preco_atual"]
        df["retorno_anualizado_liquido"] = df["rendimento_liquido"] / df["T"]

        df_filtrado = df[
            (df["distancia_strike_pct"] > 0) &
            (df["prob_exercicio_final"] <= prob_exerc_max) &
            (df["retorno_anualizado_pct"] > 0)
        ].copy()

        if df_filtrado.empty:
            print(f"[{ativo}] Nenhuma opção passou nos filtros (prob/prazo/retorno).")
            return pd.DataFrame()

        df_filtrado["score_venda"] = (
            df_filtrado["retorno_anualizado_pct"] * (1 - df_filtrado["prob_exercicio_final"])
        )
        df_filtrado = df_filtrado.sort_values("score_venda", ascending=False)
        df_filtrado["ranking_ativo"] = range(1, len(df_filtrado) + 1)
        df_filtrado["ativo"] = ativo
        df_filtrado["preco_atual_ativo"] = preco_atual

        return df_filtrado.head(top_n)

    except Exception as e:
        print(f"[{ativo}] Erro ao processar: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Gráfico de payoff
# ---------------------------------------------------------------------------

def gerar_grafico_payoff_covered_call(
    preco_atual,
    strike,
    premio,
    expiration,
    preco_custo=None,
    arquivo_saida="payoff_covered_call.png",
):
    """
    Gera gráfico de payoff ao vencimento de uma covered call.
    preco_custo: preço médio de aquisição; se None, usa preco_atual.
    """
    custo = preco_custo if preco_custo is not None else preco_atual

    s_min = preco_atual * 0.5
    s_max = preco_atual * 1.5
    ST    = np.linspace(s_min, s_max, 300)

    ganho_acao        = ST - custo
    payoff_call_vendida = -np.maximum(ST - strike, 0) + premio
    payoff_total      = ganho_acao + payoff_call_vendida

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(ST, ganho_acao,    color="#5B9BD5", linewidth=1.5, linestyle="--", label="Ação isolada")
    ax.plot(ST, payoff_total,  color="#ED7D31", linewidth=2.5, label="Covered Call")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(preco_atual, color="#5B9BD5", linewidth=1.0, linestyle=":",
               alpha=0.8, label=f"Preço atual  ${preco_atual:.2f}")
    ax.axvline(strike, color="#ED7D31", linewidth=1.0, linestyle=":",
               alpha=0.8, label=f"Strike  ${strike:.2f}")

    if preco_custo is not None and abs(preco_custo - preco_atual) > 0.01:
        ax.axvline(preco_custo, color="#70AD47", linewidth=1.0, linestyle=":",
                   alpha=0.8, label=f"Preço médio  ${preco_custo:.2f}")

    ax.annotate(
        f"Prêmio recebido: ${premio:.2f}",
        xy=(s_min + (s_max - s_min) * 0.04, premio),
        fontsize=9, color="#ED7D31", va="bottom",
    )

    breakeven = custo - premio
    if s_min < breakeven < s_max:
        ax.axvline(breakeven, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)
        ax.annotate(
            f"Breakeven ${breakeven:.2f}",
            xy=(breakeven, -premio * 2),
            xytext=(4, 4), textcoords="offset points",
            fontsize=8, color="gray",
        )

    ax.set_xlabel("Preço do ativo no vencimento (USD)")
    ax.set_ylabel("Lucro / Prejuízo por ação (USD)")
    ax.set_title(
        f"Payoff — Covered Call | Strike ${strike:.2f} | "
        f"Venc. {expiration} | Prêmio ${premio:.2f}"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(arquivo_saida, dpi=150)
    plt.close(fig)

    return arquivo_saida
