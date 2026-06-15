"""Provedor de dados offline a partir de arquivos mock locais."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from allocation.data.base import DadosMercado
from allocation.logging_setup import obter_logger

logger = obter_logger(__name__)


def salvar_dados_mock(ativo, df_calls, preco_atual, historico_precos, pasta="."):
    """
    Salva os dados obtidos de um provedor em arquivos locais para uso offline.

    Arquivos gerados:
      mock_{ativo}_calls.csv      — cadeia de opções
      mock_{ativo}_historico.csv  — série histórica de preços
      mock_{ativo}_info.json      — preco_atual e metadados
    """
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

    logger.info("Dados mock salvos em: %s_calls.csv | _historico.csv | _info.json", prefixo)


class ProvedorMock:
    """Lê dados previamente salvos localmente, substituindo o yfinance."""

    def __init__(self, pasta: str | Path = ".") -> None:
        self.pasta = str(pasta)

    def obter(self, ativo: str, periodo_historico: str = "5y") -> DadosMercado:
        prefixo = os.path.join(self.pasta, f"mock_{ativo}")
        arquivo_calls = f"{prefixo}_calls.csv"
        arquivo_historico = f"{prefixo}_historico.csv"
        arquivo_info = f"{prefixo}_info.json"

        for arq in (arquivo_calls, arquivo_historico, arquivo_info):
            if not os.path.exists(arq):
                raise FileNotFoundError(
                    f"Arquivo mock não encontrado: {arq}\n"
                    f"Rode online com salvar_mock=True para gerar os arquivos."
                )

        df_calls = pd.read_csv(arquivo_calls)

        historico_df = pd.read_csv(
            arquivo_historico, index_col=0, parse_dates=True, date_format="mixed"
        )
        historico_precos = historico_df["Close"].dropna()

        with open(arquivo_info) as f:
            info = json.load(f)
        preco_atual = float(info["preco_atual"])

        logger.info(
            "Dados mock carregados: %s | preco_atual=%.2f | calls=%d | historico=%d pregões",
            ativo, preco_atual, len(df_calls), len(historico_precos),
        )
        return DadosMercado(
            ativo=ativo,
            df_calls=df_calls,
            preco_atual=preco_atual,
            historico_precos=historico_precos,
        )
