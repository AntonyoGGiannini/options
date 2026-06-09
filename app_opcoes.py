"""Interface Streamlit para o módulo de opções (covered calls).

Expõe o screener, a matriz completa de candidatas, o gráfico de payoff e o
backtest — tudo reaproveitando a engine existente (Config + runner + report),
sem reimplementar nenhuma lógica de negócio.

Uso:
    streamlit run app_opcoes.py

Dica: comece em modo offline (dados de base_mock/) para explorar sem internet.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from allocation.config import Config
from allocation.models.payoff import gerar_grafico_payoff_covered_call
from allocation.report import montar_matriz_output, montar_output
from allocation.runner import construir_provedor, executar, executar_backtest

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Allocation · Opções",
    page_icon="📈",
    layout="wide",
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def tickers_mock(pasta: str) -> list[str]:
    """Lista os tickers disponíveis numa pasta de mock (mock_<TICKER>_calls.csv)."""
    p = ROOT / pasta
    if not p.exists():
        return []
    return sorted(f.name[len("mock_"):-len("_calls.csv")] for f in p.glob("mock_*_calls.csv"))


def montar_config(**kwargs) -> Config:
    """Cria a Config a partir dos widgets, repassando erros de validação."""
    return Config(**kwargs)


@st.cache_data(show_spinner=False)
def rodar_screener(config_kwargs: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Executa o screener e devolve (top_ranqueado, matriz_completa).

    Recebe um dict (hashável) em vez da Config para o cache funcionar.
    """
    config = Config(**config_kwargs)
    provedor = construir_provedor(config)
    matriz: list[pd.DataFrame] = []
    df_top = executar(config, provedor, matriz_out=matriz)
    df_matriz = (
        montar_matriz_output(pd.concat(matriz, ignore_index=True))
        if matriz
        else pd.DataFrame()
    )
    df_top = montar_output(df_top) if not df_top.empty else pd.DataFrame()
    return df_top, df_matriz


@st.cache_data(show_spinner=False)
def rodar_backtest(config_kwargs: dict, distancia: float, dias: int, janela_vol: int) -> pd.DataFrame:
    config = Config(**config_kwargs)
    provedor = construir_provedor(config)
    return executar_backtest(
        config,
        distancia_strike_pct=distancia,
        dias_vencimento=dias,
        janela_vol=janela_vol,
        provedor=provedor,
    )


# Configuração de colunas para exibição (percentuais e moeda).
def _column_config() -> dict:
    pct = lambda label: st.column_config.NumberColumn(label, format="percent")  # noqa: E731
    money = lambda label: st.column_config.NumberColumn(label, format="$%.2f")  # noqa: E731
    num = lambda label, f="%.4f": st.column_config.NumberColumn(label, format=f)  # noqa: E731
    return {
        "prob_exercicio": pct("prob d2"),
        "prob_empirica": pct("prob empírica"),
        "prob_exercicio_final": pct("prob final"),
        "retorno_anualizado_pct": pct("ret. anual"),
        "retorno_anualizado_liquido": pct("ret. anual líq."),
        "retorno_se_exercido_anualizado": pct("ret. se exerc. (a.a.)"),
        "downside_protection": pct("proteção downside"),
        "retorno_sobre_custo": pct("ret. s/ custo"),
        "premio": money("prêmio"),
        "strike": money("strike"),
        "bid": money("bid"),
        "ask": money("ask"),
        "lucro_se_exercido": money("lucro se exerc."),
        "preco_atual_ativo": money("preço atual"),
        "capital_por_contrato": money("capital/contrato"),
        "custo_exercicio_contrato": money("custo exerc."),
        "score_venda": num("score", "%.4f"),
        "delta": num("delta", "%.3f"),
        "theta": num("theta", "%.3f"),
        "vega": num("vega", "%.3f"),
        "spread_pct": pct("spread"),
    }


# --------------------------------------------------------------------------
# Sidebar — parâmetros (montam a Config)
# --------------------------------------------------------------------------
st.sidebar.title("⚙️ Parâmetros")

