"""Análise de carteira de um cliente: covered call, rolagem e buy-write.

Esta é a segunda função do projeto. Enquanto o *screener* (``runner.executar``)
varre um universo de ativos de forma agnóstica de posição, aqui cruzamos a
saída do screener com a **posição atual de um cliente** (carregada de um JSON)
e produzimos três frentes de recomendação:

1. **Covered call** — vende calls sobre ações detidas que ainda estão
   descobertas (sem call vendida correspondente);
2. **Rolagem** — recompra e reabre calls já vendidas cujo prêmio restante
   ficou baixo (a maior parte do crédito já foi capturada);
3. **Buy-write** — ranqueia oportunidades em ativos que o cliente **não**
   detém (montar ação + call simultaneamente).

O módulo reutiliza ao máximo o screener e os modelos existentes; não duplica
lógica de precificação nem de ranking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from allocation.config import Config
from allocation.data.base import DadosMercado, ProvedorDados
from allocation.logging_setup import obter_logger
from allocation.models.black_scholes import preco_call_bs
from allocation.opcoes.pipeline import preparar_calls_para_modelo
from allocation.models.volatility import volatilidade_realizada
from allocation.opcoes.calls import processar_ativo
from allocation.runner import construir_provedor, executar

logger = obter_logger(__name__)


# --------------------------------------------------------------------------- #
# Modelo de dados                                                             #
# --------------------------------------------------------------------------- #
@dataclass
class PosicaoAcao:
    """Ações detidas pelo cliente."""

    ativo: str
    quantidade: int
    preco_medio: float


@dataclass
class CallVendida:
    """Covered call já aberta (posição vendida em opção)."""

    ativo: str
    strike: float
    expiration: str  # YYYY-MM-DD
    premio_recebido: float  # por ação
    contratos: int


@dataclass
class Carteira:
    """Posição completa de um cliente, incluindo preferências de análise.

    Os parâmetros de análise (limiar_premio_restante, rolagem_*,
    permitir_strike_abaixo_custo) são opcionais no JSON e têm defaults
    conservadores. O config.toml cobre apenas o screener (universo, modelos,
    mercado); o que é por-cliente fica aqui.
    """

    posicoes: list[PosicaoAcao] = field(default_factory=list)
    calls_vendidas: list[CallVendida] = field(default_factory=list)
    caixa: float | None = None
    cliente: str | None = None
    # parâmetros de análise de carteira (por cliente)
    limiar_premio_restante: float = 0.20
    rolagem_min_dias: int = 21
    rolagem_max_dias: int = 60
    permitir_strike_abaixo_custo: bool = False

    def ativos_detidos(self) -> set[str]:
        return {p.ativo for p in self.posicoes}

    def preco_medio_de(self, ativo: str) -> float | None:
        for p in self.posicoes:
            if p.ativo == ativo:
                return p.preco_medio
        return None


@dataclass
class RelatorioCarteira:
    """Resultado da análise, com uma tabela por frente de recomendação."""

    covered_call: pd.DataFrame
    rolagem: pd.DataFrame
    buy_write: pd.DataFrame
    cliente: str | None = None


# --------------------------------------------------------------------------- #
# Carregamento do JSON                                                        #
# --------------------------------------------------------------------------- #
def carregar_carteira(caminho: str | Path) -> Carteira:
    """Lê e valida uma carteira de cliente (objeto JSON único).

    Para arquivos com múltiplos clientes (array JSON), use ``carregar_carteiras``.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de carteira não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as f:
        dados: Any = json.load(f)

    if not isinstance(dados, dict):
        raise ValueError("O JSON da carteira deve ser um objeto.")
    return _parse_carteira(dados)


def carregar_carteiras(caminho: str | Path) -> list[Carteira]:
    """Lê um arquivo JSON com um ou vários clientes; sempre retorna uma lista.

    Aceita dois formatos:
    - **objeto único**: ``{"cliente": "Fulano", ...}`` → lista de um elemento;
    - **array de clientes**: ``[{"cliente": "A", ...}, {"cliente": "B", ...}]``.
    """
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de carteira não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as f:
        dados: Any = json.load(f)

    if isinstance(dados, dict):
        return [_parse_carteira(dados)]
    if isinstance(dados, list):
        if not dados:
            raise ValueError("O array de carteiras está vazio.")
        return [_parse_carteira(item) for item in dados]
    raise ValueError("O JSON da carteira deve ser um objeto ou um array de objetos.")


