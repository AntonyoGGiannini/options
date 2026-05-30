from scipy.stats import norm
import yfinance as yf
import pandas as pd
import numpy as np

def carregar_historico_ativo(ativo, periodo="5y"):
    ticker = yf.Ticker(ativo)
    hist = ticker.history(period=periodo, auto_adjust=True)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"].dropna()


def calcular_probabilidade_empirica_exercicio(precos, preco_atual, strike, dias_janela):
    """
    Calcula a frequência histórica em que o ativo teve retorno futuro
    maior ou igual ao retorno necessário para atingir o strike.
    """
    if dias_janela <= 0 or preco_atual <= 0 or strike <= 0:
        return np.nan
    if len(precos) < 2 * dias_janela:
        return np.nan
    retorno_necessario = (strike / preco_atual) - 1
    retorno_futuro = precos.shift(-dias_janela) / precos - 1
    retorno_futuro = retorno_futuro.dropna()
    if len(retorno_futuro) == 0:
        return np.nan
    return float((retorno_futuro >= retorno_necessario).mean())


def _calcular_emp_row(historico_precos, preco_atual, strike, dias_janela):
    prob = calcular_probabilidade_empirica_exercicio(
        historico_precos, preco_atual, strike, dias_janela
    )
    usou = not np.isnan(prob) if prob is not None else False
    return prob, usou


def calcular_preco_atual(ativo):
    ticker = yf.Ticker(ativo)
    hist = ticker.history(period="5d")

    if hist.empty:
        raise ValueError(f"Não foi possível obter preço atual para {ativo}")

    preco_atual = hist["Close"].dropna().iloc[-1]

    return float(preco_atual)

def calcular_dias_ate_vencimento(expiration):
    hoje = pd.Timestamp.today().normalize()
    venc = pd.to_datetime(expiration).normalize()

    dias = (venc - hoje).days

    return dias

def calcular_premio(row, usar_premio):
    bid = row.get("bid", np.nan)
    ask = row.get("ask", np.nan)
    last = row.get("lastPrice", np.nan)

    if usar_premio == "bid":
        return bid

    if usar_premio == "ask":
        return ask

    if usar_premio == "lastPrice":
        return last

    if usar_premio == "mid":
        if pd.notna(bid) and pd.notna(ask) and bid > 0 and ask > 0:
            return (bid + ask) / 2
        else:
            return last

    raise ValueError("USAR_PREMIO deve ser: bid, ask, lastPrice ou mid")


def calcular_prob_exercicio_risk_neutral(S0, K, T, r, q, iv):
    """
    probabilidade “risk-neutral” de uma ação terminar acima de um strike K no vencimento.

    Dado o preço atual da ação, o strike, o prazo, juros, dividendos e volatilidade implícita, qual a chance teórica de a call terminar dentro do dinheiro?    
    
    S0 = Preco Atual
    K = Strike
    T = Tempo até vencimento (em anos)
    r = Taxa livre de risco (anual)
    q = Dividend Yield (anual)
    iv = Volatilidade Implícita (anual)
    """

    if T <= 0 or iv <= 0 or K <= 0 or S0 <= 0:
        # CHECAGEM DE VALIDACAO
        # T deve ser positivo, iv deve ser positiva, strike e preco devem ser positivos
        return np.nan

    # No modelo Black-Scholes, o d2 é uma medida padronizada de quão provável é o preço da ação terminar acima do strike.
    d2 = (
        np.log(S0 / K)
        + (r - q - 0.5 * iv ** 2) * T
    ) / (iv * np.sqrt(T))

    # iv * np.sqrt(T) é o desvio padrão esperado do preço até o vencimento.

    # aqui transformamos o d2 em uma probabilidade.
    # norm.cdf() é a função de distribuição acumulada da normal padrão.
    # Qual a probabilidade associada a esse valor de d2 numa curva normal?
    prob = norm.cdf(d2)

    return prob

