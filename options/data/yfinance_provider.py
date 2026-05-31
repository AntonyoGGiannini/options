"""Provedor de dados via yfinance, com cache em disco e retry."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from options.data.base import DadosMercado
from options.data.cache import CacheDisco
from options.data.retry import com_retry
from options.logging_setup import obter_logger

logger = obter_logger(__name__)


class ProvedorYFinance:
    """Obtém preço, cadeia de opções e histórico via yfinance.

    Aplica filtros de liquidez na cadeia de opções e, opcionalmente, usa um
    cache em disco com TTL para evitar chamadas repetidas à API.
    """

    def __init__(self, cache: CacheDisco | None = None) -> None:
        self.cache = cache

    # --- chamadas brutas ---------------------------------------------------

    def calcular_preco_atual(self, ativo: str) -> float:
        if self.cache is not None:
            cacheado = self.cache.obter_float(f"{ativo}_preco")
            if cacheado is not None:
                return cacheado

        def _buscar() -> float:
            ticker = yf.Ticker(ativo)
            hist = ticker.history(period="5d")
            if hist.empty:
                raise ValueError(f"Não foi possível obter preço atual para {ativo}")
            return float(hist["Close"].dropna().iloc[-1])

        preco = com_retry(_buscar, descricao=f"preço de {ativo}")
        if self.cache is not None:
            self.cache.salvar_float(f"{ativo}_preco", preco)
        return preco

    def carregar_historico_ativo(self, ativo: str, periodo: str = "5y") -> pd.Series:
        chave = f"{ativo}_hist_{periodo}"
        if self.cache is not None:
            df = self.cache.obter_df(chave)
            if df is not None:
                return df["Close"]

        def _buscar() -> pd.Series:
            ticker = yf.Ticker(ativo)
            hist = ticker.history(period=periodo, auto_adjust=True)
            if hist.empty:
                return pd.Series(dtype=float)
            return hist["Close"].dropna()

        serie = com_retry(_buscar, descricao=f"histórico de {ativo}")
        if self.cache is not None and len(serie) > 0:
            self.cache.salvar_df(chave, serie.to_frame("Close"))
        return serie

    def obter_calls(self, ativo: str) -> pd.DataFrame:
        chave = f"{ativo}_calls"
        if self.cache is not None:
            df = self.cache.obter_df(chave)
            if df is not None:
                return df

        def _buscar() -> pd.DataFrame:
            ticker = yf.Ticker(ativo)
            expirations = ticker.options

            lista_calls = []
            for expiration in expirations:
                try:
                    calls = ticker.option_chain(expiration).calls.copy()
                    calls["mid"] = (calls["bid"] + calls["ask"]) / 2
                    calls["spread_pct"] = (calls["ask"] - calls["bid"]) / calls["mid"]
                    calls = calls[
                        (calls["volume"] >= 100)
                        & (calls["openInterest"] >= 500)
                        & (calls["spread_pct"] <= 0.15)
                    ].copy()
                    calls["ativo"] = ativo
                    calls["expiration"] = expiration
                    calls["type"] = "CALL"
                    lista_calls.append(calls)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Erro no vencimento %s de %s: %s", expiration, ativo, exc)

            return pd.concat(lista_calls, ignore_index=True) if lista_calls else pd.DataFrame()

        df = com_retry(_buscar, descricao=f"cadeia de opções de {ativo}")
        if self.cache is not None and not df.empty:
            self.cache.salvar_df(chave, df)
        return df

    # --- interface ProvedorDados ------------------------------------------

    def obter(self, ativo: str, periodo_historico: str = "5y") -> DadosMercado:
        return DadosMercado(
            ativo=ativo,
            df_calls=self.obter_calls(ativo),
            preco_atual=self.calcular_preco_atual(ativo),
            historico_precos=self.carregar_historico_ativo(ativo, periodo_historico),
        )
