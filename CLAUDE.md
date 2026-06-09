# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`allocation` is a modular quantitative finance platform. The core module (`opcoes`) screens and ranks covered call opportunities on US equities/ETFs using Black-Scholes d2 (risk-neutral) and empirical (historical frequency) probability models combined with a realistic brokerage cost model.

## Commands

```bash
# Install (editable with dev dependencies)
pip install -e ".[dev]"

# Run the screener
allocation --config config.toml
python3 t1.py                          # legacy alias

# CLI overrides
allocation --config config.toml --ativos IBIT,AAPL --top-n 3
allocation --offline --pasta-mock ./base_mock   # use saved mock data
allocation --config config.toml --salvar-mock --pasta-mock ./base_mock  # save mock

# Subcommands
allocation --config config.toml backtest --distancia 0.05 --dias 14
allocation --offline carteira --arquivo exemplo_carteira.json --saida ./relatorios
allocation --offline puts                              # cash-secured put screener
allocation --offline vol --saida vol.xlsx              # IV term structure, cone, skew
allocation --offline hedge --ativo IBIT --custo-medio 55.0   # protective put + collar
allocation --offline spreads --estrategia bull_call    # or iron_condor

# Tests
python3 -m pytest                      # all tests (use python3 -m pytest, not bare pytest)
python3 -m pytest tests/test_black_scholes.py   # single file
python3 -m pytest -v                   # verbose

# Lint & type-check
ruff check .
ruff format .
mypy allocation
```

## Architecture

Strict layered dependency — no upward imports:

```
CLI (cli.py)
  └─ Config (config.py)               — validated TOML dataclass, all runtime params
  └─ Runner (runner.py)               — outer loop: per-asset orchestration
       └─ Data Layer (data/)          — ProvedorDados protocol, swappable yfinance ↔ mock
       └─ opcoes/pipeline.py          — vectorized batch computation of 30+ metrics
       └─ opcoes/calls.py             — filter chain → scoring → top-N
       └─ report.py                   — Excel + payoff graph generation
       └─ risco/portfolio.py          — multi-client covered_call/roll/buy-write analysis
       └─ opcoes/backtest.py          — historical strategy simulation
```

### Module layout

```
allocation/
├── opcoes/           — everything that uses option chains + Black-Scholes
│   ├── calls.py      — covered call ranking (core, formerly ranking.py)
│   ├── pipeline.py   — vectorized 30+ metric batch (formerly models/pipeline.py)
│   ├── backtest.py   — historical covered call simulation
│   ├── puts.py       — cash-secured put selling (mirror of calls; return on collateral)
│   ├── spreads.py    — multi-leg: bull call spread, iron condor
│   ├── volatilidade.py — IV term structure, realized-vol cone/rank, skew by moneyness
│   └── hedge.py      — protective put and collar analysis
├── acoes/
│   └── screening.py  — fundamentals + momentum stock screening [stub]
├── risco/
│   ├── portfolio.py  — multi-client analysis (formerly portfolio.py)
│   ├── analytics.py  — Greeks aggregation, VaR, drawdown, stress test [stub]
│   ├── montecarlo.py — GBM portfolio simulation [stub]
│   └── crises.py     — replay against historical crises [stub]
├── data/             — shared: ProvedorDados protocol, yfinance, mock, cache, retry
├── models/           — shared pure math: black_scholes, empirical, greeks, volatility, payoff
├── config.py         — validated TOML dataclass
├── runner.py         — orchestrator
├── report.py         — Excel + chart output
└── cli.py            — argument parsing, subcommand routing
```

**Data abstraction:** `data/base.py` defines `ProvedorDados` (protocol) and `DadosMercado` (container, with `df_calls` and `df_puts`). `ProvedorYFinance` (online, disk-cached) and `ProvedorMock` (CSV/JSON files) are interchangeable — no model or ranking code touches the provider directly. Mock folders without a `mock_{ativo}_puts.csv` degrade gracefully (empty `df_puts` + warning).

**Pipeline:** `opcoes/pipeline.py:preparar_opcoes_para_modelo()` is the core — a single-pass vectorized function that computes all 30+ per-option metrics for calls or puts (`tipo="call"|"put"`); `preparar_calls_para_modelo`/`preparar_puts_para_modelo` are thin wrappers. Adding a new metric belongs here.

**Per-leg premium convention (hedge/spreads):** bought legs are priced at `ask`, sold legs at `bid` (conservative), regardless of the screener's `config.usar_premio`.

**Probability model:** Final probability = `max(prob_d2, prob_empirica)` (conservative worst-case). d2 from Black-Scholes in `models/black_scholes.py`; empirical from non-overlapping historical windows in `models/empirical.py`.

**Scoring:** `score_venda = retorno_se_exercido_anualizado × (1 - prob_exercicio_final) × (1 + peso_theta × theta_eff) / (1 + peso_vega × vega_risk)` — rewards if-called return and theta yield, penalizes assignment risk and vega exposure. `peso_theta` and `peso_vega` default to 0 in config (pure return × probability mode).

**Cost model:** Net premium = `premium - sell_cost - (exercise_cost × prob_final)`, where exercise cost = `max(0.25% × strike × 100, $10)`.

## Key Conventions

**Language:** Portuguese naming throughout — variables, function names, column names, and TOML keys are in Portuguese (e.g., `ativo`, `premio`, `taxa_livre_risco`, `prob_exerc_max`). Follow this convention when adding anything.

**Volatility fallback:** IV from yfinance is preferred; if unavailable, realized historical vol is used and `fonte_vol` is set to `"historica"` vs `"implicita"`.

**Filter order in `opcoes/calls.py`:** Liquidity → probability cap → strike distance → net return above `min_retorno_anualizado_liquido` → profit-if-exercised above `min_lucro_se_exercido` (both default 0.0 = strictly positive). Rejected options are kept in the full matrix with a `status` column explaining rejection reason.

**Time convention:** `T` and all annualizations use calendar days over `dias_ano` (ACT/365 by default; set `dias_ano = 252` for a trading-day base). The empirical probability uses business days (`np.busday_count`), consistent with the price history being trading sessions — these are intentionally distinct domains.

**Mock data:** `base_mock/` contains pre-downloaded CSV/JSON for 23 tickers used in offline mode and tests. Tests use fixtures from `tests/conftest.py` pointing to this directory. `mock_IBIT_puts.csv` is *synthetic* (derived from the calls CSV via put-call parity, ignores American early exercise) — regenerate with real data via `--salvar-mock` when online.

**Config:** `config.toml` is the user-facing config. Per-asset overrides for dividend yield and cost basis use TOML tables:
```toml
[dividend_yield]
AAPL = 0.005

[preco_medio_aquisicao]
IBIT = 55.00
```

**Outputs:** The screener writes `top_opcoes_covered_call.xlsx` (ranked results) and `matriz_opcoes.xlsx` (full matrix with rejection reasons); the puts screener writes `top_opcoes_puts.xlsx`/`matriz_opcoes_puts.xlsx`. Portfolio analysis writes one Excel per client with three sheets: `covered_call`, `rolagem`, `buy_write`. `vol`/`hedge`/`spreads` save Excel only when `--saida` is given.

**Running tests:** Always use `python3 -m pytest` (not bare `pytest`) to ensure the correct Python environment picks up the installed package.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main` and all PRs: `ruff check` → `mypy allocation` → `pytest`, on Python 3.11 and 3.12.
