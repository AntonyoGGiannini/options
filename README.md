# Options

Ferramenta quantitativa para análise e ranking de **covered calls** em ativos de renda variável (ETFs e ações americanas). Combina três estimativas de probabilidade de exercício e custos de corretagem para identificar a melhor opção a vender dado o perfil de risco do usuário.

---

## Como funciona

Para cada call disponível no mercado, o modelo calcula:

1. **Probabilidade de exercício** por três métodos:
   - `prob_d2` — Black-Scholes (N(d2)), risk-neutral
   - `prob_empirica` — frequência histórica: em quantas janelas equivalentes ao prazo o ativo subiu o suficiente para atingir o strike
   - `prob_exercicio_final = max(prob_d2, prob_empirica)` — combinação conservadora

2. **Retorno líquido** descontando os custos de corretagem da venda

3. **Score de ranking**: `retorno_anualizado_liquido × (1 - prob_exercicio_final)`

Para cada contrato também são calculados os **Greeks** (delta, gamma, vega,
theta, rho). Quando a volatilidade implícita está ausente/inválida, usa-se a
**volatilidade realizada** histórica como fallback (`fonte_vol`). O
`dividend_yield` pode ser único ou **por ativo**, e contratos com dividendo e
delta alto recebem flag de **risco de atribuição antecipada**.

Filtros aplicados antes do ranking:
- Apenas calls OTM (strike acima do preço atual)
- `prob_exercicio_final ≤ PROB_EXERC_MAX`
- `premio_liquido > 0` (prêmio positivo após custos)
- Liquidez mínima: `volume ≥ 100`, `openInterest ≥ 500`, `spread ≤ 15%`

---

## Instalação

```bash
pip install -e .          # instala o pacote e o comando `options`
# ou, só as dependências de runtime:
pip install -r requirements.txt
```

Para desenvolvimento (testes, lint, type-check):

```bash
pip install -e ".[dev]"
```

---

## Uso

A configuração é **declarativa**, em `config.toml`. Edite o arquivo e rode via CLI:

```bash
options --config config.toml
```

Overrides rápidos pela linha de comando:

```bash
options --config config.toml --ativos IBIT,AAPL --top-n 3
options --offline                 # usa dados mock locais (sem internet)
options --config config.toml --sem-cache -v
```

O entrypoint legado continua funcionando (carrega `config.toml` automaticamente):

```bash
python3 t1.py
```

### Backtest

Valida a metodologia de seleção de strike sobre o histórico de preços. O prêmio
é estimado por Black-Scholes com a **volatilidade realizada** de cada data
(backtest baseado em modelo — não usa cadeias de opções históricas):

```bash
options --config config.toml backtest --distancia 0.05 --dias 14
```

Reporta, por ativo: nº de trades, retorno médio/anualizado da covered call,
taxa de exercício, taxa de acerto e comparação com buy & hold.

### Parâmetros configuráveis (`config.toml`)

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `lista_ativos` | `["IBIT", ...]` | Tickers a analisar |
| `top_n` | `5` | Top N opções por ativo |
| `prob_exerc_max` | `0.15` | Probabilidade máxima de exercício aceita |
| `taxa_livre_risco` | `0.045` | Taxa livre de risco anual |
| `dividend_yield` | `0.00` | Dividend yield anual (valor único ou por ativo via tabela `[dividend_yield]`) |
| `usar_premio` | `"bid"` | Preço do prêmio: `bid`, `ask`, `lastPrice` ou `mid` |
| `dias_ano` | `365` | Convenção de anualização (dias corridos) |
| `min_dias` / `max_dias` | `7` / `20` | Faixa de prazo até vencimento (dias) |
| `periodo_historico` | `"5y"` | Janela de histórico para probabilidade empírica |
| `min_amostras_empirica` | `30` | Mínimo de amostras para ativar prob empírica |
| `tamanho_contrato` | `100` | Ações por contrato |
| `custo_compra` / `custo_venda` / `custo_exercicio` | `0.00` | Custos por contrato (USD) |
| `usar_cache` / `cache_ttl_horas` | `true` / `6.0` | Cache em disco dos dados de mercado |
| `modo_offline` / `salvar_mock` | `false` | Usar/gerar dados mock locais |

---

## Output

Gera `top_opcoes_covered_call.xlsx` (configurável em `arquivo_excel`) com o
ranking das melhores covered calls por ativo. Principais colunas:

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `ranking_ativo` | Posição dentro do ativo (1 = melhor) |
| `strike` | Strike da opção |
| `premio` | Prêmio por ação (conforme `usar_premio`) |
| `expiration` | Data de vencimento |
| `dias_uteis_ate_vencimento` | Pregões até o vencimento |
| `prob_exercicio` | Probabilidade Black-Scholes (d2) |
| `prob_empirica` | Probabilidade histórica empírica |
| `prob_exercicio_final` | Probabilidade conservadora final `max(d2, empírica)` |
| `delta` / `theta` / `vega` | Greeks do contrato |
| `fonte_vol` | `implicita` ou `historica` (fallback de volatilidade) |
| `risco_atribuicao_antecipada` | Flag de exercício antecipado (dividendo + delta alto) |
| `retorno_anualizado_pct` | Retorno anualizado bruto do prêmio |
| `retorno_anualizado_liquido` | Retorno anualizado líquido de custos |
| `bid` / `ask` | Preços de mercado |
| `volume` / `openInterest` | Liquidez |
| `preco_atual_ativo` | Preço atual do ativo |
| `score_venda` | Score de ranking |

O terminal imprime a tabela e o resumo da melhor call geral, e um gráfico de
payoff (`payoff_<ATIVO>.png`) é gerado para a melhor opção.

---

## Estrutura

```
options/
├── config.py            # Config declarativa (TOML) com validação
├── runner.py            # Orquestração de alto nível (run e backtest)
├── ranking.py           # Filtros + score + top-N
├── report.py            # Saída: tabela, Excel e gráfico
├── backtest.py          # Backtest da covered call sobre o histórico
├── cli.py               # Interface de linha de comando
├── logging_setup.py     # Logging estruturado
├── data/                # Provedores de dados intercambiáveis
│   ├── base.py          #   interface ProvedorDados + DadosMercado
│   ├── yfinance_provider.py  # online, com cache e retry
│   ├── mock_provider.py # offline (CSV/JSON)
│   ├── cache.py         # cache em disco (parquet) com TTL
│   └── retry.py         # backoff exponencial
└── models/              # Núcleo quantitativo
    ├── black_scholes.py # prob d2 (risk-neutral) e preço da call
    ├── monte_carlo.py   # prob Monte Carlo (batch)
    ├── empirical.py     # prob empírica histórica
    ├── greeks.py        # delta, gamma, vega, theta, rho
    ├── volatility.py    # volatilidade realizada (fallback de IV)
    ├── pipeline.py      # métricas por cadeia de opções
    └── payoff.py        # gráfico de payoff

config.toml              # Configuração da execução
tests/                   # Suíte pytest (modelos, greeks, backtest, e2e)
t1.py / functions.py     # Shims de compatibilidade retroativa
```

### Desenvolvimento

```bash
pytest            # testes
ruff check .      # lint
mypy options      # type-check
```

CI no GitHub Actions roda lint + mypy + testes em cada PR (Python 3.11 e 3.12).

### Arquitetura

A camada de dados é abstraída pela interface `ProvedorDados`, permitindo trocar
yfinance, dados mock ou qualquer outra fonte sem alterar os modelos ou o ranking.
O provedor online aplica cache em disco (TTL) e retry com backoff exponencial.
