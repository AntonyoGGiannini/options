# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`options` is a quantitative finance tool for screening and ranking **covered call** opportunities on US equities/ETFs. It combines Black-Scholes d2 (risk-neutral) and empirical (historical frequency) probability-of-exercise models with a realistic brokerage cost model to score and rank option chains.

## Commands

```bash
# Install (editable with dev dependencies)
pip install -e ".[dev]"

# Run the screener
options --config config.toml
python3 t1.py                          # legacy alias

# CLI overrides
options --config config.toml --ativos IBIT,AAPL --top-n 3
options --offline --pasta-mock ./base_mock   # use saved mock data
options --config config.toml --salvar-mock --pasta-mock ./base_mock  # save mock

# Subcommands
options --config config.toml backtest --distancia 0.05 --dias 14
options --offline carteira --arquivo exemplo_carteira.json --saida ./relatorios

# Tests
pytest                                 # all tests
pytest tests/test_black_scholes.py    # single file
pytest -v                             # verbose

# Lint & type-check
ruff check .
ruff format .
mypy options
```

## Architecture

The codebase is organized in strict layers with no upward dependencies:

```
CLI (cli.py)
  └─ Config (config.py)          — validated TOML dataclass, all runtime params
  └─ Runner (runner.py)          — outer loop: per-asset orchestration
       └─ Data Layer (data/)     — ProvedorDados protocol, swappable yfinance ↔ mock
       └─ Pipeline (models/pipeline.py) — vectorized batch computation of 30+ metrics
       └─ Ranking (ranking.py)   — filter chain → scoring → top-N
       └─ Report (report.py)     — Excel + payoff graph generation
       └─ Portfolio (portfolio.py) — multi-client covered_call/roll/buy-write analysis
       └─ Backtest (backtest.py) — historical strategy simulation
```

**Data abstraction:** `data/base.py` defines `ProvedorDados` (protocol) and `DadosMercado` (container). `ProvedorYFinance` (online, disk-cached) and `ProvedorMock` (CSV/JSON files) are interchangeable — no model or ranking code touches the provider directly.

**Pipeline:** `models/pipeline.py:preparar_calls_para_modelo()` is the core — a single-pass vectorized function that computes all 30+ per-option metrics (probabilities, Greeks, costs, returns) from raw chain data. Adding a new metric belongs here.

**Probability model:** Final probability = `max(prob_d2, prob_empirica)` (conservative worst-case). d2 from Black-Scholes in `models/black_scholes.py`; empirical from non-overlapping historical windows in `models/empirical.py`.

**Scoring:** `score_venda = retorno_anualizado_liquido × (1 - prob_exercicio_final)` — rewards income, penalizes assignment risk.

**Cost model:** Net premium = `premium - sell_cost - (exercise_cost × prob_final)`, where exercise cost = `max(0.25% × strike × 100, $10)`.

## Key Conventions

**Language:** Portuguese naming throughout — variables, function names, column names, and TOML keys are in Portuguese (e.g., `ativo`, `premio`, `taxa_livre_risco`, `prob_exerc_max`). Follow this convention when adding anything.

**Volatility fallback:** IV from yfinance is preferred; if unavailable, realized historical vol is used and `fonte_vol` is set to `"historica"` vs `"implicita"`.

**Filter order in `ranking.py`:** Liquidity → probability cap → strike distance → positive net return → positive profit-if-exercised. Rejected options are kept in the full matrix with a `status` column explaining rejection reason.

**Mock data:** `base_mock/` contains pre-downloaded CSV/JSON for 23 tickers used in offline mode and tests. Tests use fixtures from `tests/conftest.py` pointing to this directory.

**Config:** `config.toml` is the user-facing config. Per-asset overrides for dividend yield and cost basis use TOML tables:
```toml
[dividend_yield]
AAPL = 0.005

[preco_medio_aquisicao]
IBIT = 55.00
```

**Outputs:** The screener writes `top_opcoes_covered_call.xlsx` (ranked results) and `matriz_opcoes.xlsx` (full matrix with rejection reasons). Portfolio analysis writes one Excel per client with three sheets: `covered_call`, `rolagem`, `buy_write`.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on push to `main` and all PRs: `ruff check` → `mypy options` → `pytest`, on Python 3.11 and 3.12.
