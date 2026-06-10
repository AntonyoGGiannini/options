"""Store local de cadeias de opções históricas (snapshots EOD por pregão).

Layout em disco: ``{pasta}/{ativo}/{YYYY-MM-DD}.parquet`` — um arquivo por
pregão, contendo a cadeia completa (calls e puts, coluna ``type``) vista
naquela data, mais o ``spot`` do fechamento. O schema é um superset do mock
CSV, então os snapshots alimentam o pipeline do screener sem adaptação.

A ingestão (rede) é separada — ver ``allocation.data.thetadata``. Este módulo
só lê/escreve o store local, no espírito do ProvedorMock.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from allocation.logging_setup import obter_logger

logger = obter_logger(__name__)

COLUNAS_OBRIGATORIAS = [
    "strike",
    "bid",
    "ask",
    "volume",
    "openInterest",
    "impliedVolatility",
    "expiration",
    "type",
]


@dataclass
class SnapshotChain:
    """Cadeia de opções de um ativo como vista em um pregão específico."""

    ativo: str
    data_pregao: pd.Timestamp
    df_calls: pd.DataFrame
    df_puts: pd.DataFrame
    spot: float


def _normalizar_data(data: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(data).normalize()


class StoreChainsHistoricas:
    """Lê e grava snapshots EOD de cadeias de opções em parquet."""

    def __init__(self, pasta: str | Path = "chains_historicas") -> None:
        self.pasta = Path(pasta)

    def _caminho(self, ativo: str, data_pregao: str | pd.Timestamp) -> Path:
        data = _normalizar_data(data_pregao)
        return self.pasta / ativo / f"{data.date().isoformat()}.parquet"

    def tem_snapshot(self, ativo: str, data_pregao: str | pd.Timestamp) -> bool:
        return self._caminho(ativo, data_pregao).exists()

    def salvar_snapshot(
        self,
        ativo: str,
        data_pregao: str | pd.Timestamp,
        df_chain: pd.DataFrame,
        spot: float,
    ) -> Path:
        """Grava a cadeia completa (calls + puts) de um pregão.

        ``df_chain`` deve conter as colunas de ``COLUNAS_OBRIGATORIAS``; as
        colunas ``ativo``, ``data_pregao`` e ``spot`` são (re)preenchidas aqui
        para o arquivo ser auto-contido.
        """
        faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df_chain.columns]
        if faltantes:
            raise ValueError(f"Snapshot sem colunas obrigatórias: {faltantes}")
        if not float(spot) > 0:
            raise ValueError("spot deve ser positivo")

        data = _normalizar_data(data_pregao)
        df = df_chain.copy()
        df["ativo"] = ativo
        df["data_pregao"] = data.date().isoformat()
        df["spot"] = float(spot)
        df["strike"] = df["strike"].astype(float)
        df["type"] = df["type"].astype(str).str.upper()

        caminho = self._caminho(ativo, data)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(caminho, index=False)
        return caminho

    def carregar_snapshot(self, ativo: str, data_pregao: str | pd.Timestamp) -> SnapshotChain:
        caminho = self._caminho(ativo, data_pregao)
        if not caminho.exists():
            raise FileNotFoundError(f"Snapshot não encontrado: {caminho}")
        df = pd.read_parquet(caminho)
        tipo = df["type"].astype(str).str.upper()
        return SnapshotChain(
            ativo=ativo,
            data_pregao=_normalizar_data(data_pregao),
            df_calls=df[tipo == "CALL"].reset_index(drop=True),
            df_puts=df[tipo == "PUT"].reset_index(drop=True),
            spot=float(df["spot"].iloc[0]),
        )

    def datas_disponiveis(
        self,
        ativo: str,
        inicio: str | pd.Timestamp | None = None,
        fim: str | pd.Timestamp | None = None,
    ) -> list[pd.Timestamp]:
        """Datas de pregão com snapshot, ordenadas (lê só nomes de arquivo)."""
        pasta_ativo = self.pasta / ativo
        if not pasta_ativo.is_dir():
            return []
        datas = sorted(pd.Timestamp(p.stem) for p in pasta_ativo.glob("*.parquet"))
        if inicio is not None:
            t0 = _normalizar_data(inicio)
            datas = [d for d in datas if d >= t0]
        if fim is not None:
            t1 = _normalizar_data(fim)
            datas = [d for d in datas if d <= t1]
        return datas

    def serie_spot(
        self,
        ativo: str,
        inicio: str | pd.Timestamp | None = None,
        fim: str | pd.Timestamp | None = None,
    ) -> pd.Series:
        """Série de spots de fechamento dos snapshots (índice = data do pregão).

        Usada na liquidação do replay (S_T no vencimento). Lê só a primeira
        linha de cada parquet (coluna ``spot``).
        """
        datas = self.datas_disponiveis(ativo, inicio, fim)
        valores = {}
        for data in datas:
            df = pd.read_parquet(self._caminho(ativo, data), columns=["spot"])
            if not df.empty:
                valores[data] = float(df["spot"].iloc[0])
        return pd.Series(valores, dtype=float).sort_index()
