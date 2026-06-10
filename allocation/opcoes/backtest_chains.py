"""Replay do screener sobre cadeias de opções históricas reais.

Diferente de ``opcoes/backtest.py`` (model-based: prêmio estimado por
Black-Scholes), este módulo reexecuta o screener de produção — pipeline +
``rankear_calls``, sem cópia — sobre snapshots EOD reais gravados pelo
``StoreChainsHistoricas``, e liquida cada trade no spot real do vencimento.
É a validação empírica dos parâmetros da config (prob_exerc_max, janela de
dias, distância de strike, custos): retorno realizado, taxa de exercício
realizada vs prevista (calibração) e grid de combinações de parâmetros.

Anti-look-ahead: a série histórica usada pela prob. empírica/vol é truncada
na data do pregão; a IV vem do próprio snapshot; o spot do vencimento é lido
apenas para a liquidação.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from typing import cast

import numpy as np
import pandas as pd

from allocation.config import Config
from allocation.data.chains_historicas import SnapshotChain, StoreChainsHistoricas
from allocation.logging_setup import obter_logger
from allocation.opcoes.calls import rankear_calls
from allocation.opcoes.pipeline import preparar_calls_para_modelo

logger = obter_logger(__name__)

# Spread relativo máximo tolerado nos dados EOD antes do pipeline (bids
# stale/zerados são comuns em snapshots de fechamento).
SPREAD_MAX_QUALIDADE = 1.0

COLUNAS_TRADES = [
    "ativo",
    "data_entrada",
    "expiration",
    "dias_vencimento",
    "S_entrada",
    "strike",
    "bid_entrada",
    "premio_liquido",
    "prob_exercicio_final",
    "prob_exercicio",
    "prob_empirica",
    "score_venda",
    "fonte_vol",
    "exercido",
    "S_vencimento",
    "retorno_cc",
    "retorno_cc_anualizado",
    "retorno_buy_hold",
]


@dataclass
class ResumoReplayChains:
    """Métricas agregadas de um replay do screener sobre chains reais."""

    ativo: str
    n_pregoes_avaliados: int
    n_trades: int
    n_sem_candidata: int
    n_incompletos: int
    retorno_medio_trade: float
    retorno_anualizado: float
    taxa_exercicio_realizada: float
    prob_exercicio_media_prevista: float
    retorno_medio_buy_hold: float
    vol_retorno: float

    def as_dict(self) -> dict:
        return asdict(self)


def _filtrar_qualidade(df: pd.DataFrame, spread_max: float = SPREAD_MAX_QUALIDADE) -> pd.DataFrame:
    """Remove contratos com quotes EOD inutilizáveis antes do pipeline."""
    if df.empty:
        return df
    bid = df["bid"].astype(float)
    ask = df["ask"].astype(float)
    mid = (bid + ask) / 2
    spread_rel = (ask - bid) / mid.where(mid > 0)
    cond = (bid > 0) & (ask > 0) & (ask >= bid) & (spread_rel <= spread_max)
    return df[cond.fillna(False)].copy()


def _normalizar_indice(serie: pd.Series) -> pd.Series:
    """Índice datetime, sem timezone, normalizado e ordenado."""
    s = serie.copy()
    idx = pd.to_datetime(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def _serie_liquidacao(spots_store: pd.Series, historico_precos: pd.Series | None) -> pd.Series:
    """Série de spots para liquidar trades no vencimento.

    Prioridade para o spot dos snapshots (não ajustado, mesma sessão de
    fechamento das opções); o histórico do provedor cobre datas sem snapshot
    (ex.: vencimentos após o fim do store).
    """
    partes = []
    if historico_precos is not None and len(historico_precos) > 0:
        partes.append(_normalizar_indice(historico_precos))
    if len(spots_store) > 0:
        partes.append(_normalizar_indice(spots_store))
    if not partes:
        return pd.Series(dtype=float)
    combinada = pd.concat(partes)
    return combinada[~combinada.index.duplicated(keep="last")].sort_index()


def _rodar_screener_em_snapshot(
    snap: SnapshotChain,
    config: Config,
    historico_truncado: pd.Series | None,
) -> pd.DataFrame:
    """Executa o screener de produção (pipeline + rankear_calls) num snapshot."""
    df_calls = _filtrar_qualidade(snap.df_calls)
    if df_calls.empty:
        return pd.DataFrame()
    df = preparar_calls_para_modelo(
        df_calls=df_calls,
        preco_atual=snap.spot,
        taxa_livre_risco=config.taxa_livre_risco,
        dividend_yield=config.dividend_para(snap.ativo),
        usar_premio=config.usar_premio,
        t_min=config.min_dias,
        t_max=config.max_dias,
        dias_ano=config.dias_ano,
        historico_precos=historico_truncado,
        usar_prob_d2=config.usar_prob_d2,
        usar_prob_empirica=config.usar_prob_empirica,
        min_amostras_empirica=config.min_amostras_empirica,
        liquidez_volume_min=config.liquidez_volume_min,
        liquidez_open_interest_min=config.liquidez_open_interest_min,
        liquidez_spread_max=config.liquidez_spread_max,
        data_referencia=snap.data_pregao,
    )
    if df.empty:
        return df
    return rankear_calls(df, config, snap.spot)


def replay_screener_chains(
    ativo: str,
    store: StoreChainsHistoricas,
    config: Config,
    inicio: str | pd.Timestamp | None = None,
    fim: str | pd.Timestamp | None = None,
    historico_precos: pd.Series | None = None,
    top_n_executar: int = 1,
    passo_dias: int | None = None,
    _snapshots: dict[pd.Timestamp, SnapshotChain] | None = None,
    _spots_store: pd.Series | None = None,
) -> tuple[pd.DataFrame, ResumoReplayChains]:
    """Reexecuta o screener pregão a pregão e liquida os trades no vencimento.

    Em cada data com snapshot, roda o screener real e "vende" as
    ``top_n_executar`` melhores calls ao ``bid`` do dia (prêmio executável,
    independente de ``config.usar_premio``, que segue valendo só para a
    seleção/score). O desfecho usa o spot real na expiração: exercida se
    ``S_T > strike``; retorno do covered call sobre o spot de entrada, com os
    custos da config (custo de exercício integral quando exercida — aqui o
    desfecho é conhecido, sem ponderar por probabilidade).

    Avanço: por padrão "sequencial" — a próxima entrada é o primeiro pregão
    após o vencimento do trade (carteira realista, sem sobreposição).
    ``passo_dias`` fixa o passo em N pregões (amostras sobrepostas, mais
    pontos para estatística/calibração).

    ``historico_precos``: série longa de fechamentos para a prob. empírica e
    fallback de vol; é truncada em cada data de pregão (anti-look-ahead) e
    complementa a liquidação em datas sem snapshot.

    ``_snapshots``/``_spots_store``: caches internos reutilizados pelo grid de
    parâmetros (o I/O dos parquets domina o custo).
    """
    if top_n_executar < 1:
        raise ValueError("top_n_executar deve ser >= 1")
    if passo_dias is not None and passo_dias < 1:
        raise ValueError("passo_dias deve ser >= 1")

    datas = store.datas_disponiveis(ativo, inicio, fim)
    spots_store = _spots_store if _spots_store is not None else store.serie_spot(ativo)
    serie_liq = _serie_liquidacao(spots_store, historico_precos)
    historico = (
        _normalizar_indice(historico_precos)
        if historico_precos is not None and len(historico_precos) > 0
        else None
    )
    snapshots = _snapshots if _snapshots is not None else {}

    trades: list[dict] = []
    n_avaliados = 0
    n_sem_candidata = 0
    n_incompletos = 0
    ultima_data_liq = serie_liq.index.max() if len(serie_liq) else pd.Timestamp.min

    i = 0
    while i < len(datas):
        d = datas[i]
        if d not in snapshots:
            snapshots[d] = store.carregar_snapshot(ativo, d)
        snap = snapshots[d]
        n_avaliados += 1

        hist_d = historico.loc[:d] if historico is not None else None
        df_top = _rodar_screener_em_snapshot(snap, config, hist_d)

        if df_top.empty:
            n_sem_candidata += 1
            i += 1 if passo_dias is None else passo_dias
            continue

        exp_max = d
        executou = False
        for _, row in df_top.head(top_n_executar).iterrows():
            expiracao = pd.Timestamp(row["expiration"]).normalize()
            if expiracao > ultima_data_liq:
                n_incompletos += 1
                continue
            executou = True
            exp_max = max(exp_max, expiracao)

            strike = float(row["strike"])
            bid = float(row["bid"])
            premio_liq = bid - config.custo_venda / config.tamanho_contrato
            s_t = float(cast("float", serie_liq.asof(expiracao)))
            exercido = s_t > strike
            custo_exerc = (
                config.custo_exercicio_para(strike) / config.tamanho_contrato if exercido else 0.0
            )
            retorno_cc = (min(s_t, strike) - snap.spot + premio_liq - custo_exerc) / snap.spot
            dias = int(row["dias_vencimento"])
            trades.append(
                {
                    "ativo": ativo,
                    "data_entrada": d,
                    "expiration": expiracao,
                    "dias_vencimento": dias,
                    "S_entrada": snap.spot,
                    "strike": strike,
                    "bid_entrada": bid,
                    "premio_liquido": premio_liq,
                    "prob_exercicio_final": float(row["prob_exercicio_final"]),
                    "prob_exercicio": float(row.get("prob_exercicio", np.nan)),
                    "prob_empirica": float(row.get("prob_empirica", np.nan)),
                    "score_venda": float(row["score_venda"]),
                    "fonte_vol": row.get("fonte_vol", ""),
                    "exercido": exercido,
                    "S_vencimento": s_t,
                    "retorno_cc": retorno_cc,
                    "retorno_cc_anualizado": retorno_cc * config.dias_ano / dias,
                    "retorno_buy_hold": (s_t - snap.spot) / snap.spot,
                }
            )

        if passo_dias is not None:
            i += passo_dias
        elif executou:
            # sequencial: próxima entrada no primeiro pregão após o vencimento
            i = next(
                (j for j in range(i + 1, len(datas)) if datas[j] > exp_max),
                len(datas),
            )
        else:
            i += 1

    df_trades = pd.DataFrame(trades, columns=COLUNAS_TRADES)
    resumo = ResumoReplayChains(
        ativo=ativo,
        n_pregoes_avaliados=n_avaliados,
        n_trades=len(df_trades),
        n_sem_candidata=n_sem_candidata,
        n_incompletos=n_incompletos,
        retorno_medio_trade=float(df_trades["retorno_cc"].mean()) if len(df_trades) else np.nan,
        retorno_anualizado=(
            float(df_trades["retorno_cc_anualizado"].mean()) if len(df_trades) else np.nan
        ),
        taxa_exercicio_realizada=(
            float(df_trades["exercido"].mean()) if len(df_trades) else np.nan
        ),
        prob_exercicio_media_prevista=(
            float(df_trades["prob_exercicio_final"].mean()) if len(df_trades) else np.nan
        ),
        retorno_medio_buy_hold=(
            float(df_trades["retorno_buy_hold"].mean()) if len(df_trades) else np.nan
        ),
        vol_retorno=float(df_trades["retorno_cc"].std()) if len(df_trades) > 1 else np.nan,
    )
    return df_trades, resumo


def calibracao_probabilidade(df_trades: pd.DataFrame, n_buckets: int = 5) -> pd.DataFrame:
    """Compara probabilidade de exercício prevista vs frequência realizada.

    Agrupa os trades em até ``n_buckets`` faixas (quantis) da probabilidade
    prevista e calcula a frequência de exercício realizada em cada faixa — a
    validação direta do ``prob_exerc_max``: se o modelo prevê 15% e a faixa
    realiza 30%, o limite está calibrado errado.
    """
    if df_trades.empty:
        return pd.DataFrame(
            columns=["faixa_prob", "n_trades", "prob_media_prevista", "freq_exercicio_realizada"]
        )
    df = df_trades.copy()
    q = min(n_buckets, df["prob_exercicio_final"].nunique())
    df["faixa_prob"] = pd.qcut(df["prob_exercicio_final"], q=max(q, 1), duplicates="drop")
    grupos = df.groupby("faixa_prob", observed=True)
    out = pd.DataFrame(
        {
            "n_trades": grupos.size(),
            "prob_media_prevista": grupos["prob_exercicio_final"].mean(),
            "freq_exercicio_realizada": grupos["exercido"].mean(),
        }
    ).reset_index()
    out["faixa_prob"] = out["faixa_prob"].astype(str)
    return out


def validar_parametros_grid(
    ativo: str,
    store: StoreChainsHistoricas,
    config_base: Config,
    grade: dict[str, list],
    inicio: str | pd.Timestamp | None = None,
    fim: str | pd.Timestamp | None = None,
    historico_precos: pd.Series | None = None,
    **kwargs_replay,
) -> pd.DataFrame:
    """Roda o replay para cada combinação de parâmetros da grade.

    ``grade``: ex. ``{"prob_exerc_max": [0.10, 0.25], "max_dias": [20, 45]}``.
    Cada combinação vira ``config_base.aplicar_overrides(**combo)`` (a própria
    Config valida as faixas). Retorna uma linha por combinação: parâmetros +
    métricas do :class:`ResumoReplayChains`. Snapshots e spots são carregados
    uma única vez e compartilhados entre as combinações.
    """
    if not grade:
        raise ValueError("grade de parâmetros vazia")
    campos_config = {f for f in Config.__dataclass_fields__}
    desconhecidos = set(grade) - campos_config
    if desconhecidos:
        raise ValueError(f"Parâmetros desconhecidos na grade: {sorted(desconhecidos)}")

    snapshots: dict[pd.Timestamp, SnapshotChain] = {}
    spots_store = store.serie_spot(ativo)

    chaves = list(grade)
    linhas = []
    for valores in itertools.product(*(grade[k] for k in chaves)):
        combo = dict(zip(chaves, valores, strict=True))
        config = config_base.aplicar_overrides(**combo)
        _, resumo = replay_screener_chains(
            ativo,
            store,
            config,
            inicio=inicio,
            fim=fim,
            historico_precos=historico_precos,
            _snapshots=snapshots,
            _spots_store=spots_store,
            **kwargs_replay,
        )
        linhas.append({**combo, **resumo.as_dict()})
        logger.info("[grid %s] %s -> %d trades", ativo, combo, resumo.n_trades)

    return pd.DataFrame(linhas)