def _parse_carteira(dados: dict[str, Any]) -> Carteira:
    """Valida e converte um único objeto-cliente em ``Carteira``."""
    if not isinstance(dados, dict):
        raise ValueError("Cada cliente do JSON deve ser um objeto.")

    posicoes = [_parse_posicao(p) for p in dados.get("posicoes", [])]
    calls = [_parse_call(c) for c in dados.get("calls_vendidas", [])]

    caixa = dados.get("caixa")
    if caixa is not None and not isinstance(caixa, (int, float)):
        raise ValueError("caixa deve ser numérico.")

    limiar = dados.get("limiar_premio_restante", 0.20)
    rol_min = dados.get("rolagem_min_dias", 21)
    rol_max = dados.get("rolagem_max_dias", 60)
    perm = dados.get("permitir_strike_abaixo_custo", False)

    if not isinstance(limiar, (int, float)) or not (0.0 <= float(limiar) <= 1.0):
        raise ValueError("limiar_premio_restante deve ser um número em [0, 1].")
    if not isinstance(rol_min, int) or not isinstance(rol_max, int) or rol_min < 0 or rol_max < rol_min:
        raise ValueError("rolagem_min_dias/rolagem_max_dias inválidos.")

    return Carteira(
        posicoes=posicoes,
        calls_vendidas=calls,
        caixa=float(caixa) if caixa is not None else None,
        cliente=dados.get("cliente"),
        limiar_premio_restante=float(limiar),
        rolagem_min_dias=int(rol_min),
        rolagem_max_dias=int(rol_max),
        permitir_strike_abaixo_custo=bool(perm),
    )


def _parse_posicao(p: dict[str, Any]) -> PosicaoAcao:
    for campo in ("ativo", "quantidade", "preco_medio"):
        if campo not in p:
            raise ValueError(f"posição sem campo obrigatório '{campo}': {p}")
    if int(p["quantidade"]) <= 0:
        raise ValueError(f"quantidade deve ser > 0 na posição: {p}")
    if float(p["preco_medio"]) <= 0:
        raise ValueError(f"preco_medio deve ser > 0 na posição: {p}")
    return PosicaoAcao(
        ativo=str(p["ativo"]),
        quantidade=int(p["quantidade"]),
        preco_medio=float(p["preco_medio"]),
    )


def _parse_call(c: dict[str, Any]) -> CallVendida:
    for campo in ("ativo", "strike", "expiration", "premio_recebido", "contratos"):
        if campo not in c:
            raise ValueError(f"call_vendida sem campo obrigatório '{campo}': {c}")
    if int(c["contratos"]) <= 0:
        raise ValueError(f"contratos deve ser > 0 na call: {c}")
    if float(c["premio_recebido"]) <= 0:
        raise ValueError(f"premio_recebido deve ser > 0 na call: {c}")
    return CallVendida(
        ativo=str(c["ativo"]),
        strike=float(c["strike"]),
        expiration=str(c["expiration"]),
        premio_recebido=float(c["premio_recebido"]),
        contratos=int(c["contratos"]),
    )


# --------------------------------------------------------------------------- #
# Análise principal                                                           #
# --------------------------------------------------------------------------- #
def avaliar_carteira(
    carteira: Carteira,
    config: Config,
    provedor: ProvedorDados | None = None,
) -> RelatorioCarteira:
    """Avalia a carteira nas três frentes e retorna um RelatorioCarteira."""
    if provedor is None:
        provedor = construir_provedor(config)

    return RelatorioCarteira(
        covered_call=_analisar_covered_call(carteira, config, provedor),
        rolagem=_analisar_rolagem(carteira, config, provedor),
        buy_write=_analisar_buy_write(carteira, config, provedor),
        cliente=carteira.cliente,
    )


