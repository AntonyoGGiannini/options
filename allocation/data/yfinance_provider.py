"""Provedor de dados via yfinance, com cache em disco e retry."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from allocation.data.base import DadosMercado
from allocation.data.cache import CacheDisco
from allocation.data.retry import com_retry
from allocation.logging_setup import obter_logger

logger = obter_logger(__name__)


class ProvedorYFinance:
    """Obtém preço, cadeia de opções e histórico via yfinance.

    Mantém todas as opções da cadeia (a liquidez é avaliada como flag no
    pipeline, não mais descartada aqui) e, opcionalmente, usa um cache em disco
    com TTL para evitar chamadas repetidas à API.
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

    def obter_cadeia(self, ativo: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Cadeia completa de opções (calls, puts) por vencimento."""
        chave_calls = f"{ativo}_calls"
        chave_puts = f"{ativo}_puts"
        if self.cache is not None:
            df_calls = self.cache.obter_df(chave_calls)
            df_puts = self.cache.obter_df(chave_puts)
            if df_calls is not None and df_puts is not None:
                return df_calls, df_puts

        def _anotar(df: pd.DataFrame, expiration: str, tipo: str) -> pd.DataFrame:
            df = df.copy()
            df["mid"] = (df["bid"] + df["ask"]) / 2
            df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"]
            df["ativo"] = ativo
            df["expiration"] = expiration
            df["type"] = tipo
            return df

        def _buscar() -> tuple[pd.DataFrame, pd.DataFrame]:
            ticker = yf.Ticker(ativo)
            expirations = ticker.options

            lista_calls = []
            lista_puts = []
            for expiration in expirations:
                try:
                    cadeia = ticker.option_chain(expiration)
                    lista_calls.append(_anotar(cadeia.calls, expiration, "CALL"))
                    lista_puts.append(_anotar(cadeia.puts, expiration, "PUT"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Erro no vencimento %s de %s: %s", expiration, ativo, exc)

            df_calls = pd.concat(lista_calls, ignore_index=True) if lista_calls else pd.DataFrame()
            df_puts = pd.concat(lista_puts, ignore_index=True) if lista_puts else pd.DataFrame()
            return df_calls, df_puts

        df_calls, df_puts = com_retry(_buscar, descricao=f"cadeia de opções de {ativo}")
        if self.cache is not None and not df_calls.empty:
            self.cache.salvar_df(chave_calls, df_calls)
        if self.cache is not None and not df_puts.empty:
            self.cache.salvar_df(chave_puts, df_puts)
        return df_calls, df_puts

    def obter_calls(self, ativo: str) -> pd.DataFrame:
        return self.obter_cadeia(ativo)[0]

    # --- interface ProvedorDados ------------------------------------------

    def obter(self, ativo: str, periodo_historico: str = "5y") -> DadosMercado:
        df_calls, df_puts = self.obter_cadeia(ativo)
        return DadosMercado(
            ativo=ativo,
            df_calls=df_calls,
            preco_atual=self.calcular_preco_atual(ativo),
            historico_precos=self.carregar_historico_ativo(ativo, periodo_historico),
            df_puts=df_puts,
        )
