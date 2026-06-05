# allocation

Plataforma quantitativa modular para análise de portfólio e estratégias de opções em ETFs e ações americanas. O módulo principal (`opcoes`) combina duas estimativas de probabilidade de exercício e custos de corretagem para identificar as melhores covered calls e buy-writes dado o perfil de risco do usuário.

---

## Como funciona

Para cada call disponível no mercado, o modelo calcula:

1. **Probabilidade de exercício** por dois métodos:
   - `prob_d2` — Black-Scholes (N(d2)), risk-neutral
   - `prob_empirica` — frequência histórica (janelas não-sobrepostas): em quantas
     janelas equivalentes ao prazo o ativo subiu o suficiente para atingir o strike
   - `prob_exercicio_final = max(prob_d2, prob_empirica)` — combinação conservadora

2. **Retorno líquido** descontando os custos de corretagem da venda

3. **Score de ranking:**
   ```
   score_venda = retorno_se_exercido_anualizado
               × (1 − prob_exercicio_final)
               × (1 + peso_theta × theta_eff)
               / (1 + peso_vega × vega_risk)
   ```
   Com `peso_theta = peso_vega = 0` (default), reduz a `retorno_se_exercido × (1 − prob)`.

Para cada contrato também são calculados os **Greeks** (delta, gamma, vega, theta, rho). Quando a volatilidade implícita está ausente/inválida, usa-se a **volatilidade realizada** histórica como fallback (`fonte_vol`). O `dividend_yield` pode ser único ou **por ativo**, e contratos com dividendo e delta alto recebem flag de **risco de atribuição antecipada**.

### Screener vs. análise de posição existente

- **Screener (default):** sem `preco_medio_aquisicao`. Use para varrer dezenas de
  ativos em busca de oportunidades de venda de call (incl. buy-write). A saída é
  enxuta — o preço médio não importa aqui.
- **Posição existente (opcional):** ao informar `preco_medio_aquisicao` para um
  ativo, a saída ganha colunas de custo (`retorno_sobre_custo`,
  `capital_por_contrato`) e o flag `alerta_abaixo_custo = true` para strikes abaixo
  do custo (exercício trancaria prejuízo).

Filtros aplicados antes do ranking:
- `distancia_strike_pct ≥ min_distancia_strike_pct` (padrão 0.0 = apenas OTM+)
- `prob_exercicio_final ≤ prob_exerc_max`
- `retorno_anualizado_liquido > 0` (prêmio positivo após custos)
- `lucro_se_exercido > 0` — descarta operações que dariam prejuízo se a call for
  exercida (venda das ações pelo strike + prêmio − custos de venda/exercício/compra).
  Pode ser desligado por cliente via `permitir_strike_abaixo_custo`.
- Liquidez mínima: `volume ≥ 100`, `openInterest ≥ 500`, `spread ≤ 15%`

O **custo de exercício (atribuição)** por contrato segue a regra
`max(custo_exercicio_pct × strike × tamanho_contrato, custo_exercicio_min) + custo_exercicio`
— por padrão **0,25% do valor de venda ou US$ 10, o que for maior**. Ele é
descontado do prêmio líquido (ponderado pela probabilidade de exercício), entra
no filtro de lucro-se-exercido e é refletido no gráfico de payoff.

### Premissas e limitações

- **Exercício europeu:** Greeks e prob d2 seguem Black-Scholes europeu. Para calls
  americanas com dividendo, o flag `risco_atribuicao_antecipada` sinaliza delta ≥ 0.70
  como heurística de risco de early assignment — não substitui modelagem americana.
- **Medidas heterogêneas:** `prob_d2` é risk-neutral; `prob_empirica` é frequência
  histórica real. Combiná-las via `max` é conservador mas mistura medidas distintas.

---

## Instalação

```bash
pip install -e .          # instala o pacote e o comando `allocation`
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
allocation --config config.toml
```

Overrides rápidos pela linha de comando:

```bash
allocation --config config.toml --ativos IBIT,AAPL --top-n 3
allocation --offline                 # usa dados mock locais (sem internet)
allocation --config config.toml --sem-cache -v
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
allocation --config config.toml backtest --distancia 0.05 --dias 14
# argumentos completos
allocation --config config.toml backtest --distancia 0.05 --dias 14 --janela-vol 60
```

Reporta, por ativo: nº de trades, retorno médio/anualizado da covered call,
taxa de exercício, taxa de acerto e comparação com buy & hold.

