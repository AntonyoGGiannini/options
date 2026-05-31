"""Cache em disco (parquet) com TTL para dados de mercado."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from options.logging_setup import obter_logger

logger = obter_logger(__name__)


class CacheDisco:
    """Cache simples de DataFrames/Series em parquet, com expiração por TTL."""

    def __init__(self, pasta: str | Path = ".cache", ttl_horas: float = 6.0) -> None:
        self.pasta = Path(pasta)
        self.ttl_segundos = ttl_horas * 3600.0

    def _caminho(self, chave: str) -> Path:
        return self.pasta / f"{chave}.parquet"

    def _expirado(self, caminho: Path) -> bool:
        if self.ttl_segundos <= 0:
            return True
        idade = time.time() - caminho.stat().st_mtime
        return idade > self.ttl_segundos

    def obter_df(self, chave: str) -> pd.DataFrame | None:
        caminho = self._caminho(chave)
        if not caminho.exists() or self._expirado(caminho):
            return None
        try:
            logger.debug("Cache hit: %s", chave)
            return pd.read_parquet(caminho)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao ler cache %s: %s", chave, exc)
            return None

    def salvar_df(self, chave: str, df: pd.DataFrame) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        try:
            df.to_parquet(self._caminho(chave))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao salvar cache %s: %s", chave, exc)

    def obter_float(self, chave: str) -> float | None:
        caminho = self.pasta / f"{chave}.json"
        if not caminho.exists() or self._expirado(caminho):
            return None
        try:
            with caminho.open() as f:
                return float(json.load(f)["valor"])
        except Exception:  # noqa: BLE001
            return None

    def salvar_float(self, chave: str, valor: float) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        caminho = self.pasta / f"{chave}.json"
        with caminho.open("w") as f:
            json.dump({"valor": float(valor)}, f)