def avaliar_carteiras(
    carteiras: list[Carteira],
    config: Config,
    provedor: ProvedorDados | None = None,
) -> list[RelatorioCarteira]:
    """Avalia vários clientes, reutilizando o mesmo provedor (e seu cache)."""
    if provedor is None:
        provedor = construir_provedor(config)
    return [avaliar_carteira(c, config, provedor) for c in carteiras]


def _analisar_covered_call(
    carteira: Carteira, config: Config, provedor: ProvedorDados
) -> pd.DataFrame:
    """Sugere venda de calls sobre ações detidas ainda descobertas."""
    cobertos: dict[str, int] = {}
    for c in carteira.calls_vendidas:
        cobertos[c.ativo] = cobertos.get(c.ativo, 0) + c.contratos

    linhas: list[pd.DataFrame] = []
    for pos in carteira.posicoes:
        possiveis = pos.quantidade // config.tamanho_contrato
        descobertos = possiveis - cobertos.get(pos.ativo, 0)
        if descobertos <= 0:
            logger.info("[%s] Posição totalmente coberta (ou < 1 contrato).", pos.ativo)
            continue

        df = processar_ativo(
            pos.ativo, provedor, config, preco_custo=pos.preco_medio,
            excluir_prejuizo_exercicio=not carteira.permitir_strike_abaixo_custo,
        )
        if df.empty:
            continue

        if not carteira.permitir_strike_abaixo_custo:
            df = df[df["strike"] >= pos.preco_medio].copy()
            if df.empty:
                logger.info(
                    "[%s] Nenhum strike >= custo (%.2f); nada a sugerir.",
                    pos.ativo, pos.preco_medio,
                )
                continue

        df["contratos_sugeridos"] = descobertos
        linhas.append(df)

    if not linhas:
        return pd.DataFrame()
    return pd.concat(linhas, ignore_index=True)


def _analisar_rolagem(
    carteira: Carteira, config: Config, provedor: ProvedorDados
) -> pd.DataFrame:
    """Avalia cada call vendida: rolar (prêmio restante baixo) ou manter."""
    linhas: list[dict[str, Any]] = []
    for call in carteira.calls_vendidas:
        try:
            dados = provedor.obter(call.ativo, config.periodo_historico)
        except Exception as exc:  # noqa: BLE001 — isola falha por ativo
            logger.error("[%s] Erro ao obter dados para rolagem: %s", call.ativo, exc)
            continue

        dias_ate_venc = (
            pd.Timestamp(call.expiration).normalize()
            - pd.Timestamp.today().normalize()
        ).days
        valor_atual = _valor_recompra(call, dados, config, dias_ate_venc)
        premio_restante_pct = (
            valor_atual / call.premio_recebido if call.premio_recebido > 0 else float("nan")
        )

        linha: dict[str, Any] = {
            "ativo": call.ativo,
            "strike_atual": call.strike,
            "venc_atual": call.expiration,
            "contratos": call.contratos,
            "premio_recebido": call.premio_recebido,
            "valor_recompra": round(valor_atual, 4),
            "premio_restante_pct": round(premio_restante_pct, 4),
            "dias_ate_venc": dias_ate_venc,
        }

        candidata = (
            premio_restante_pct == premio_restante_pct  # not NaN
            and premio_restante_pct <= carteira.limiar_premio_restante
        )
        if candidata:
            preco_medio = carteira.preco_medio_de(call.ativo)
            alvo = _melhor_roll(
                call, dados, config, valor_atual, preco_medio,
                carteira.rolagem_min_dias, carteira.rolagem_max_dias,
            )
            if alvo is None:
                linha["acao"] = "rolar (sem alvo na janela)"
            else:
                linha.update(alvo)
                linha["acao"] = "rolar"
        else:
            linha["acao"] = "manter"

        linhas.append(linha)

    return pd.DataFrame(linhas)