modo = st.sidebar.radio(
    "Fonte de dados",
    ["Offline (mock)", "Online (yfinance)"],
    help="Offline usa os CSVs de base_mock/. Online baixa da internet via yfinance.",
)
offline = modo.startswith("Offline")

pasta_mock = "base_mock"
if offline:
    disponiveis = tickers_mock(pasta_mock)
    ativos = st.sidebar.multiselect(
        "Ativos",
        options=disponiveis,
        default=[t for t in ["IBIT", "AAPL", "NVDA"] if t in disponiveis] or disponiveis[:3],
    )
else:
    texto = st.sidebar.text_input("Ativos (separados por vírgula)", value="AAPL,MSFT,NVDA")
    ativos = [a.strip().upper() for a in texto.split(",") if a.strip()]

top_n = st.sidebar.number_input("Top N por ativo", min_value=1, max_value=50, value=5)

with st.sidebar.expander("Risco & mercado", expanded=True):
    prob_exerc_max = st.slider("Prob. máx. de exercício", 0.0, 1.0, 0.15, 0.01)
    taxa_livre_risco = st.number_input("Taxa livre de risco", 0.0, 0.5, 0.045, 0.005, format="%.3f")
    dividend_yield = st.number_input("Dividend yield", 0.0, 0.5, 0.0, 0.005, format="%.3f")

with st.sidebar.expander("Prazo & strike"):
    min_dias = st.number_input("Mín. dias até vencimento", 0, 365, 7)
    max_dias = st.number_input("Máx. dias até vencimento", 0, 365, 20)
    min_distancia_strike_pct = st.slider(
        "Distância mín. do strike", -0.20, 0.50, 0.0, 0.01,
        help="0,0 = ATM+; negativo permite ITM (ex.: -0,05 = até 5% ITM).",
    )
    usar_premio = st.selectbox("Prêmio de referência", ["bid", "mid", "ask", "lastPrice"], index=0)

with st.sidebar.expander("Liquidez"):
    liquidez_volume_min = st.number_input("Volume mín.", 0, 100000, 100)
    liquidez_open_interest_min = st.number_input("Open interest mín.", 0, 100000, 500)
    liquidez_spread_max = st.slider("Spread máx.", 0.0, 1.0, 0.15, 0.01)

with st.sidebar.expander("Custos (US$ por ação / por contrato)"):
    custo_venda = st.number_input("Custo de venda (por ação)", 0.0, 10.0, 0.0, 0.01)
    custo_compra = st.number_input("Custo de compra (buy-write, por ação)", 0.0, 10.0, 0.0, 0.01)
    custo_exercicio_pct = st.number_input("Custo exercício (% do strike)", 0.0, 0.05, 0.0025, 0.0005, format="%.4f")
    custo_exercicio_min = st.number_input("Custo exercício mín. (por contrato)", 0.0, 100.0, 10.0, 1.0)
    custo_exercicio = st.number_input("Taxa fixa de exercício (por contrato)", 0.0, 100.0, 0.0, 1.0)

with st.sidebar.expander("Modelos & score"):
    usar_prob_d2 = st.checkbox("Probabilidade d2 (Black-Scholes)", value=True)
    usar_prob_empirica = st.checkbox("Probabilidade empírica (histórica)", value=True)
    periodo_historico = st.selectbox("Período histórico", ["1y", "2y", "5y", "10y", "max"], index=2)
    min_amostras_empirica = st.number_input("Mín. amostras (empírica)", 1, 500, 30)
    peso_theta = st.number_input("Peso theta no score", 0.0, 10.0, 0.0, 0.1)
    peso_vega = st.number_input("Peso vega no score", 0.0, 10.0, 0.0, 0.1)

usar_pma = st.sidebar.checkbox("Tenho posição (preço médio de aquisição)")
preco_medio_aquisicao = None
if usar_pma and ativos:
    pma_dict = {}
    with st.sidebar.expander("Preço médio por ativo", expanded=True):
        for a in ativos:
            v = st.number_input(f"PMA {a}", 0.0, 100000.0, 0.0, 0.5, key=f"pma_{a}")
            if v > 0:
                pma_dict[a] = v
    preco_medio_aquisicao = pma_dict or None