| Coluna | Descrição |
|---|---|
| `n_trades` | Nº de trades simulados |
| `retorno_medio_cc` | Retorno médio por trade |
| `retorno_anualizado_cc` | Retorno anualizado da estratégia |
| `taxa_exercicio` | % de trades em que a call foi exercida |
| `taxa_acerto` | % de trades com retorno positivo |
| `retorno_medio_buy_hold` | Retorno médio do ativo no período (benchmark) |
| `vol_retorno_cc` | Volatilidade dos retornos da estratégia |

### Análise de carteira

Enquanto o screener varre o universo de forma agnóstica de posição, o subcomando
`carteira` cruza a posição **de um ou mais clientes** (arquivo JSON) com a saída
do screener e gera três frentes de recomendação **por cliente**:

1. **Covered call** — vende calls sobre ações detidas ainda **descobertas**
   (contratos possíveis − contratos já vendidos); por padrão exclui strikes
   abaixo do preço médio (não trava prejuízo).
2. **Rolagem** — para cada call já vendida, calcula o custo de recompra
   (mid da cadeia, ou Black-Scholes com vol realizada como fallback). Quando o
   **prêmio restante** cai abaixo de `limiar_premio_restante` (a maior parte do
   crédito já foi capturada), sugere o roll-out de maior **crédito líquido** na
   janela `rolagem_min_dias`–`rolagem_max_dias`; caso contrário, marca `manter`.
3. **Buy-write** — ranqueia oportunidades em ativos que o cliente **não** detém.

```bash
# --saida é a PASTA de saída; gera um analise_<cliente>.xlsx por cliente
allocation --offline carteira --arquivo exemplo_carteira.json --saida ./relatorios
allocation carteira --arquivo carteira.json --limiar-premio-restante 0.25 --rolagem-max-dias 75
```

O JSON aceita **um cliente** (objeto único) ou **vários clientes** (array).
Formato completo (ver `exemplo_carteira.json`):

```json
[
  {
    "cliente": "Nome do Cliente",
    "caixa": 100000,
    "posicoes": [
      {"ativo": "AAPL", "quantidade": 300, "preco_medio": 180.0},
      {"ativo": "NVDA", "quantidade": 200, "preco_medio": 95.0}
    ],
    "calls_vendidas": [
      {"ativo": "AAPL", "strike": 210.0, "expiration": "2026-07-17",
       "premio_recebido": 3.5, "contratos": 2}
    ],
    "limiar_premio_restante": 0.20,
    "rolagem_min_dias": 21,
    "rolagem_max_dias": 60,
    "permitir_strike_abaixo_custo": false
  }
]
```

| Campo JSON | Obrigatório | Padrão | Descrição |
|---|---|---|---|
| `cliente` | não | — | Nome para nomear o arquivo de saída |
| `caixa` | não | — | Caixa disponível (informativo) |
| `posicoes[].ativo` / `.quantidade` / `.preco_medio` | sim | — | Posição em ações |
| `calls_vendidas[].strike` / `.expiration` / `.premio_recebido` / `.contratos` | sim | — | Call já vendida |
| `limiar_premio_restante` | não | `0.20` | Rolar quando prêmio restante < 20% |
| `rolagem_min_dias` / `rolagem_max_dias` | não | `21` / `60` | Faixa de DTE do roll-out |
| `permitir_strike_abaixo_custo` | não | `false` | Permite sugerir strikes abaixo do preço médio |

Para cada cliente gera `analise_<cliente>.xlsx` com três abas (`covered_call`, `rolagem`, `buy_write`) e imprime o resumo no terminal.

#### Base mock em pasta dedicada

Para validar tudo offline com uma base salva uma única vez:

```bash
# 1) salva a base de todos os ativos da config (uma vez, com internet)
allocation --config config.toml --salvar-mock --pasta-mock ./base_mock

# 2) tickers detidos na carteira que não estão na lista_ativos? salve-os também
allocation --ativos NU,TSM --salvar-mock --pasta-mock ./base_mock

# 3) rode tudo offline a partir da base
allocation --offline --pasta-mock ./base_mock carteira --arquivo exemplo_carteira.json
```

