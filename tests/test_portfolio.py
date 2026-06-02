"""Testes da análise de carteira (covered call, rolagem e buy-write)."""

from __future__ import annotations

import json

import pytest

from options.config import Config
from options.data.mock_provider import ProvedorMock
from options.portfolio import (
    CallVendida,
    Carteira,
    PosicaoAcao,
    avaliar_carteira,
    carregar_carteira,
)


def _config(pasta_mock: str, **extra) -> Config:
    base = dict(
        lista_ativos=["IBIT"],
        top_n=5,
        prob_exerc_max=0.99,
        min_dias=0,
        max_dias=365,
        rolagem_min_dias=0,
        rolagem_max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )
    base.update(extra)
    return Config(**base)


# --------------------------------------------------------------------------- #
# carregar_carteira                                                           #
# --------------------------------------------------------------------------- #
def test_carregar_carteira_valida(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps({
        "cliente": "Fulano",
        "caixa": 1000,
        "posicoes": [{"ativo": "IBIT", "quantidade": 300, "preco_medio": 38.0}],
        "calls_vendidas": [{"ativo": "IBIT", "strike": 45.0,
                            "expiration": "2026-06-18", "premio_recebido": 2.0,
                            "contratos": 1}],
    }))
    cart = carregar_carteira(arq)
    assert cart.cliente == "Fulano"
    assert cart.caixa == 1000
    assert cart.posicoes[0].quantidade == 300
    assert cart.calls_vendidas[0].strike == 45.0
    assert cart.ativos_detidos() == {"IBIT"}
    assert cart.preco_medio_de("IBIT") == 38.0


def test_carregar_carteira_campo_faltando(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps({"posicoes": [{"ativo": "IBIT", "quantidade": 100}]}))
    with pytest.raises(ValueError, match="preco_medio"):
        carregar_carteira(arq)


def test_carregar_carteira_arquivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_carteira(tmp_path / "nao_existe.json")


# --------------------------------------------------------------------------- #
# Covered call                                                                #
# --------------------------------------------------------------------------- #
def test_covered_call_sugere_contratos_descobertos(pasta_mock):
    carteira = Carteira(
        posicoes=[PosicaoAcao("IBIT", 300, 38.0)],
        calls_vendidas=[CallVendida("IBIT", 45.0, "2026-06-18", 2.0, 1)],
    )
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
    assert not rel.covered_call.empty
    # 300 ações = 3 contratos possíveis, 1 já coberto → 2 descobertos
    assert (rel.covered_call["contratos_sugeridos"] == 2).all()
    # strikes abaixo do custo (38) são excluídos por padrão
    assert (rel.covered_call["strike"] >= 38.0).all()


def test_covered_call_posicao_coberta_nao_sugere(pasta_mock):
    # 100 ações = 1 contrato, 1 já coberto → nada descoberto
    carteira = Carteira(
        posicoes=[PosicaoAcao("IBIT", 100, 38.0)],
        calls_vendidas=[CallVendida("IBIT", 45.0, "2026-06-18", 2.0, 1)],
    )
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
    assert rel.covered_call.empty


# --------------------------------------------------------------------------- #
# Rolagem                                                                     #
# --------------------------------------------------------------------------- #
def test_rolagem_premio_restante_baixo_dispara_rolar(pasta_mock):
    # call strike 45 / 2026-06-18: recompra ~0.365; prêmio recebido 2.0 → ~18% restante
    carteira = Carteira(
        posicoes=[PosicaoAcao("IBIT", 100, 38.0)],
        calls_vendidas=[CallVendida("IBIT", 45.0, "2026-06-18", 2.0, 1)],
    )
    rel = avaliar_carteira(
        carteira, _config(pasta_mock, limiar_premio_restante=0.20),
        ProvedorMock(pasta_mock),
    )
    linha = rel.rolagem.iloc[0]
    assert linha["premio_restante_pct"] <= 0.20
    assert linha["acao"] == "rolar"
    assert linha["venc_novo"] > "2026-06-18"
    assert linha["strike_novo"] >= 45.0


def test_rolagem_premio_alto_mantem(pasta_mock):
    # prêmio recebido baixo (0.40) → recompra 0.365 ≈ 91% restante → manter
    carteira = Carteira(
        calls_vendidas=[CallVendida("IBIT", 45.0, "2026-06-18", 0.40, 1)],
    )
    rel = avaliar_carteira(
        carteira, _config(pasta_mock, limiar_premio_restante=0.20),
        ProvedorMock(pasta_mock),
    )
    linha = rel.rolagem.iloc[0]
    assert linha["premio_restante_pct"] > 0.20
    assert linha["acao"] == "manter"


# --------------------------------------------------------------------------- #
# Buy-write                                                                   #
# --------------------------------------------------------------------------- #
def test_buy_write_exclui_ativos_detidos(pasta_mock):
    # IBIT é o único ativo do universo e está detido → buy-write vazio
    carteira = Carteira(posicoes=[PosicaoAcao("IBIT", 100, 38.0)])
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
    assert rel.buy_write.empty


def test_buy_write_ranqueia_nao_detidos(pasta_mock):
    # cliente não detém IBIT → IBIT entra no buy-write, ranqueado por score
    carteira = Carteira()
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
    assert not rel.buy_write.empty
    assert (rel.buy_write["ativo"] == "IBIT").all()
    assert rel.buy_write["score_venda"].is_monotonic_decreasing
    assert "capital_por_contrato" in rel.buy_write.columns
    assert (rel.buy_write["ranking_global"] == range(1, len(rel.buy_write) + 1)).all()