def calcular_prob_acima_strike_monte_carlo(
    S0,
    K,
    T,
    mu,
    sigma,
    q=0.0,
    n_simulacoes=10000,
    seed=None
):
    """
    Estima a chance do ativo terminar acima do strike no vencimento
    usando simulacao de Monte Carlo.

    S0 = preco atual
    K = strike
    T = tempo ate vencimento em anos
    mu = retorno esperado anualizado
    sigma = volatilidade anualizada
    q = dividend yield anual
    n_simulacoes = quantidade de caminhos simulados
    seed = semente opcional para resultado reproduzivel
    """

    if T <= 0 or sigma <= 0 or K <= 0 or S0 <= 0 or n_simulacoes <= 0:
        return np.nan

    rng = np.random.default_rng(seed)
    choques = rng.standard_normal(n_simulacoes)

    precos_vencimento = S0 * np.exp(
        (mu - q - 0.5 * sigma ** 2) * T
        + sigma * np.sqrt(T) * choques
    )

    prob = np.mean(precos_vencimento > K)

    return float(prob)

def calcular_prob_exercicio_risk_neutral_vetor(S0, K, T, r, q, iv):
    S0_arr = np.asarray(S0, dtype=float)
    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    iv_arr = np.asarray(iv, dtype=float)

    S0_arr, K_arr, T_arr, iv_arr = np.broadcast_arrays(
        S0_arr,
        K_arr,
        T_arr,
        iv_arr
    )

    probs = np.full(S0_arr.shape, np.nan, dtype=float)
    validos = (T_arr > 0) & (iv_arr > 0) & (K_arr > 0) & (S0_arr > 0)

    d2 = (
        np.log(S0_arr[validos] / K_arr[validos])
        + (r - q - 0.5 * iv_arr[validos] ** 2) * T_arr[validos]
    ) / (iv_arr[validos] * np.sqrt(T_arr[validos]))

    probs[validos] = norm.cdf(d2)

    return probs

def calcular_prob_acima_strike_monte_carlo_batch(
    S0,
    K,
    T,
    mu,
    sigma,
    q=0.0,
    n_simulacoes=10000,
    seed=None,
    batch_size=500
):
    """
    Versao vetorizada da simulacao de Monte Carlo.

    Use esta funcao para calcular muitos contratos de uma vez. Ela evita
    chamar o gerador aleatorio contrato por contrato e processa em blocos
    para controlar uso de memoria.
    """

    K_arr = np.asarray(K, dtype=float)
    T_arr = np.asarray(T, dtype=float)
    sigma_arr = np.asarray(sigma, dtype=float)

    S0_arr = np.asarray(S0, dtype=float)
    if S0_arr.ndim == 0:
        S0_arr = np.full(K_arr.shape, float(S0_arr))

    S0_arr, K_arr, T_arr, sigma_arr = np.broadcast_arrays(
        S0_arr,
        K_arr,
        T_arr,
        sigma_arr
    )

    probs = np.full(K_arr.shape, np.nan, dtype=float)

    if n_simulacoes <= 0 or batch_size <= 0:
        return probs

    validos = (T_arr > 0) & (sigma_arr > 0) & (K_arr > 0) & (S0_arr > 0)
    indices_validos = np.flatnonzero(validos.ravel())

    if len(indices_validos) == 0:
        return probs

    rng = np.random.default_rng(seed)
    probs_flat = probs.ravel()
    S0_flat = S0_arr.ravel()
    K_flat = K_arr.ravel()
    T_flat = T_arr.ravel()
    sigma_flat = sigma_arr.ravel()

    for inicio in range(0, len(indices_validos), batch_size):
        idx = indices_validos[inicio:inicio + batch_size]
        choques = rng.standard_normal((len(idx), n_simulacoes))

        log_precos_vencimento = (
            np.log(S0_flat[idx])[:, None]
            + ((mu - q - 0.5 * sigma_flat[idx] ** 2) * T_flat[idx])[:, None]
            + (sigma_flat[idx] * np.sqrt(T_flat[idx]))[:, None] * choques
        )

        probs_flat[idx] = np.mean(
            log_precos_vencimento > np.log(K_flat[idx])[:, None],
            axis=1
        )

    return probs

