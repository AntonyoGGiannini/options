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

Filtros aplicados antes do ranking:
- Apenas calls OTM (strike acima do preço atual)
- `prob_exercicio_final ≤ PROB_EXERC_MAX`
- `premio_liquido > 0` (prêmio positivo após custos)
- Liquidez mínima: `volume ≥ 100`, `openInterest ≥ 500`, `spread ≤ 15%`

---

## Instalação

```bash
pip install -r requirements.txt
```

Dependências: `pandas`, `numpy`, `scipy`, `yfinance`

---

## Uso

Edite as constantes no topo de `t1.py` e execute:

```bash
python3 t1.py
```

### Parâmetros configuráveis

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `ATIVO` | `"IBIT"` | Ticker do ativo |
| `PROB_EXERC_MAX` | `0.80` | Probabilidade máxima de exercício aceita |
| `TAXA_LIVRE_RISCO` | `0.045` | Taxa livre de risco anual |
| `DIVIDEND_YIELD` | `0.00` | Dividend yield anual |
| `USAR_PREMIO` | `"bid"` | Preço do prêmio: `bid`, `ask`, `lastPrice` ou `mid` |
| `DIAS_ANO` | `365` | Convenção de anualização (dias corridos) |
| `MIN_DIAS` | `7` | Prazo mínimo até vencimento (dias) |
| `MAX_DIAS` | `45` | Prazo máximo até vencimento (dias) |
| `PERIODO_HISTORICO` | `"5y"` | Janela de histórico para probabilidade empírica |
| `MIN_AMOSTRAS_EMPIRICA` | `30` | Mínimo de amostras para ativar prob empírica |
| `TAMANHO_CONTRATO` | `100` | Ações por contrato |
| `CUSTO_COMPRA` | `1.00` | Custo de compra por contrato (USD) |
| `CUSTO_VENDA` | `1.00` | Custo de venda por contrato (USD) |
| `CUSTO_EXERCICIO` | `5.00` | Custo de exercício por contrato (USD) |

---

## Output

Gera `df_calls_ajustado.xlsx` com as colunas:

| Coluna | Descrição |
|---|---|
| `expiration` | Data de vencimento |
| `strike` | Strike da opção |
| `T` | Prazo em anos |
| `dias_uteis_ate_vencimento` | Pregões até o vencimento |
| `bid` / `ask` / `lastPrice` | Preços de mercado |
| `volume` / `openInterest` | Liquidez |
| `premio` | Prêmio bruto por ação |
| `premio_liquido` | Prêmio líquido após custo de venda |
| `impliedVolatility` | Volatilidade implícita |
| `retorno_necessario` | Retorno necessário para atingir o strike |
| `prob_d2` | Probabilidade Black-Scholes |
| `prob_empirica` | Probabilidade histórica empírica |
| `usa_prob_empirica` | Se há histórico suficiente para a prob empírica |
| `prob_exercicio_final` | Probabilidade conservadora final |
| `prob_exercicio_mc` | Probabilidade Monte Carlo |
| `rendimento_liquido` | Yield líquido sobre o preço atual |
| `retorno_anualizado_liquido` | Retorno anualizado líquido |
| `score_venda` | Score de ranking |
| `ranking` | Posição (1 = melhor) |

O terminal imprime o resumo da melhor call encontrada.

---

## Estrutura

```
Options2/
├── t1.py           # Configuração e execução principal
├── functions.py    # Modelos e funções de cálculo
├── requirements.txt
└── README.md
```

### Funções principais em `functions.py`

| Função | Descrição |
|---|---|
| `obter_calls(ativo)` | Busca cadeia de opções via yfinance com filtros de liquidez |
| `calcular_preco_atual(ativo)` | Preço atual via yfinance |
| `obter_historico_precos(ativo, periodo)` | Histórico de preços ajustados |
| `preparar_calls_para_modelo(...)` | Pipeline completo de cálculo por ativo |
| `calcular_prob_exercicio_risk_neutral_vetor(...)` | Black-Scholes vetorizado |
| `calcular_prob_acima_strike_monte_carlo_batch(...)` | Monte Carlo em batch |
| `calcular_probabilidade_empirica_batch(...)` | Probabilidade histórica vetorizada |
