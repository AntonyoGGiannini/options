"""Testes da configuração e sua validação."""

from __future__ import annotations

import pytest

from options.config import Config


def test_defaults_validos():
    c = Config()
    assert c.top_n >= 1
    assert 0 <= c.prob_exerc_max <= 1


def test_prob_exerc_max_fora_de_faixa():
    with pytest.raises(ValueError):
        Config(prob_exerc_max=1.5)


def test_usar_premio_invalido():
    with pytest.raises(ValueError):
        Config(usar_premio="meio")


def test_lista_ativos_vazia():
    with pytest.raises(ValueError):
        Config(lista_ativos=[])


def test_intervalo_dias_invalido():
    with pytest.raises(ValueError):
        Config(min_dias=30, max_dias=10)


def test_from_dict_rejeita_chave_desconhecida():
    with pytest.raises(ValueError):
        Config.from_dict({"parametro_inexistente": 1})


def test_aplicar_overrides_ignora_none():
    c = Config(top_n=5)
    c2 = c.aplicar_overrides(top_n=None, prob_exerc_max=0.2)
    assert c2.top_n == 5
    assert c2.prob_exerc_max == 0.2


def test_from_toml(tmp_path):
    conteudo = 'lista_ativos = ["AAPL", "MSFT"]\ntop_n = 3\nprob_exerc_max = 0.10\n'
    arq = tmp_path / "c.toml"
    arq.write_text(conteudo)
    c = Config.from_toml(arq)
    assert c.lista_ativos == ["AAPL", "MSFT"]
    assert c.top_n == 3
    assert c.prob_exerc_max == 0.10
