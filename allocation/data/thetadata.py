"""Ingestão de chains de opções EOD históricas via Theta Data.

Fala com o ThetaTerminal local (REST, ``http://127.0.0.1:25510``) — o usuário
precisa estar com o terminal aberto e logado; o tier gratuito cobre 1 ano de
EOD de opções US. Os endpoints *bulk* retornam todos os strikes × pregões de
uma expiration por request, então o nº de requests ≈ nº de expirations (×2,
com open interest), não dias × strikes — importante com o limite de 20
req/min do tier gratuito.

A saída é normalizada para o schema do ``StoreChainsHistoricas`` (superset do
mock CSV) e particionada em um parquet por pregão. IV não vem do EOD (tier
pago) e fica NaN — o pipeline já cai para a vol realizada (``fonte_vol =
"historica"``).

Spot: preferimos o EOD de ações do próprio Theta (preço **não ajustado**, da
mesma sessão de fechamento das opções — strikes referem-se a preços não
ajustados). Fallback: yfinance com ``auto_adjust=False``. A série *ajustada*
do provedor normal continua correta para a prob. empírica (retornos), mas não
para comparar spot × strike.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import pandas as pd

from allocation.data.chains_historicas import StoreChainsHistoricas
from allocation.logging_setup import obter_logger

logger = obter_logger(__name__)

URL_THETATERMINAL = "http://127.0.0.1:25510"


def _aaaammdd(data: str | pd.Timestamp) -> str:
    return pd.Timestamp(data).strftime("%Y%m%d")


def _data_iso(aaaammdd: int | str) -> str:
    return pd.Timestamp(str(aaaammdd)).date().isoformat()


class ClienteThetaData:
    """Cliente REST mínimo do ThetaTerminal, com rate limit embutido."""

    def __init__(
        self,
        base_url: str = URL_THETATERMINAL,
        max_req_por_min: int = 20,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._intervalo = 60.0 / max_req_por_min
        self._ultima_req = 0.0
        self._timeout = timeout

    def _get(self, caminho: str, **params: str) -> dict:
        espera = self._intervalo - (time.monotonic() - self._ultima_req)
        if espera > 0:
            time.sleep(espera)
        url = f"{self.base_url}{caminho}?{urllib.parse.urlencode(params)}"
        self._ultima_req = time.monotonic()
        with urllib.request.urlopen(url, timeout=self._timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read())
        erro = (payload.get("header") or {}).get("error_type")
        if erro and erro not in ("null", "NO_DATA"):
            raise RuntimeError(f"Theta Data {caminho}: {erro}")
        return payload

    def listar_expiracoes(self, ativo: str) -> list[str]:
        """Expirations listadas para o subjacente, como datas ISO ordenadas."""
        payload = self._get("/v2/list/expirations", root=ativo)
        return sorted(_data_iso(e) for e in payload.get("response") or [])

    def eod_chain_bulk(self, ativo: str, expiration: str, start_date: str, end_date: str) -> dict:
        """EOD de todos os strikes de uma expiration no intervalo (payload cru)."""
        return self._get(
            "/v2/bulk_hist/option/eod",
            root=ativo,
            exp=_aaaammdd(expiration),
            start_date=_aaaammdd(start_date),
            end_date=_aaaammdd(end_date),
        )

    def open_interest_bulk(
        self, ativo: str, expiration: str, start_date: str, end_date: str
    ) -> dict:
        """Open interest diário de todos os strikes de uma expiration."""
        return self._get(
            "/v2/bulk_hist/option/open_interest",
            root=ativo,
            exp=_aaaammdd(expiration),
            start_date=_aaaammdd(start_date),
            end_date=_aaaammdd(end_date),
        )

    def eod_stock(self, ativo: str, start_date: str, end_date: str) -> pd.Series:
        """Fechamentos EOD (não ajustados) do subjacente, índice = data ISO."""
        payload = self._get(
            "/v2/hist/stock/eod",
            root=ativo,
            start_date=_aaaammdd(start_date),
            end_date=_aaaammdd(end_date),
        )
        formato = (payload.get("header") or {}).get("format") or []
        valores = {}
        for tick in payload.get("response") or []:
            linha = dict(zip(formato, tick, strict=False))
            valores[pd.Timestamp(_data_iso(linha["date"]))] = float(linha["close"])
        return pd.Series(valores, dtype=float).sort_index()


def _simbolo_occ(ativo: str, expiration: str, tipo: str, strike: float) -> str:
    """Identificador OCC: ROOT + AAMMDD + C/P + strike×1000 em 8 dígitos."""
    data = pd.Timestamp(expiration).strftime("%y%m%d")
    return f"{ativo}{data}{tipo[0].upper()}{int(round(strike * 1000)):08d}"


def _normalizar_chain_theta(payload: dict, ativo: str) -> pd.DataFrame:
    """Converte o payload bulk EOD do Theta para o schema do store.

    Cada item de ``response`` traz um contrato (``contract``: root, expiration,
    strike em milésimos de dólar, right C/P) e seus ``ticks`` diários, cujos
    campos são nomeados por ``header.format`` — o mapeamento é feito por nome,
    não por posição. IV fica NaN (EOD não traz; fallback de vol no pipeline) e
    ``openInterest`` 0 até o merge com o endpoint próprio.
    """
    formato = (payload.get("header") or {}).get("format") or []
    linhas = []
    for item in payload.get("response") or []:
        contrato = item.get("contract") or {}
        strike = float(contrato["strike"]) / 1000.0
        tipo = "CALL" if str(contrato.get("right", "C")).upper().startswith("C") else "PUT"
        expiration = _data_iso(contrato["expiration"])
        for tick in item.get("ticks") or []:
            campos = dict(zip(formato, tick, strict=False))
            bid = float(campos.get("bid", 0.0) or 0.0)
            ask = float(campos.get("ask", 0.0) or 0.0)
            linhas.append(
                {
                    "contractSymbol": _simbolo_occ(ativo, expiration, tipo, strike),
                    "strike": strike,
                    "lastPrice": float(campos.get("close", 0.0) or 0.0),
                    "bid": bid,
                    "ask": ask,
                    "volume": int(campos.get("volume", 0) or 0),
                    "openInterest": 0,
                    "impliedVolatility": float("nan"),
                    "expiration": expiration,
                    "type": tipo,
                    "data_pregao": _data_iso(campos["date"]),
                }
            )
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df["spread_pct"] = (df["ask"] - df["bid"]) / df["mid"].where(df["mid"] > 0)
    return df


def _normalizar_oi_theta(payload: dict) -> pd.DataFrame:
    """Extrai (expiration, strike, type, data_pregao) → openInterest do bulk OI."""
    formato = (payload.get("header") or {}).get("format") or []
    linhas = []
    for item in payload.get("response") or []:
        contrato = item.get("contract") or {}
        strike = float(contrato["strike"]) / 1000.0
        tipo = "CALL" if str(contrato.get("right", "C")).upper().startswith("C") else "PUT"
        expiration = _data_iso(contrato["expiration"])
        for tick in item.get("ticks") or []:
            campos = dict(zip(formato, tick, strict=False))
            linhas.append(
                {
                    "expiration": expiration,
                    "strike": strike,
                    "type": tipo,
                    "data_pregao": _data_iso(campos["date"]),
                    "openInterest": int(campos.get("open_interest", 0) or 0),
                }
            )
    return pd.DataFrame(linhas)


def _spot_yfinance(ativo: str, inicio: str, fim: str) -> pd.Series:
    """Fallback de spot: fechamentos NÃO ajustados do yfinance."""
    import yfinance as yf

    df = yf.download(
        ativo,
        start=inicio,
        end=pd.Timestamp(fim) + pd.Timedelta(days=1),
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # colunas multi-nível p/ 1 ticker
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.astype(float)


def baixar_chains_historicas(
    ativo: str,
    inicio: str,
    fim: str,
    store: StoreChainsHistoricas,
    cliente: ClienteThetaData | None = None,
    sobrescrever: bool = False,
    margem_vencimento_dias: int = 60,
) -> int:
    """Baixa as chains EOD do intervalo e grava um snapshot parquet por pregão.

    Considera expirations entre ``inicio`` e ``fim + margem_vencimento_dias``
    (vencimentos além do fim ainda são visíveis — e negociáveis — dentro da
    janela). Dias que já têm snapshot são pulados na gravação (idempotente);
    use ``sobrescrever=True`` para regravar. Retorna o nº de snapshots gravados.
    """
    cliente = cliente or ClienteThetaData()

    t0, t1 = pd.Timestamp(inicio), pd.Timestamp(fim)
    expiracoes = [
        e
        for e in cliente.listar_expiracoes(ativo)
        if t0 <= pd.Timestamp(e) <= t1 + pd.Timedelta(days=margem_vencimento_dias)
    ]
    if not expiracoes:
        logger.warning("[%s] Nenhuma expiration entre %s e %s.", ativo, inicio, fim)
        return 0
    logger.info(
        "[%s] %d expirations no intervalo (~%d requests de chain + OI).",
        ativo,
        len(expiracoes),
        2 * len(expiracoes),
    )

    frames = []
    for n, expiration in enumerate(expiracoes, start=1):
        logger.info("[%s] (%d/%d) expiration %s...", ativo, n, len(expiracoes), expiration)
        df = _normalizar_chain_theta(cliente.eod_chain_bulk(ativo, expiration, inicio, fim), ativo)
        if df.empty:
            continue
        df_oi = _normalizar_oi_theta(cliente.open_interest_bulk(ativo, expiration, inicio, fim))
        if not df_oi.empty:
            df = df.drop(columns=["openInterest"]).merge(
                df_oi, on=["expiration", "strike", "type", "data_pregao"], how="left"
            )
            df["openInterest"] = df["openInterest"].fillna(0).astype(int)
        frames.append(df)

    if not frames:
        logger.warning("[%s] Nenhum dado de opções retornado pelo Theta.", ativo)
        return 0
    todas = pd.concat(frames, ignore_index=True)

    spots = cliente.eod_stock(ativo, inicio, fim)
    if spots.empty:
        logger.warning("[%s] Sem EOD de ações no Theta; usando yfinance (não ajustado).", ativo)
        spots = _spot_yfinance(ativo, inicio, fim)

    gravados = 0
    for chave, grupo in todas.groupby("data_pregao"):
        data_pregao = str(chave)
        if not sobrescrever and store.tem_snapshot(ativo, data_pregao):
            continue
        spot = spots.get(pd.Timestamp(data_pregao))
        if spot is None or not float(spot) > 0:
            logger.warning("[%s] Sem spot para %s — snapshot pulado.", ativo, data_pregao)
            continue
        df_dia = grupo.copy()
        ehcall = df_dia["type"] == "CALL"
        df_dia["inTheMoney"] = (df_dia["strike"] < float(spot)).where(
            ehcall, df_dia["strike"] > float(spot)
        )
        store.salvar_snapshot(ativo, data_pregao, df_dia, spot=float(spot))
        gravados += 1

    logger.info(
        "[%s] %d snapshots gravados (%d pregões no retorno).",
        ativo,
        gravados,
        todas["data_pregao"].nunique(),
    )
    return gravados
