# Guia de Uso — allocation

Plataforma de análise quantitativa de covered calls em ações/ETFs norte-americanos.

---

## Sumário

1. [Instalação](#instalação)
2. [Configuração (config.toml)](#configuração-configtoml)
3. [Screener de Covered Calls](#screener-de-covered-calls)
4. [Análise de Carteira](#análise-de-carteira)
5. [Backtest](#backtest)
6. [Modo Offline / Mock](#modo-offline--mock)
7. [Referência das Funções](#referência-das-funções)
8. [Fluxo de Dados](#fluxo-de-dados)
9. [Colunas de Saída](#colunas-de-saída)

---

## Instalação

```bash
git clone <repo>
cd allocation
pip install -e ".[dev]"
```

Verifique:

```bash
allocation --help
```

---

## Configuração (config.toml)

Todos os parâmetros da plataforma vivem em `config.toml`. Abaixo, cada seção com os campos, tipos e o que controlam.

### Universo de ativos

```toml
lista_ativos = ["AAPL", "NVDA", "SPY", "IBIT"]
top_n = 5   # quantas opções retornar por ativo
```

### Filtros de probabilidade e risco

```toml
prob_exerc_max = 0.15        # probabilidade máxima de exercício aceita (15%)
taxa_livre_risco = 0.045     # taxa livre de risco anualizada (4.5%)
dividend_yield = 0.0         # yield de dividendos padrão (pode ser sobrescrito por ativo)
```

Sobrescrita por ativo:

```toml
[dividend_yield]
AAPL = 0.005
IVV  = 0.013
```

### Modelos de probabilidade

```toml
usar_prob_d2       = true   # probabilidade risk-neutral de Black-Scholes (N(d2))
usar_prob_empirica = true   # frequência histórica não-sobreposta
periodo_historico  = "5y"   # histórico para vol realizada e empírica
min_amostras_empirica = 30  # mínimo de janelas independentes exigido
```

**Probabilidade final** = `max(prob_d2, prob_empirica)` — abordagem conservadora.

### Janela de vencimento e prêmio

```toml
usar_premio = "bid"   # convenção de prêmio: bid | ask | lastPrice | mid
dias_ano    = 365
min_dias    = 7       # dias corridos mínimos até vencimento
max_dias    = 20      # dias corridos máximos até vencimento
```

### Filtros de liquidez

```toml
liquidez_volume_min       = 100    # volume diário mínimo
liquidez_open_interest_min = 500   # open interest mínimo
liquidez_spread_max        = 0.15  # spread bid-ask máximo como fração do mid
```

### Custos de corretagem

```toml
tamanho_contrato    = 100      # ações por contrato
custo_compra        = 1.0      # custo fixo por contrato ao comprar ($)
custo_venda         = 1.0      # custo fixo por contrato ao vender ($)
custo_exercicio_pct = 0.0025   # 0.25% do valor nocional se exercido
custo_exercicio_min = 0.0     # mínimo de custo de exercício por contrato ($)
```

Custo de exercício efetivo por contrato:
```
max(custo_exercicio_pct × strike × tamanho_contrato, custo_exercicio_min)
```

### Distância do strike

```toml
min_distancia_strike_pct = 0.0   # strike ≥ preço atual × (1 + min_distancia)
                                  # use valor negativo para aceitar ITM
```

### Peso dos Greeks no score

```toml
peso_theta = 0.0   # peso do benefício de theta decay no score
peso_vega  = 0.0   # peso da penalidade de vega (risco de volatilidade)
```

Com ambos em zero: `score = retorno_anualizado × (1 − prob_exercício)`.

### Custo de aquisição (portfolio mode)

```toml
[preco_medio_aquisicao]
AAPL = 180.00
NVDA = 95.00
```

### Arquivos de saída

```toml
arquivo_excel  = "top_opcoes_covered_call.xlsx"   # ranking top-N
arquivo_matriz = "matriz_opcoes.xlsx"             # matriz completa com status
```

---

## Screener de Covered Calls

O screener varre o universo de ativos e retorna as melhores oportunidades de venda de call coberta, rankeadas por `score_venda`.

### Uso básico

```bash
allocation --config config.toml
```

**Output:**
- `top_opcoes_covered_call.xlsx` — top-N opções por ativo
- `matriz_opcoes.xlsx` — todas as opções com coluna `status` explicando rejeições
- Gráfico de payoff da melhor opção (PNG embutido no terminal, se suportado)
- Resumo no terminal por ativo

### Sobrescrever ativos via CLI

```bash
allocation --config config.toml --ativos AAPL,NVDA,MSFT
```

### Sobrescrever top-N via CLI

```bash
allocation --config config.toml --top-n 3
```

### Output no terminal (por ativo)

```
AAPL | strike=215 | venc=2025-06-20 | prêmio=1.82 | retorno_anualizado=18.4% | prob_exerc=11.2% | score=0.163
```

---

## Análise de Carteira

Analisa portfólios reais de clientes com três frentes:

1. **Covered Call** — sugere calls a vender em posições não cobertas
2. **Rolagem** — avalia calls já vendidas e sugere fechar + reabrir mais longe
3. **Buy-Write** — sugere entrada simultânea em ação + venda de call

### Formato do arquivo de carteira (JSON)

```json
[
  {
    "nome": "Nome do Cliente",
    "posicoes": [
      { "ativo": "AAPL", "quantidade": 300, "preco_custo": 180.0 },
      { "ativo": "NVDA", "quantidade": 200, "preco_custo": 95.0 }
    ],
    "calls_vendidas": [
      {
        "ativo": "AAPL",
        "strike": 210.0,
        "vencimento": "2025-07-17",
        "premio_recebido": 3.50,
        "contratos": 2
      }
    ],
    "caixa": 100000.0,
    "prob_exerc_max": 0.15,
    "min_dias": 21,
    "max_dias": 60,
    "permitir_strike_abaixo_custo": false
  }
]
```

**Campos obrigatórios em `posicoes`:** `ativo`, `quantidade`, `preco_custo`
**Campos obrigatórios em `calls_vendidas`:** `ativo`, `strike`, `vencimento`, `premio_recebido`, `contratos`

O arquivo pode ser um array (vários clientes) ou um objeto único (um cliente).

### Comando

```bash
allocation --config config.toml carteira \
    --arquivo exemplo_carteira.json \
    --saida ./relatorios
```

**Output:**
- Um arquivo Excel por cliente em `./relatorios/`, ex: `Nome_do_Cliente.xlsx`
- Três abas por Excel: `covered_call`, `rolagem`, `buy_write`
- Resumo no terminal

### Aba `covered_call`

Posições em ações sem call coberta correspondente.

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `strike` | Strike sugerido |
| `vencimento` | Data de vencimento |
| `premio` | Prêmio por ação |
| `retorno_anualizado` | Retorno líquido de custos |
| `prob_exerc` | Probabilidade de exercício |
| `score_venda` | Score composto |
| `alerta_abaixo_custo` | True se strike < preço de custo |

### Aba `rolagem`

Uma linha por call vendida com avaliação de rolagem.

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `strike_atual` | Strike da call vendida |
| `vencimento_atual` | Vencimento da call vendida |
| `valor_recompra_est` | Custo estimado para fechar posição |
| `credito_liquido_roll` | Crédito líquido da rolagem |
| `strike_novo` | Strike sugerido para nova call |
| `vencimento_novo` | Novo vencimento sugerido |
| `recomendacao` | `"rolar"` ou `"manter"` |

### Aba `buy_write`

Ativos do universo não presentes na carteira, com sugestão de entrada combinada.

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `preco_acao` | Preço atual da ação |
| `strike` | Strike da call |
| `premio` | Prêmio por ação |
| `custo_liquido` | `preco_acao - premio` (custo efetivo de entrada) |
| `retorno_se_exercido` | Retorno se ação for chamada no strike |
| `score_venda` | Score composto |

---

## Backtest

Simula a estratégia de venda de call coberta sobre histórico de preços.

### Comando

```bash
allocation --config config.toml backtest \
    --distancia 0.05 \
    --dias 14
```

**Parâmetros:**
- `--distancia` — distância percentual do strike em relação ao preço (ex: 0.05 = 5% OTM)
- `--dias` — dias corridos de prazo por operação (default: 14)

**Output no terminal por ativo:**

```
=== Backtest AAPL ===
Operações     :  87
Retorno médio :  1.84%
Retorno anual : 24.1%
Taxa exercício: 12.6%
Taxa de acerto: 87.4%
Vol retornos  :  2.1%
```

**Campos do `ResumoBacktest`:**

| Campo | Tipo | Descrição |
|---|---|---|
| `n_operacoes` | int | Total de trades simulados |
| `retorno_medio` | float | Retorno médio por operação |
| `retorno_anualizado` | float | Retorno anualizado (252 pregões) |
| `taxa_exercicio` | float | Fração de operações exercidas |
| `taxa_acerto` | float | Fração com retorno ≥ 0 |
| `vol_retornos` | float | Desvio padrão dos retornos |

---

## Modo Offline / Mock

Permite rodar sem conexão usando dados pré-baixados.

### Salvar dados para uso offline

```bash
allocation --config config.toml --salvar-mock --pasta-mock ./base_mock
```

### Usar dados salvos

```bash
allocation --offline --pasta-mock ./base_mock
```

O diretório `base_mock/` já acompanha o repositório com 23 tickers pré-baixados.

---

## Referência das Funções

### `preparar_calls_para_modelo()` — `opcoes/pipeline.py`

Calcula todas as métricas por opção em um único passo vetorizado.

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `chain` | `pd.DataFrame` | Chain de calls do yfinance (colunas: `strike`, `bid`, `ask`, `lastPrice`, `volume`, `openInterest`, `impliedVolatility`) |
| `preco_atual` | `float` | Preço spot do ativo |
| `historico` | `pd.Series` | Série de preços de fechamento |
| `config` | `Config` | Configuração completa |
| `div_yield` | `float` | Dividend yield do ativo |

**Output:** `pd.DataFrame` com 30+ colunas, uma linha por opção:

| Coluna | Descrição |
|---|---|
| `strike` | Strike da opção |
| `dias_vencimento` | Dias corridos até vencimento |
| `premio` | Prêmio selecionado (bid/ask/mid/last) |
| `distancia_strike_pct` | `(strike/preco - 1)` |
| `retorno_bruto_pct` | `premio / preco` |
| `retorno_anualizado` | Retorno bruto anualizado |
| `liquidez_ok` | Bool — passa filtros de liquidez |
| `fonte_vol` | `"implicita"` ou `"historica"` |
| `iv` | Volatilidade implícita usada |
| `delta` | Greeks delta |
| `gamma` | Greeks gamma |
| `vega` | Greeks vega |
| `theta` | Greeks theta (decay diário) |
| `rho` | Greeks rho |
| `prob_d2` | Probabilidade risk-neutral N(d2) |
| `prob_empirica` | Frequência histórica empírica |
| `usa_empirica` | Bool — se empírica foi calculada |
| `prob_exercicio_final` | `max(prob_d2, prob_empirica)` |
| `risco_exerc_antecipado` | Bool — heurística americana |

---

### `rankear_calls()` — `opcoes/calls.py`

Aplica filtros e calcula score final, retornando top-N opções.

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `df` | `pd.DataFrame` | Output de `preparar_calls_para_modelo()` |
| `config` | `Config` | Configuração |
| `preco_atual` | `float` | Preço spot |
| `preco_custo` | `float \| None` | Preço médio de aquisição (None = modo screener) |
| `matriz_out` | `list \| None` | Lista para acumular matriz completa |

**Output:** `pd.DataFrame` com as top-N opções, colunas adicionais:

| Coluna | Descrição |
|---|---|
| `premio_liquido` | `premio - custo_venda - custo_exercicio × prob` |
| `retorno_se_exercido_anualizado` | Retorno líquido se chamado no strike |
| `score_venda` | Score composto final |
| `status` | `"ok"` (aceitas) ou motivo da rejeição |

**Rejeições registradas no `status`:**

| Status | Motivo |
|---|---|
| `"liquidez"` | Não passa filtros de volume/OI/spread |
| `"prob_exerc_max"` | Probabilidade acima do limite |
| `"distancia_strike"` | Strike muito próximo do preço |
| `"retorno_negativo"` | Prêmio líquido ≤ 0 |
| `"lucro_exerc_negativo"` | Prejuízo se exercido (buy-write) |

---

### `calcular_probabilidade_empirica_batch()` — `models/empirical.py`

Calcula a frequência histórica de o ativo superar o strike em janelas não-sobrepostas.

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `precos` | `pd.Series` | Série de preços de fechamento |
| `preco_atual_arr` | `np.ndarray` | Preço atual por opção |
| `strike_arr` | `np.ndarray` | Strike por opção |
| `dias_janela_arr` | `np.ndarray` | Dias até vencimento por opção |
| `min_amostras` | `int` | Mínimo de janelas independentes (default: 30) |

**Output:** `(probs: np.ndarray, usa_empirica: np.ndarray)`

- `probs[i]` — probabilidade empírica para opção i (NaN se histórico insuficiente)
- `usa_empirica[i]` — True se cálculo foi possível

---

### `calcular_prob_exercicio_risk_neutral_vetor()` — `models/black_scholes.py`

Probabilidade risk-neutral de o ativo estar acima do strike no vencimento (N(d2)).

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `S` | `np.ndarray` | Preço spot |
| `K` | `np.ndarray` | Strike |
| `T` | `np.ndarray` | Tempo até vencimento em anos |
| `r` | `float` | Taxa livre de risco |
| `sigma` | `np.ndarray` | Volatilidade implícita |
| `q` | `float` | Dividend yield |

**Output:** `np.ndarray` — N(d2) por opção; NaN onde T≤0 ou sigma≤0.

---

### `backtest_covered_call()` — `opcoes/backtest.py`

Simula vendas sistemáticas de call coberta sobre histórico de preços.

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `historico` | `pd.Series` | Série de preços com DatetimeIndex |
| `config` | `Config` | Configuração |
| `distancia` | `float` | Distância OTM do strike (ex: 0.05) |
| `dias` | `int` | Prazo de cada operação em pregões |

**Output:** `ResumoBacktest` com campos: `n_operacoes`, `retorno_medio`, `retorno_anualizado`, `taxa_exercicio`, `taxa_acerto`, `vol_retornos`.

---

### `carregar_carteiras()` — `risco/portfolio.py`

Carrega um ou mais portfólios de clientes a partir de JSON.

**Input:** caminho para arquivo JSON (array ou objeto único)

**Output:** `list[Carteira]`

Cada `Carteira` contém:
- `nome: str`
- `posicoes: list[PosicaoAcao]`
- `calls_vendidas: list[CallVendida]`
- `caixa: float`
- Parâmetros de análise: `prob_exerc_max`, `min_dias`, `max_dias`, `permitir_strike_abaixo_custo`

---

### `reportar_carteiras()` — `risco/portfolio.py`

Gera Excel por cliente com as três abas de análise.

**Input:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `carteiras` | `list[Carteira]` | Portfólios carregados |
| `config` | `Config` | Config base (sobrescrita por parâmetros do cliente) |
| `provedor` | `ProvedorDados` | Fonte de dados (yfinance ou mock) |
| `pasta_saida` | `str` | Diretório de saída dos Excel |

**Output:** Arquivos `{pasta_saida}/{nome_cliente}.xlsx` por cliente.

---

## Fluxo de Dados

```
config.toml
    │
    ▼
Config (config.py)          ←── CLI overrides (--ativos, --top-n, ...)
    │
    ▼
Runner (runner.py)
    │
    ├── ProvedorYFinance ──► yfinance API ──► DadosMercado
    │   ou ProvedorMock  ──► base_mock/
    │
    ▼
processar_ativo() [calls.py]
    │
    ├── preparar_calls_para_modelo() [pipeline.py]
    │       ├── calcular_premio_vetor()
    │       ├── Black-Scholes Greeks [models/greeks.py]
    │       ├── calcular_prob_exercicio_risk_neutral_vetor() [models/black_scholes.py]
    │       └── calcular_probabilidade_empirica_batch() [models/empirical.py]
    │
    ├── rankear_calls()
    │       ├── filtros: liquidez → prob → distância → retorno → lucro_exerc
    │       └── score_venda = retorno_anualizado × (1 − prob) × θ_weight / vega_weight
    │
    └── DataFrame top-N por ativo
            │
            ▼
        report.py
            ├── top_opcoes_covered_call.xlsx
            ├── matriz_opcoes.xlsx
            └── payoff_melhor.png
```

---

## Colunas de Saída

### `top_opcoes_covered_call.xlsx`

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `strike` | Strike da opção |
| `vencimento` | Data de vencimento |
| `dias_vencimento` | Dias corridos |
| `premio` | Prêmio por ação (convenção configurada) |
| `premio_liquido` | Prêmio após custos de venda e exercício esperado |
| `retorno_bruto_pct` | `premio / preco_atual` |
| `retorno_anualizado` | Retorno anualizado bruto |
| `retorno_se_exercido_anualizado` | Retorno anualizado se chamado no strike |
| `prob_d2` | Probabilidade risk-neutral N(d2) |
| `prob_empirica` | Frequência histórica empírica |
| `prob_exercicio_final` | Probabilidade final usada no filtro e score |
| `score_venda` | Score composto final (ordena o ranking) |
| `iv` | Volatilidade implícita usada |
| `fonte_vol` | `"implicita"` ou `"historica"` |
| `delta` | Delta da opção |
| `theta` | Theta (decay por dia, em $) |
| `vega` | Vega |
| `volume` | Volume negociado |
| `openInterest` | Open interest |
| `bid` / `ask` | Bid e ask |
| `distancia_strike_pct` | `(strike/preco - 1)` |
| `risco_exerc_antecipado` | Alerta de exercício antecipado (opções americanas) |
| `alerta_abaixo_custo` | Strike abaixo do preço de custo (modo carteira) |
| `lucro_se_exercido` | Lucro total se exercido (modo carteira) |

### `matriz_opcoes.xlsx`

Inclui todas as opções (aceitas e rejeitadas) com a coluna adicional:

| Coluna | Descrição |
|---|---|
| `status` | `"ok"` ou motivo de rejeição (`"liquidez"`, `"prob_exerc_max"`, etc.) |
