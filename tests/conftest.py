"""Fixtures compartilhadas, baseadas nos dados mock versionados (IBIT)."""

from __future__ import annotations

from pathlib import Path

import pytest

from options.data.mock_provider import ProvedorMock

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def pasta_mock() -> str:
    return str(RAIZ / "base_mock")


@pytest.fixture
def dados_ibit(pasta_mock):
    """DadosMercado de IBIT carregados dos arquivos mock."""
    return ProvedorMock(pasta_mock).obter("IBIT")
