"""Retry com backoff exponencial para chamadas de rede instáveis."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from allocation.logging_setup import obter_logger

logger = obter_logger(__name__)

T = TypeVar("T")


def com_retry(
    func: Callable[[], T],
    tentativas: int = 4,
    espera_inicial: float = 2.0,
    descricao: str = "operação",
) -> T:
    """Executa ``func`` com retry e backoff exponencial (2s, 4s, 8s, ...).

    Re-lança a última exceção se todas as tentativas falharem.
    """
    espera = espera_inicial
    ultima_exc: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 — re-lançada ao fim
            ultima_exc = exc
            if tentativa == tentativas:
                break
            logger.warning(
                "Falha em %s (tentativa %d/%d): %s — aguardando %.0fs",
                descricao, tentativa, tentativas, exc, espera,
            )
            time.sleep(espera)
            espera *= 2
    assert ultima_exc is not None
    raise ultima_exc