def _valor_recompra(
    call: CallVendida, dados: DadosMercado, config: Config, dias_ate_venc: int
) -> float:
    """Custo de recompra (buy-back) da call vendida.

    Usa o mid real da cadeia quando o contrato (mesmo strike+vencimento) existe;
    caso contrário, estima por Black-Scholes com a vol realizada. Se já venceu,
    usa o valor intrínseco.
    """
    chain = dados.df_calls
    match = chain[
        (chain["strike"] == call.strike) & (chain["expiration"] == call.expiration)
    ]
    if not match.empty:
        row = match.iloc[0]
        bid, ask = row.get("bid"), row.get("ask")
        if pd.notna(bid) and pd.notna(ask) and bid > 0 and ask > 0:
            return float((bid + ask) / 2)
        last = row.get("lastPrice")
        if pd.notna(last) and last > 0:
            return float(last)

    if dias_ate_venc <= 0:
        return float(max(dados.preco_atual - call.strike, 0.0))

    vol = volatilidade_realizada(dados.historico_precos)
    valor = preco_call_bs(
        dados.preco_atual,
        call.strike,
        dias_ate_venc / config.dias_ano,
        config.taxa_livre_risco,
        config.dividend_para(call.ativo),
        vol,
    )
    return float(valor) if valor == valor else 0.0  # valor==valor descarta NaN


def _melhor_roll(
    call: CallVendida,
    dados: DadosMercado,
    config: Config,
    valor_recompra: float,
    preco_medio: float | None,
    rolagem_min_dias: int,
    rolagem_max_dias: int,
) -> dict[str, Any] | None:
    """Encontra o melhor vencimento-alvo para o roll-out (maior crédito líquido)."""
    historico = dados.historico_precos if config.usar_prob_empirica else None
    df = preparar_calls_para_modelo(
        df_calls=dados.df_calls,
        preco_atual=dados.preco_atual,
        taxa_livre_risco=config.taxa_livre_risco,
        dividend_yield=config.dividend_para(call.ativo),
        usar_premio=config.usar_premio,
        t_min=rolagem_min_dias,
        t_max=rolagem_max_dias,
        dias_ano=config.dias_ano,
        historico_precos=historico,
        usar_prob_d2=config.usar_prob_d2,
        usar_prob_empirica=config.usar_prob_empirica,
        min_amostras_empirica=config.min_amostras_empirica,
    )
    if df.empty:
        return None

    venc_atual = pd.Timestamp(call.expiration)
    piso_strike = max(call.strike, preco_medio or 0.0)
    # liquidez voltou a ser flag (não é mais descartada no provedor): exige
    # passou_liquidez aqui, como o ranking principal faz, para não sugerir roll
    # em opções ilíquidas. Mocks sem a coluna são tratados como líquidos.
    passou_liquidez = (
        df["passou_liquidez"]
        if "passou_liquidez" in df.columns
        else pd.Series(True, index=df.index)
    )
    cand = df[
        passou_liquidez
        & (pd.to_datetime(df["expiration"]) > venc_atual)
        & (df["strike"] >= piso_strike)
        & (df["prob_exercicio_final"] <= config.prob_exerc_max)
        & (df["premio"] > 0)
    ].copy()
    if cand.empty:
        return None

    cand["credito_liquido"] = cand["premio"] - valor_recompra
    melhor = cand.sort_values("credito_liquido", ascending=False).iloc[0]
    return {
        "strike_novo": float(melhor["strike"]),
        "venc_novo": str(pd.Timestamp(melhor["expiration"]).date()),
        "premio_novo": round(float(melhor["premio"]), 4),
        "credito_liquido": round(float(melhor["credito_liquido"]), 4),
        "prob_exercicio_final_nova": round(float(melhor["prob_exercicio_final"]), 4),
    }


def _analisar_buy_write(
    carteira: Carteira, config: Config, provedor: ProvedorDados
) -> pd.DataFrame:
    """Ranqueia buy-write em ativos não detidos pelo cliente (sem limite de caixa)."""
    detidos = carteira.ativos_detidos()
    universo = [a for a in config.lista_ativos if a not in detidos]
    if not universo:
        logger.info("Nenhum ativo não-detido no universo para buy-write.")
        return pd.DataFrame()

    df = executar(config.aplicar_overrides(lista_ativos=universo), provedor)
    if df.empty:
        return df

    df = df.sort_values("score_venda", ascending=False).reset_index(drop=True).copy()
    df["capital_por_contrato"] = df["preco_atual_ativo"] * config.tamanho_contrato
    df["ranking_global"] = range(1, len(df) + 1)
    return df


