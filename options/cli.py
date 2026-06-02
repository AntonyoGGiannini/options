"""Interface de linha de comando."""

from __future__ import annotations

import argparse
import logging
import sys

from options.config import Config
from options.logging_setup import configurar_logging, obter_logger
from options.portfolio import avaliar_carteira, carregar_carteira, reportar_carteira
from options.runner import executar_backtest, executar_e_reportar

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

    sub = parser.add_subparsers(dest="comando")
    parser.set_defaults(comando="run")

    bt = sub.add_parser("backtest", help="Backtest da estratégia sobre o histórico.")
    bt.add_argument("--distancia", type=float, default=0.05,
                    help="Distância do strike OTM (ex.: 0.05 = 5%% acima).")
    bt.add_argument("--dias", type=int, default=14,
                    help="Horizonte até o vencimento, em pregões.")
    bt.add_argument("--janela-vol", type=int, default=60,
                    help="Janela (pregões) da volatilidade realizada.")

    ca = sub.add_parser("carteira", help="Analisa a carteira de um cliente (JSON).")
    ca.add_argument("--arquivo", required=True,
                    help="Caminho do JSON com a posição do cliente.")
    ca.add_argument("--saida", default="analise_carteira.xlsx",
                    help="Arquivo Excel de saída (3 abas).")
    ca.add_argument("--limiar-premio-restante", type=float, default=None,
                    help="Gatilho de rolagem: fração do prêmio ainda em aberto (ex.: 0.20).")
    ca.add_argument("--rolagem-min-dias", type=int, default=None,
                    help="Mínimo de dias até o vencimento-alvo do roll-out.")
    ca.add_argument("--rolagem-max-dias", type=int, default=None,
                    help="Máximo de dias até o vencimento-alvo do roll-out.")

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
        "limiar_premio_restante": getattr(args, "limiar_premio_restante", None),
        "rolagem_min_dias": getattr(args, "rolagem_min_dias", None),
        "rolagem_max_dias": getattr(args, "rolagem_max_dias", None),
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

    if args.comando == "backtest":
        df = executar_backtest(
            config,
            distancia_strike_pct=args.distancia,
            dias_vencimento=args.dias,
            janela_vol=args.janela_vol,
        )
        if df.empty:
            logger.warning("Backtest não produziu resultados.")
            return 1
        print("\n" + "=" * 80)
        print(f"BACKTEST COVERED CALL | distância {args.distancia:.0%} | {args.dias} pregões")
        print("=" * 80)
        print(df.to_string(index=False))
        return 0

    if args.comando == "carteira":
        try:
            carteira = carregar_carteira(args.arquivo)
        except (ValueError, FileNotFoundError) as exc:
            logger.error("Carteira inválida: %s", exc)
            return 2
        relatorio = avaliar_carteira(carteira, config)
        reportar_carteira(relatorio, args.saida)
        return 0

    df_final = executar_e_reportar(config)
    return 0 if not df_final.empty else 1


if __name__ == "__main__":
    sys.exit(main())