def calcular_premio_vetor(df, usar_premio):
    if usar_premio == "bid":
        return df["bid"]

    if usar_premio == "ask":
        return df["ask"]

    if usar_premio == "lastPrice":
        return df["lastPrice"]

    if usar_premio == "mid":
        mid_valido = (
            df["bid"].notna()
            & df["ask"].notna()
            & (df["bid"] > 0)
            & (df["ask"] > 0)
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
):
    """
    Calcula metricas de contrato uma unica vez por cadeia de opcoes.

    Esta fase deve rodar por ativo, antes de aplicar regras especificas
    de clientes.
    """

    if df_calls.empty:
        return df_calls.copy()

    df = df_calls.copy()

    df["preco_atual"] = preco_atual
    df["dias_vencimento"] = (
        pd.to_datetime(df["expiration"]).dt.normalize()
        - pd.Timestamp.today().normalize()
    ).dt.days
    df["T"] = df["dias_vencimento"] / dias_ano
    df["premio"] = calcular_premio_vetor(df, usar_premio)

    df["distancia_strike_pct"] = (df["strike"] / df["preco_atual"]) - 1
    df["retorno_premio_pct"] = df["premio"] / df["preco_atual"]
    df["retorno_anualizado_pct"] = df["retorno_premio_pct"] * (
        dias_ano / df["dias_vencimento"]
    )
    
    df["preco_atual"] = preco_atual
    df["rendimento"] = df["premio"] / preco_atual
    
    df = df[(df["dias_vencimento"] >= t_min) & (df["dias_vencimento"] <= t_max)].copy()

    if usar_prob_d2:
        df["prob_exercicio"] = calcular_prob_exercicio_risk_neutral_vetor(
            df["preco_atual"].to_numpy(),
            df["strike"].to_numpy(),
            df["T"].to_numpy(),
            taxa_livre_risco,
            dividend_yield,
            df["impliedVolatility"].to_numpy()
        )
    else:
        df["prob_exercicio"] = np.nan

    if usar_prob_mc:
        df["prob_exercicio_mc"] = calcular_prob_acima_strike_monte_carlo_batch(
            df["preco_atual"].to_numpy(),
            df["strike"].to_numpy(),
            df["T"].to_numpy(),
            mu=mu,
            sigma=df["impliedVolatility"].to_numpy(),
            q=dividend_yield,
            n_simulacoes=n_simulacoes,
            seed=seed,
            batch_size=batch_size
        )
    else:
        df["prob_exercicio_mc"] = np.nan

    df["retorno_necessario"] = (df["strike"] / df["preco_atual"]) - 1
    df["dias_uteis_ate_vencimento"] = df["dias_vencimento"]

    if usar_prob_empirica and historico_precos is not None and len(historico_precos) > 0:
        prob_emp_lista = []
        usa_emp_lista = []
        for _, row in df.iterrows():
            dias_janela = int(row["dias_vencimento"])
            p, usou = _calcular_emp_row(historico_precos, row["preco_atual"], row["strike"], dias_janela)
            prob_emp_lista.append(p)
            usa_emp_lista.append(usou)
        df["prob_empirica"] = prob_emp_lista
        df["usa_prob_empirica"] = usa_emp_lista
    else:
        df["prob_empirica"] = np.nan
        df["usa_prob_empirica"] = False

    # Probabilidade final conservadora: max(prob_d2, prob_empirica)
    prob_d2_series = df["prob_exercicio"] if usar_prob_d2 else pd.Series(np.nan, index=df.index)
    prob_emp_series = df["prob_empirica"]
    df["prob_exercicio_final"] = prob_d2_series.combine(prob_emp_series, lambda a, b: (
        max(x for x in [a, b] if pd.notna(x)) if any(pd.notna(x) for x in [a, b]) else np.nan
    ))

    return df

def obter_calls(ativo):
    ticker = yf.Ticker(ativo)
    expirations = ticker.options

    lista_calls = []

    for expiration in expirations:
        try:
            calls = ticker.option_chain(expiration).calls.copy()

            # FILTRO
            # Evitar opções com liquidez ruim, porque isso pode gerar:
            #   spread bid/ask muito aberto;
            #   dificuldade de vender perto do preço justo;
            #   dificuldade de recomprar/rolar;
            #   preço lastPrice enganoso;
            #   IV pouco confiável

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

    if lista_calls:
        df_calls = pd.concat(lista_calls, ignore_index=True)
    else:
        df_calls = pd.DataFrame()
    
    return df_calls