# --------------------------------------------------------------------------- #
# Relatório                                                                   #
# --------------------------------------------------------------------------- #
_COLS_COVERED = [
    "ativo", "contratos_sugeridos", "ranking_ativo", "strike", "premio",
    "expiration", "dias_uteis_ate_vencimento", "prob_exercicio_final",
    "delta", "retorno_anualizado_liquido", "retorno_sobre_custo",
    "capital_por_contrato", "custo_exercicio_contrato", "lucro_se_exercido",
    "alerta_abaixo_custo", "score_venda",
]
_COLS_ROLAGEM = [
    "ativo", "acao", "strike_atual", "venc_atual", "contratos", "premio_recebido",
    "valor_recompra", "premio_restante_pct", "dias_ate_venc",
    "strike_novo", "venc_novo", "premio_novo", "credito_liquido",
    "prob_exercicio_final_nova",
]
_COLS_BUYWRITE = [
    "ranking_global", "ativo", "strike", "premio", "expiration",
    "dias_uteis_ate_vencimento", "prob_exercicio_final", "delta",
    "retorno_anualizado_liquido", "preco_atual_ativo", "capital_por_contrato",
    "custo_exercicio_contrato", "lucro_se_exercido", "score_venda",
]


def _selecionar(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    return df[[c for c in colunas if c in df.columns]].copy()


def reportar_carteira(relatorio: RelatorioCarteira, caminho_xlsx: str) -> str:
    """Imprime o resumo no terminal e salva um Excel com três abas."""
    secoes = [
        ("COVERED CALL (ações descobertas)", relatorio.covered_call, _COLS_COVERED),
        ("ROLAGEM (calls vendidas)", relatorio.rolagem, _COLS_ROLAGEM),
        ("BUY-WRITE (ativos não detidos)", relatorio.buy_write, _COLS_BUYWRITE),
    ]

    titulo = f"ANÁLISE DE CARTEIRA — {relatorio.cliente}" if relatorio.cliente else "ANÁLISE DE CARTEIRA"
    print("\n" + "=" * 80)
    print(titulo)
    print("=" * 80)
    for nome, df, cols in secoes:
        print(f"\n## {nome}")
        sel = _selecionar(df, cols)
        if sel.empty:
            print("  (sem sugestões)")
        else:
            print(sel.to_string(index=False))

    with pd.ExcelWriter(caminho_xlsx) as writer:
        for aba, df, cols in [
            ("covered_call", relatorio.covered_call, _COLS_COVERED),
            ("rolagem", relatorio.rolagem, _COLS_ROLAGEM),
            ("buy_write", relatorio.buy_write, _COLS_BUYWRITE),
        ]:
            sel = _selecionar(df, cols)
            (sel if not sel.empty else pd.DataFrame(columns=cols)).to_excel(
                writer, sheet_name=aba, index=False
            )

    logger.info("Análise de carteira salva em: %s", caminho_xlsx)
    return caminho_xlsx


def _slug_cliente(cliente: str | None, indice: int) -> str:
    """Nome de arquivo seguro a partir do nome do cliente."""
    if not cliente:
        return f"cliente_{indice + 1}"
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in cliente.strip())
    return seguro.strip("_") or f"cliente_{indice + 1}"


def reportar_carteiras(
    relatorios: list[RelatorioCarteira], pasta_saida: str | Path = "."
) -> list[str]:
    """Gera um Excel por cliente em ``pasta_saida`` (``analise_<cliente>.xlsx``).

    Imprime o resumo de cada cliente no terminal e retorna os caminhos gerados.
    """
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)

    caminhos: list[str] = []
    usados: set[str] = set()
    for i, rel in enumerate(relatorios):
        slug = _slug_cliente(rel.cliente, i)
        # desambigua usando o conjunto de slugs já emitidos (incluindo sufixos),
        # evitando colisão quando um cliente tem nome natural igual a um sufixo gerado
        if slug in usados:
            n = 2
            while f"{slug}_{n}" in usados:
                n += 1
            slug = f"{slug}_{n}"
        usados.add(slug)
        caminho = str(pasta / f"analise_{slug}.xlsx")
        caminhos.append(reportar_carteira(rel, caminho))
    return caminhos
