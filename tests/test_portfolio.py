"""Testes da análise de carteira (covered call, rolagem e buy-write)."""

from __future__ import annotations

import json

import pytest

from allocation.config import Config
from allocation.data.mock_provider import ProvedorMock
from allocation.risco.portfolio import (
    CallVendida,
    Carteira,
    PosicaoAcao,
    avaliar_carteira,
    avaliar_carteiras,
    carregar_carteira,
    carregar_carteiras,
)


def _config(pasta_mock: str) -> Config:
    return Config(
        lista_ativos=["IBIT"],
        top_n=5,
        prob_exerc_max=0.99,
        min_dias=0,
        max_dias=365,
        modo_offline=True,
        pasta_mock=pasta_mock,
    )


# --------------------------------------------------------------------------- #
# carregar_carteira                                                           #
# --------------------------------------------------------------------------- #
def test_carregar_carteira_valida(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(
        json.dumps(
            {
                "cliente": "Fulano",
                "caixa": 1000,
                "posicoes": [{"ativo": "IBIT", "quantidade": 300, "preco_medio": 38.0}],
                "calls_vendidas": [
                    {
                        "ativo": "IBIT",
                        "strike": 45.0,
                        "expiration": "2026-06-18",
                        "premio_recebido": 2.0,
                        "contratos": 1,
                    }
                ],
                "limiar_premio_restante": 0.15,
                "rolagem_min_dias": 14,
                "rolagem_max_dias": 45,
            }
        )
    )
    cart = carregar_carteira(arq)
    assert cart.cliente == "Fulano"
    assert cart.caixa == 1000
    assert cart.posicoes[0].quantidade == 300
    assert cart.calls_vendidas[0].strike == 45.0
    assert cart.ativos_detidos() == {"IBIT"}
    assert cart.preco_medio_de("IBIT") == 38.0
    assert cart.limiar_premio_restante == 0.15
    assert cart.rolagem_min_dias == 14
    assert cart.rolagem_max_dias == 45


def test_carregar_carteira_campo_faltando(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(json.dumps({"posicoes": [{"ativo": "IBIT", "quantidade": 100}]}))
    with pytest.raises(ValueError, match="preco_medio"):
        carregar_carteira(arq)


def test_carregar_carteira_arquivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_carteira(tmp_path / "nao_existe.json")


# --------------------------------------------------------------------------- #
# carregar_carteiras (múltiplos clientes)                                     #
# --------------------------------------------------------------------------- #
def test_carregar_carteiras_array(tmp_path):
    arq = tmp_path / "c.json"
    arq.write_text(
        json.dumps(
            [
                {
                    "cliente": "Fulano",
                    "posicoes": [{"ativo": "IBIT", "quantidade": 300, "preco_medio": 38.0}],
                },
                {
                    "cliente": "Beltrano",
                    "posicoes": [{"ativo": "AAPL", "quantidade": 100, "preco_medio": 180.0}],
                },
            ]
        )
    )
    carteiras = carregar_carteiras(arq)
    assert len(carteiras) == 2
    assert carteiras[0].cliente == "Fulano"
    assert carteiras[1].cliente == "Beltrano"
    assert carteiras[1].ativos_detidos() == {"AAPL"}


def test_carregar_carteiras_objeto_unico_retrocompat(tmp_path):
    # formato antigo (objeto único) ainda vira lista de um elemento
    arq = tmp_path / "c.json"
    arq.write_text(
        json.dumps(
            {
                "cliente": "Fulano",
                "posicoes": [{"ativo": "IBIT", "quantidade": 300, "preco_medio": 38.0}],
            }
        )
    )
    carteiras = carregar_carteiras(arq)
    assert len(carteiras) == 1
    assert carteiras[0].cliente == "Fulano"


def test_avaliar_carteiras_itera_clientes(pasta_mock):
    carteiras = [
        Carteira(cliente="A", posicoes=[PosicaoAcao("IBIT", 300, 38.0)]),
        Carteira(cliente="B"),
    ]
    rels = avaliar_carteiras(carteiras, _config(pasta_mock), ProvedorMock(pasta_mock))
    assert len(rels) == 2
    assert [r.cliente for r in rels] == ["A", "B"]
    # cliente A detém IBIT → buy-write vazio; cliente B não detém → buy-write com IBIT
    assert rels[0].buy_write.empty
    assert not rels[1].buy_write.empty


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
        limiar_premio_restante=0.20,
        rolagem_min_dias=0,
        rolagem_max_dias=365,
    )
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
    linha = rel.rolagem.iloc[0]
    assert linha["premio_restante_pct"] <= 0.20
    assert linha["acao"] == "rolar"
    assert linha["venc_novo"] > "2026-06-18"
    assert linha["strike_novo"] >= 45.0


def test_rolagem_premio_alto_mantem(pasta_mock):
    # prêmio recebido baixo (0.40) → recompra 0.365 ≈ 91% restante → manter
    carteira = Carteira(
        calls_vendidas=[CallVendida("IBIT", 45.0, "2026-06-18", 0.40, 1)],
        limiar_premio_restante=0.20,
    )
    rel = avaliar_carteira(carteira, _config(pasta_mock), ProvedorMock(pasta_mock))
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