Salve o conjunto de tickers = `lista_ativos` ∪ ativos detidos ∪ ativos com calls
vendidas. Para a rolagem usar a recompra real (mid da cadeia, não o fallback
Black-Scholes), a base do ativo precisa conter o strike + vencimento da call vendida.

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
| `min_distancia_strike_pct` | `0.0` | Distância mínima do strike (0 = OTM+, negativo = permite ITM) |
| `periodo_historico` | `"5y"` | Janela de histórico para probabilidade empírica |
| `min_amostras_empirica` | `30` | Mínimo de janelas não-sobrepostas para ativar prob empírica |
| `tamanho_contrato` | `100` | Ações por contrato |
| `custo_compra` / `custo_venda` | `0.00` | Custos por contrato (USD) |
| `custo_exercicio_pct` / `custo_exercicio_min` | `0.0025` / `10.00` | Custo de exercício = `max(pct × strike × tamanho_contrato, mínimo)` |
| `custo_exercicio` | `0.00` | Taxa fixa adicional de exercício por contrato (USD) |
| `peso_theta` / `peso_vega` | `0.0` / `0.0` | Pesos dos Greeks no score (0 = ignora) |
| `usar_cache` / `cache_ttl_horas` | `true` / `6.0` | Cache em disco dos dados de mercado |
| `modo_offline` / `salvar_mock` | `false` | Usar/gerar dados mock locais |
| `preco_medio_aquisicao` | — | Preço de custo por ativo (tabela `[preco_medio_aquisicao]`); ativa modo covered_call |

---

## Output

Gera `top_opcoes_covered_call.xlsx` (configurável em `arquivo_excel`) com o
ranking das melhores opções por ativo. Colunas de custo (`retorno_sobre_custo`,
`capital_por_contrato`, `alerta_abaixo_custo`) só aparecem quando
`preco_medio_aquisicao` é informado.

| Coluna | Descrição |
|---|---|
| `ativo` | Ticker |
| `ranking_ativo` | Posição dentro do ativo (1 = melhor) |
| `strike` | Strike da opção |
| `premio` | Prêmio por ação (conforme `usar_premio`) |
| `expiration` | Data de vencimento |
| `dias_uteis_ate_vencimento` | Pregões até o vencimento |
| `prob_exercicio` | Probabilidade Black-Scholes (d2), risk-neutral |
| `prob_empirica` | Probabilidade histórica empírica (janelas não-sobrepostas) |
| `prob_exercicio_final` | Probabilidade conservadora final `max(d2, empírica)` |
| `delta` / `theta` / `vega` | Greeks do contrato |
| `fonte_vol` | `implicita` ou `historica` (fallback de volatilidade) |
| `risco_atribuicao_antecipada` | Flag de exercício antecipado (dividendo + delta alto) |
| `alerta_abaixo_custo` | (com custo) `true` se strike < preço médio de aquisição |
| `retorno_anualizado_pct` | Retorno anualizado bruto do prêmio |
| `retorno_anualizado_liquido` | Retorno anualizado líquido de custos |
| `retorno_se_exercido_anualizado` | Retorno anualizado se a call for exercida |
| `downside_protection` | Quanto o ativo pode cair antes do break-even |
| `lucro_se_exercido` | P&L total se o strike for atingido |
| `retorno_sobre_custo` | (com custo) Prêmio líquido / preço médio de aquisição |
| `capital_por_contrato` | (com custo) Capital da posição por contrato (USD) |
| `bid` / `ask` | Preços de mercado |
| `volume` / `openInterest` | Liquidez |
| `preco_atual_ativo` | Preço atual do ativo |
| `score_venda` | Score de ranking |

O terminal imprime a tabela e o resumo da melhor call geral, e um gráfico de
payoff (`payoff_<ATIVO>.png`) é gerado para a melhor opção.

### Matriz completa

Além do ranking, é gerado `matriz_opcoes.xlsx` (configurável em `arquivo_matriz`)
com **todas** as opções candidatas — inclusive as reprovadas — e uma coluna
`status` por opção:

| `status` | Significado |
|---|---|
| `ok` | Passou em todos os filtros |
| `fora do filtro de liquidez` | Reprovada por volume/open interest/spread |
| `fora do filtro de probabilidade de exercicio` | `prob_exercicio_final > prob_exerc_max` |
| `fora dos filtros (retorno/strike/lucro)` | Passa liquidez e probabilidade, mas falha em retorno, distância de strike ou lucro no exercício |

---

## Estrutura

