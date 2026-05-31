"""Configuração de logging estruturado para a aplicação."""

from __future__ import annotations

import logging

_CONFIGURADO = False


def configurar_logging(nivel: int | str = logging.INFO) -> None:
    """Configura o logging raiz da aplicação (idempotente)."""
    global _CONFIGURADO
    if _CONFIGURADO:
        return
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _CONFIGURADO = True


def obter_logger(nome: str) -> logging.Logger:
    """Retorna um logger nomeado, garantindo a configuração base."""
    configurar_logging()
    return logging.getLogger(nome)