def kwargs_config() -> dict:
    return dict(
        lista_ativos=ativos,
        top_n=int(top_n),
        preco_medio_aquisicao=preco_medio_aquisicao,
        prob_exerc_max=float(prob_exerc_max),
        taxa_livre_risco=float(taxa_livre_risco),
        dividend_yield=float(dividend_yield),
        usar_prob_d2=usar_prob_d2,
        usar_prob_empirica=usar_prob_empirica,
        periodo_historico=periodo_historico,
        min_amostras_empirica=int(min_amostras_empirica),
        usar_premio=usar_premio,
        min_dias=int(min_dias),
        max_dias=int(max_dias),
        min_distancia_strike_pct=float(min_distancia_strike_pct),
        liquidez_volume_min=int(liquidez_volume_min),
        liquidez_open_interest_min=int(liquidez_open_interest_min),
        liquidez_spread_max=float(liquidez_spread_max),
        custo_venda=float(custo_venda),
        custo_compra=float(custo_compra),
        custo_exercicio_pct=float(custo_exercicio_pct),
        custo_exercicio_min=float(custo_exercicio_min),
        custo_exercicio=float(custo_exercicio),
        peso_theta=float(peso_theta),
        peso_vega=float(peso_vega),
        modo_offline=offline,
        pasta_mock=pasta_mock,
        usar_cache=True,
    )


# --------------------------------------------------------------------------
# Corpo principal
# --------------------------------------------------------------------------
st.title("📈 Módulo de Opções — Covered Calls")
st.caption(
    "Screening, ranking, payoff e backtest de covered calls. "
    f"Fonte: **{'offline (mock)' if offline else 'online (yfinance)'}** · "
    f"{len(ativos)} ativo(s) selecionado(s)."
)

rodar = st.button("▶️ Rodar análise", type="primary", use_container_width=True)

if rodar:
    if not ativos:
        st.warning("Selecione ao menos um ativo na barra lateral.")
        st.stop()
    try:
        cfg_kwargs = kwargs_config()
        Config(**cfg_kwargs)  # valida cedo (mensagem clara em caso de erro)
    except (ValueError, FileNotFoundError) as exc:
        st.error(f"Configuração inválida: {exc}")
        st.stop()
    with st.spinner("Processando cadeias de opções..."):
        try:
            df_top, df_matriz = rodar_screener(cfg_kwargs)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Erro ao processar: {exc}")
            st.stop()
    st.session_state["df_top"] = df_top
    st.session_state["df_matriz"] = df_matriz
    st.session_state["cfg_kwargs"] = cfg_kwargs

tab_top, tab_matriz, tab_payoff, tab_bt = st.tabs(
    ["🏆 Ranking", "🧮 Matriz completa", "📐 Payoff", "🔁 Backtest"]
)

# --- Ranking ---
with tab_top:
    df_top = st.session_state.get("df_top")
    if df_top is None:
        st.info("Ajuste os parâmetros na barra lateral e clique em **Rodar análise**.")
    elif df_top.empty:
        st.warning("Nenhuma opção passou nos filtros. Afrouxe prob. máx., liquidez ou distância de strike.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Opções no ranking", len(df_top))
        c2.metric("Ativos com candidatas", df_top["ativo"].nunique() if "ativo" in df_top else 0)
        if "score_venda" in df_top:
            c3.metric("Melhor score", f"{df_top['score_venda'].max():.4f}")
        st.dataframe(
            df_top, use_container_width=True, hide_index=True, column_config=_column_config()
        )
        st.download_button(
            "⬇️ Baixar ranking (CSV)",
            df_top.to_csv(index=False).encode("utf-8"),
            file_name="top_covered_calls.csv",
            mime="text/csv",
        )

# --- Matriz completa ---
with tab_matriz:
    df_matriz = st.session_state.get("df_matriz")
    if df_matriz is None:
        st.info("Rode a análise para ver todas as candidatas, com o motivo de rejeição.")
    elif df_matriz.empty:
        st.warning("Sem candidatas para exibir.")
    else:
        status_opcoes = sorted(df_matriz["status"].dropna().unique()) if "status" in df_matriz else []
        sel = st.multiselect("Filtrar por status", status_opcoes, default=status_opcoes)
        df_show = df_matriz[df_matriz["status"].isin(sel)] if sel else df_matriz
        st.caption(f"{len(df_show)} de {len(df_matriz)} candidatas")
        st.dataframe(
            df_show, use_container_width=True, hide_index=True, column_config=_column_config()
        )
        st.download_button(
            "⬇️ Baixar matriz (CSV)",
            df_matriz.to_csv(index=False).encode("utf-8"),
            file_name="matriz_opcoes.csv",
            mime="text/csv",
        )