```
allocation/
├── opcoes/              — tudo que usa cadeia de opções + Black-Scholes
│   ├── calls.py         — covered call ranking (filtros, score, top-N)
│   ├── pipeline.py      — batch vetorizado de 30+ métricas por contrato
│   ├── backtest.py      — simulação histórica da covered call
│   ├── puts.py          — venda de puts cash-secured / naked [stub]
│   ├── spreads.py       — multi-perna: bull spread, iron condor [stub]
│   ├── volatilidade.py  — IV rank, term structure, skew [stub]
│   └── hedge.py         — collar, put protetora, beta hedge [stub]
├── acoes/
│   └── screening.py     — screening fundamentalista + momentum [stub]
├── risco/
│   ├── portfolio.py     — análise multi-cliente: covered call, rolagem, buy-write
│   ├── analytics.py     — Greeks agregados, VaR, drawdown, stress test [stub]
│   ├── montecarlo.py    — simulação GBM de portfólio [stub]
│   └── crises.py        — replay contra períodos de crise histórica [stub]
├── data/                — compartilhado: ProvedorDados, yfinance, mock, cache, retry
├── models/              — matemática pura: black_scholes, empirical, greeks, volatility, payoff
├── config.py            — Config declarativa (TOML) com validação
├── runner.py            — orquestrador de alto nível
├── report.py            — saída: Excel e gráfico de payoff
└── cli.py               — interface de linha de comando

config.toml              — configuração da execução
exemplo_carteira.json    — exemplo de carteira multi-cliente
tests/                   — suíte pytest (modelos, greeks, backtest, e2e, carteira)
t1.py                    — entrypoint legado (carrega config.toml automaticamente)
```

### Desenvolvimento

```bash
python3 -m pytest         # testes (usar python3 -m pytest, não bare pytest)
ruff check .              # lint
mypy allocation           # type-check
```

CI no GitHub Actions roda lint + mypy + testes em cada PR (Python 3.11 e 3.12).

### Arquitetura

A camada de dados é abstraída pela interface `ProvedorDados` (`data/base.py`),
permitindo trocar yfinance por dados mock ou qualquer outra fonte sem alterar
modelos ou ranking. O provedor online aplica cache em disco (TTL configurável)
e retry com backoff exponencial.

O `opcoes/pipeline.py:preparar_calls_para_modelo()` é o núcleo — uma única
passagem vetorizada que calcula todas as 30+ métricas por contrato. Novos
indicadores pertencem aqui. Os módulos `models/` contêm apenas matemática pura
(Black-Scholes, Greeks, probabilidade empírica) sem efeitos colaterais.

---

## Versionamento

Este projeto segue [Semantic Versioning 2.0.0](https://semver.org/lang/pt-BR/) — `MAJOR.MINOR.PATCH`.

| Incremento | Quando usar |
|---|---|
| `MAJOR` | Quebra de compatibilidade: remoção de parâmetros, renomeação de funções públicas, mudança de comportamento que quebra código existente |
| `MINOR` | Nova funcionalidade sem quebrar compatibilidade: novo modelo, novo campo no output, nova opção de configuração |
| `PATCH` | Correção de bug, ajuste de cálculo, atualização de dependência sem mudança de API |

### Fluxo de release

```bash
# 1. Alterar version em pyproject.toml
# 2. Commit
git commit -m "chore: bump version to X.Y.Z"
# 3. Tag
git tag vX.Y.Z
# 4. Push com tag
git push origin main --tags
```

### Instalação fixando versão

```bash
# Versão específica — recomendado para produção
pip install git+https://github.com/antonyoggiannini/options.git@v0.6.0

# Sempre a última versão da main
pip install git+https://github.com/antonyoggiannini/options.git
```

### Histórico

| Versão | Descrição |
|---|---|
| `0.6.0` | Rename `options` → `allocation`; reorganização em módulos `opcoes/`, `acoes/`, `risco/`; stubs de puts, spreads, volatilidade, hedge, analytics, montecarlo, crises |
| `0.5.0` | Custo de exercício realista (`max(0,25% × valor de venda, US$ 10)`): descontado do prêmio líquido, refletido no payoff e usado no filtro `lucro_se_exercido > 0` |
| `0.4.0` | `carteira` aceita múltiplos clientes (array JSON); `--saida` passa a ser pasta de saída |
| `0.3.0` | Análise de carteira: covered call sobre ações descobertas, rolagem por prêmio restante baixo e buy-write |
| `0.2.0` | Score e filtro líquidos; covered_call vs buy_write; cost basis no ranking; empírica sem sobreposição; filtro OTM parametrizável |
| `0.1.0` | Versão inicial — núcleo quantitativo (Black-Scholes, empírico), CLI, cache, backtest |
