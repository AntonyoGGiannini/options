"""Configuração declarativa e validada da aplicação.

A configuração pode ser construída a partir de um arquivo TOML e/ou sobrescrita
por argumentos de linha de comando. Toda a validação de tipos e faixas acontece
aqui, num único lugar, em vez de espalhada pelo código de execução.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class Config:
    """Parâmetros de execução da análise de covered calls."""

    # --- universo ---
    lista_ativos: list[str] = field(default_factory=lambda: ["IBIT"])
    top_n: int = 5

    # --- preço médio de aquisição (ranking + gráfico) ---
    # None, float único ou dict {ativo: preco}
    preco_medio_aquisicao: float | dict[str, float] | None = None

    # --- risco / mercado ---
    prob_exerc_max: float = 0.15
    taxa_livre_risco: float = 0.045
    # float único para todos os ativos, ou dict {ativo: yield}
    dividend_yield: float | dict[str, float] = 0.0

    # --- modelos de probabilidade ---
    usar_prob_d2: bool = True
    usar_prob_empirica: bool = True
    periodo_historico: str = "5y"
    min_amostras_empirica: int = 30

    # --- prêmio / convenção ---
    usar_premio: str = "bid"
    dias_ano: int = 365
    min_dias: int = 7
    max_dias: int = 20

    # --- filtro de strike ---
    # Distância mínima do strike em relação ao preço atual (ex.: 0.0 = ATM+,
    # -0.05 = permite até 5% ITM). Default 0.0 mantém comportamento anterior (OTM).
    min_distancia_strike_pct: float = 0.0

    # --- custos ---
    tamanho_contrato: int = 100
    custo_compra: float = 0.0
    custo_venda: float = 0.0
    # custo de exercício (atribuição) por contrato = max(pct * valor de venda,
    # mínimo) + taxa fixa. valor de venda = strike * tamanho_contrato.
    # Default: 0,25% do valor de venda ou US$ 10 (o que for maior).
    custo_exercicio_pct: float = 0.0025
    custo_exercicio_min: float = 10.0
    custo_exercicio: float = 0.0  # taxa fixa adicional por contrato (opcional)

    # --- dados ---
    modo_offline: bool = False
    salvar_mock: bool = False
    pasta_mock: str = "."
    usar_cache: bool = True
    cache_ttl_horas: float = 6.0
    pasta_cache: str = ".cache"

    # --- greeks no score ---
    peso_theta: float = 0.0
    peso_vega: float = 0.0

    # --- saída ---
    arquivo_excel: str = "top_opcoes_covered_call.xlsx"

    def __post_init__(self) -> None:
        self.validar()

    def validar(self) -> None:
        """Valida tipos e faixas; lança ValueError com mensagem clara."""
        if not self.lista_ativos:
            raise ValueError("lista_ativos não pode ser vazia")
        if self.top_n < 1:
            raise ValueError("top_n deve ser >= 1")
        if not (0.0 <= self.prob_exerc_max <= 1.0):
            raise ValueError("prob_exerc_max deve estar em [0, 1]")
        if self.taxa_livre_risco < 0:
            raise ValueError("taxa_livre_risco não pode ser negativa")
        if isinstance(self.dividend_yield, dict):
            if any(v < 0 for v in self.dividend_yield.values()):
                raise ValueError("dividend_yield não pode ser negativo")
        elif self.dividend_yield < 0:
            raise ValueError("dividend_yield não pode ser negativo")
        if self.usar_premio not in {"bid", "ask", "lastPrice", "mid"}:
            raise ValueError("usar_premio deve ser: bid, ask, lastPrice ou mid")
        if self.dias_ano <= 0:
            raise ValueError("dias_ano deve ser > 0")
        if self.min_dias < 0 or self.max_dias < self.min_dias:
            raise ValueError("intervalo de dias inválido (min_dias/max_dias)")
        if self.min_distancia_strike_pct < -1.0:
            raise ValueError("min_distancia_strike_pct não pode ser menor que -1.0")
        if self.tamanho_contrato <= 0:
            raise ValueError("tamanho_contrato deve ser > 0")
        if self.custo_compra < 0 or self.custo_venda < 0 or self.custo_exercicio < 0:
            raise ValueError("custos (compra/venda/exercício) não podem ser negativos")
        if self.custo_exercicio_pct < 0:
            raise ValueError("custo_exercicio_pct não pode ser negativo")
        if self.custo_exercicio_min < 0:
            raise ValueError("custo_exercicio_min não pode ser negativo")
        if self.cache_ttl_horas < 0:
            raise ValueError("cache_ttl_horas não pode ser negativo")
        if self.peso_theta < 0:
            raise ValueError("peso_theta não pode ser negativo")
        if self.peso_vega < 0:
            raise ValueError("peso_vega não pode ser negativo")

    @classmethod
    def from_dict(cls, dados: dict[str, Any]) -> Config:
        """Cria uma Config a partir de um dict, ignorando chaves desconhecidas."""
        validos = {f.name for f in fields(cls)}
        desconhecidas = set(dados) - validos
        if desconhecidas:
            raise ValueError(f"Chaves de configuração desconhecidas: {sorted(desconhecidas)}")
        return cls(**{k: v for k, v in dados.items() if k in validos})

    @classmethod
    def from_toml(cls, caminho: str | Path) -> Config:
        """Carrega a configuração de um arquivo TOML."""
        caminho = Path(caminho)
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo de configuração não encontrado: {caminho}")
        with caminho.open("rb") as f:
            dados = tomllib.load(f)
        return cls.from_dict(dados)

    def dividend_para(self, ativo: str) -> float:
        """Resolve o dividend yield de um ativo (suporta valor único ou por ativo)."""
        if isinstance(self.dividend_yield, dict):
            return float(self.dividend_yield.get(ativo, 0.0))
        return float(self.dividend_yield)

    def custo_exercicio_para(self, strike: float) -> float:
        """Custo de exercício (atribuição) por contrato para um dado strike.

        Regra: max(custo_exercicio_pct × valor de venda, custo_exercicio_min)
        mais a taxa fixa custo_exercicio. O valor de venda do ativo no exercício
        é strike × tamanho_contrato (as ações são vendidas pelo strike).
        """
        valor_venda = float(strike) * self.tamanho_contrato
        return (
            max(self.custo_exercicio_pct * valor_venda, self.custo_exercicio_min)
            + self.custo_exercicio
        )

    def preco_custo_para(self, ativo: str) -> float | None:
        """Resolve o preço médio de aquisição de um ativo."""
        pma = self.preco_medio_aquisicao
        if isinstance(pma, dict):
            v = pma.get(ativo)
            return float(v) if v is not None else None
        if isinstance(pma, (int, float)):
            return float(pma)
        return None

    def aplicar_overrides(self, **kwargs: Any) -> Config:
        """Retorna uma nova Config com os campos não-None sobrescritos."""
        atual = {f.name: getattr(self, f.name) for f in fields(self)}
        for chave, valor in kwargs.items():
            if valor is not None and chave in atual:
                atual[chave] = valor
        return Config.from_dict(atual)