# --- Payoff ---
with tab_payoff:
    df_top = st.session_state.get("df_top")
    cfg_kwargs = st.session_state.get("cfg_kwargs", {})
    if df_top is None or df_top.empty:
        st.info("Rode a análise para visualizar o payoff de uma opção ranqueada.")
    else:
        rotulos = [
            f"{r.get('ativo', '?')} · strike {r['strike']:.2f} · venc {r.get('expiration', '?')}"
            for _, r in df_top.iterrows()
        ]
        idx = st.selectbox("Opção", range(len(rotulos)), format_func=lambda i: rotulos[i])
        linha = df_top.iloc[idx]
        pma = None
        if isinstance(preco_medio_aquisicao, dict):
            pma = preco_medio_aquisicao.get(linha.get("ativo"))
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                destino = tmp.name
            gerar_grafico_payoff_covered_call(
                preco_atual=float(linha.get("preco_atual_ativo")),
                strike=float(linha["strike"]),
                premio=float(linha["premio"]),
                expiration=linha.get("expiration"),
                preco_custo=pma,
                arquivo_saida=destino,
                custo_exercicio_contrato=float(linha.get("custo_exercicio_contrato", 0.0) or 0.0),
                custo_venda_contrato=float(cfg_kwargs.get("custo_venda", 0.0)) * int(cfg_kwargs.get("tamanho_contrato", 100) or 100),
                tamanho_contrato=int(cfg_kwargs.get("tamanho_contrato", 100) or 100),
            )
            st.image(destino, use_container_width=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Não foi possível gerar o gráfico de payoff: {exc}")

# --- Backtest ---
with tab_bt:
    st.write("Simula vendas sucessivas de covered calls no histórico (prêmio por Black-Scholes "
             "com volatilidade realizada na data de entrada).")
    c1, c2, c3 = st.columns(3)
    bt_dist = c1.slider("Distância do strike (OTM)", 0.0, 0.30, 0.05, 0.01)
    bt_dias = c2.number_input("Horizonte (pregões)", 1, 120, 14)
    bt_janela = c3.number_input("Janela de vol (pregões)", 5, 252, 60)
    if st.button("🔁 Rodar backtest"):
        if not ativos:
            st.warning("Selecione ao menos um ativo.")
        else:
            try:
                cfg_kwargs = kwargs_config()
                with st.spinner("Simulando histórico..."):
                    df_bt = rodar_backtest(cfg_kwargs, float(bt_dist), int(bt_dias), int(bt_janela))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Erro no backtest: {exc}")
                df_bt = pd.DataFrame()
            if df_bt.empty:
                st.warning("Backtest sem resultados (histórico insuficiente para o horizonte/janela).")
            else:
                st.dataframe(
                    df_bt, use_container_width=True, hide_index=True,
                    column_config={
                        "retorno_medio_cc": st.column_config.NumberColumn("ret. médio CC", format="percent"),
                        "retorno_anualizado_cc": st.column_config.NumberColumn("ret. anual CC", format="percent"),
                        "taxa_exercicio": st.column_config.NumberColumn("taxa exercício", format="percent"),
                        "taxa_acerto": st.column_config.NumberColumn("taxa acerto", format="percent"),
                        "retorno_medio_buy_hold": st.column_config.NumberColumn("ret. médio B&H", format="percent"),
                        "vol_retorno_cc": st.column_config.NumberColumn("vol retorno CC", format="percent"),
                    },
                )
                st.download_button(
                    "⬇️ Baixar backtest (CSV)",
                    df_bt.to_csv(index=False).encode("utf-8"),
                    file_name="backtest_covered_call.csv",
                    mime="text/csv",
                )
