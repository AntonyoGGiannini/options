"""Entrypoint legado.

Mantido por compatibilidade. Carrega ``config.toml`` se existir (senão usa os
padrões) e executa a análise. Equivalente a rodar ``options --config config.toml``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from allocation.cli import main

if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if "--config" not in argv and "-c" not in argv and Path("config.toml").exists():
        argv = ["--config", "config.toml", *argv]
    sys.exit(main(argv))
