"""Interface de linha de comando."""

from __future__ import annotations

import argparse
import logging
import sys

from options.config import Config
from options.logging_setup import configurar_logging, obter_logger
from options.runner import executar_e_reportar

logger = obter_logger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="options",
        description="Análise e ranking quantitativo de covered calls.",
    )
    parser.add_argument(
        "-c", "--config", default=None,
        help="Caminho para um arquivo TOML de configuração.",
    )
    parser.add_argument(
        "--ativos", default=None,
        help="Lista de tickers separada por vírgula (sobrescreve a config).",
    )
    parser.add_argument("--top-n", type=int, default=None, help="Top N opções por ativo.")
    parser.add_argument(
        "--offline", action="store_true", default=None,
        help="Usa dados mock locais (sem internet).",
    )
    parser.add_argument(
        "--salvar-mock", action="store_true", default=None,
        help="Salva os dados obtidos online como arquivos mock.",
    )
    parser.add_argument(
        "--sem-cache", action="store_true", default=False,
        help="Desabilita o cache em disco do provedor online.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Logging em nível DEBUG.",
    )
    return parser.parse_args(argv)


def construir_config(args: argparse.Namespace) -> Config:
    """Constrói a Config a partir do arquivo (se houver) e dos overrides da CLI."""
    config = Config.from_toml(args.config) if args.config else Config()

    ativos = args.ativos.split(",") if args.ativos else None
    overrides = {
        "lista_ativos": [a.strip() for a in ativos] if ativos else None,
        "top_n": args.top_n,
        "modo_offline": args.offline,
        "salvar_mock": args.salvar_mock,
        "usar_cache": False if args.sem_cache else None,
    }
    return config.aplicar_overrides(**overrides)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configurar_logging(logging.DEBUG if args.verbose else logging.INFO)

    try:
        config = construir_config(args)
    except (ValueError, FileNotFoundError) as exc:
        logger.error("Configuração inválida: %s", exc)
        return 2

    df_final = executar_e_reportar(config)
    return 0 if not df_final.empty else 1


if __name__ == "__main__":
    sys.exit(main())
