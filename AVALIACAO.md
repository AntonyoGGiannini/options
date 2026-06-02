# Avaliação do projeto `options`

Avaliação completa de arquitetura, lógica, código e parâmetros de input/output,
com análise de utilidade das funcionalidades no **cenário atual** e proposta de
próximos passos com requisitos.

**Cenário de referência:** ferramenta profissional de **gestão de carteiras de
clientes** — selecionar venda de calls sobre **posições já existentes** dos
clientes e identificar oportunidades de **_buy-write_** (comprar o ativo + vender
call) para rentabilizar o portfólio, inclusive em ativos ainda não detidos.

---

## 1. Sumário executivo

O projeto está **bem arquitetado e maduro para a versão v0.1.0**: pacote modular,
41 testes, CI (ruff + mypy + pytest), type hints, logging estruturado, cache/retry
e provedor de dados abstrato. As Fases 0–2 do `PLANO_DE_EVOLUCAO.md` foram
concluídas com qualidade.

**Veredito:** os maiores ganhos hoje **não** estão em adicionar features, e sim em
(a) **alinhar o código ao cenário de gestão de carteiras** — sobretudo considerar
o **preço médio de aquisição** do cliente na seleção — e (b) **remover peso morto**
(o Monte Carlo é calculado a alto custo e nunca usado). Há ainda divergências
entre o README e o código que comprometem a confiança nos números.

---

## 2. Arquitetura

Arquitetura em camadas, com boa separação de responsabilidades:

```
CLI (cli.py)
  └─ Config declarativa + validada (config.py)
       └─ Camada de dados — interface ProvedorDados (data/base.py)
            ├─ ProvedorYFinance (online: cache parquet + retry backoff)
            └─ ProvedorMock     (offline: CSV/JSON)
       └─ Models / pipeline (models/pipeline.py)
            ├─ black_scholes · monte_carlo · empirical
            ├─ greeks · volatility
            └─ payoff
       └─ Ranking — filtros + score + top-N (ranking.py)
       └─ Report — Excel + gráfico + tabela (report.py)
       └─ Runner — orquestração run/backtest (runner.py)
```

**Pontos fortes**
- Abstração `ProvedorDados` (`options/data/base.py`) permite trocar a fonte de
  dados sem tocar nos modelos — facilita testes (mock) e futuras fontes.
- Vetorização NumPy/pandas; Monte Carlo em batches para controlar memória.
- Config declarativa com validação centralizada (`options/config.py:75-107`).
- Cache em disco com TTL (`options/data/cache.py`) + retry com backoff
  (`options/data/retry.py`).
- 1.529 LOC em `options/`, 41 testes, CI em Python 3.11 e 3.12, versionamento
  semântico documentado.

---

## 3. Lógica e fluxo de dados

```
Config (config.toml + overrides CLI)
   │
   ▼
ProvedorDados.obter(ativo)  ──►  DadosMercado(df_calls, preco_atual, historico)
   │
   ▼
preparar_calls_para_modelo()         (options/models/pipeline.py)
   • T, prêmio, distância de strike, retorno anualizado
   • iv_usada = IV implícita  ──(fallback)──►  volatilidade realizada
   • prob_exercicio (d2 / risk-neutral)
   • prob_exercicio_mc (Monte Carlo)          ◄── calculado, porém NÃO usado
   • greeks (delta, gamma, vega, theta, rho)
   • risco_atribuicao_antecipada (flag)
   • prob_empirica (histórico)
   • prob_exercicio_final = max(prob_d2, prob_empirica)
   │
   ▼
rankear_calls()                       (options/ranking.py)
   • filtros: OTM · prob_final ≤ máx · retorno > 0
   • score_venda = retorno_anualizado × (1 - prob_final) × fator_theta / fator_vega
   • top-N por score
   │
   ▼
Output: Excel ranqueado + gráfico payoff + tabela no terminal
```

Três métodos de probabilidade de exercício e combinação conservadora
`max(prob_d2, prob_empirica)`. Greeks por Black-Scholes europeu.

---

## 4. Parâmetros de input e output

### Inputs (`config.toml` → `Config`, `options/config.py:16-70`)

| Grupo | Parâmetros |
|---|---|
| Universo | `lista_ativos`, `top_n` |
| Risco/mercado | `prob_exerc_max`, `taxa_livre_risco`, `dividend_yield` (único ou por ativo) |
| Modelos | `usar_prob_d2`, `usar_prob_mc`, `usar_prob_empirica`, `periodo_historico`, `min_amostras_empirica`, `mu`, `n_simulacoes`, `seed`, `batch_size` |
| Prêmio/convenção | `usar_premio` (bid/ask/lastPrice/mid), `dias_ano`, `min_dias`, `max_dias` |
| Custos | `tamanho_contrato`, `custo_compra`, `custo_venda`, `custo_exercicio` |
| Dados | `modo_offline`, `salvar_mock`, `pasta_mock`, `usar_cache`, `cache_ttl_horas`, `pasta_cache` |
| Score | `peso_theta`, `peso_vega` |
| Saída | `arquivo_excel`, `preco_medio_aquisicao` |

### Outputs

- **Excel** (`top_opcoes_covered_call.xlsx`): ranking por ativo com `strike`,
  `premio`, `expiration`, `prob_exercicio`, `prob_empirica`,
  `prob_exercicio_final`, greeks, `fonte_vol`, `risco_atribuicao_antecipada`,
  `retorno_anualizado_pct`/`_liquido`, liquidez e `score_venda`.
- **Gráfico** `payoff_<ATIVO>.png` da melhor opção geral.
- **Backtest**: nº de trades, retorno médio/anualizado, taxa de exercício, taxa
  de acerto e comparação com buy & hold.

---

## 5. Funcionalidades — úteis vs. pouco úteis no cenário atual

### ✅ Úteis (manter)
Probabilidade d2 e empírica · greeks delta/theta/vega · filtros de liquidez ·
score/ranking · saída em Excel · gráfico de payoff · cache/retry · CLI + config
declarativa · modo offline (mock) · multi-ativo · backtest (com ressalvas da §7).

### ⚠️ Inertes / pouco úteis hoje (candidatos a remoção ou simplificação)

- **Monte Carlo — calculado mas nunca usado.** `prob_exercicio_mc` é estimado a
  alto custo (50 000 simulações × nº de contratos, `pipeline.py:106-114`) e
  **não entra** no `prob_exercicio_final` nem no `score_venda` — o ranking usa
  apenas `prob_exercicio_final` (`ranking.py:42-47`). Pior: com `mu=0.0` (default)
  o MC **não é risk-neutral**, então produz um número inconsistente com o d2 e sem
  propósito. Arrasta consigo os parâmetros `mu`, `n_simulacoes`, `batch_size`,
  `seed` (do MC) e `usar_prob_mc`. **Candidato nº 1 a remoção.**
- **`gamma` e `rho`** — calculados e exportados, sem uso em score ou filtro;
  apenas ruído no output para um gestor.
- **`peso_theta` / `peso_vega` = 0.0 por padrão** — os fatores theta/vega só
  afetam o score se o usuário configurar pesos; por padrão são decorativos.
- **`t1.py` / `functions.py`** — shims de compatibilidade legados. Úteis apenas
  se houver notebooks (Databricks) dependendo da API antiga; caso contrário, são
  cruft a depreciar.

---

## 6. Achados de rigor quantitativo (divergências e fragilidades)

| # | Achado | Onde | Impacto |
|---|---|---|---|
| A | **Score README ↔ código:** o README diz `retorno_anualizado_liquido × (1-prob)` (README:18), mas o código usa `retorno_anualizado_pct` **bruto** (`ranking.py:43`). O líquido é calculado (`ranking.py:21`) e descartado. | `ranking.py:42-47` | Alto — custos de corretagem do cliente não entram no ranking |
| B | **Filtro README ↔ código:** README cita `premio_liquido > 0` (README:29); o código filtra `retorno_anualizado_pct > 0`. | `ranking.py:23-27` | Médio — documentação incorreta |
| C | **Prob. empírica com janelas sobrepostas:** `precos.shift(-janela)/precos - 1` gera amostras autocorrelacionadas, inflando o nº efetivo de amostras e enviesando a probabilidade. | `empirical.py:22` | Médio — confiança no número empírico |
| D | **Mistura de medidas:** `max(prob_d2 [risk-neutral], prob_empirica [mundo real])` combina probabilidades de medidas distintas. Pragmático/conservador, mas heterogêneo. | `pipeline.py:147-153` | Baixo — premissa a documentar |
| E | **Exercício americano tratado como europeu:** d2/greeks europeus; early assignment só como flag heurística (`delta≥0.70 & q>0`). Subestima exercício em calls com dividendo. | `pipeline.py:127-130` | Médio — relevante p/ ações com dividendo |
| F | **Cost basis ignorado na seleção:** `preco_medio_aquisicao` só alimenta o gráfico, não o ranking. No cenário "call sobre posição existente", vender strike abaixo do preço médio do cliente **trava prejuízo** se exercido — o ranking não enxerga isso. | `report.py` / `ranking.py` | **Alto — gap central frente ao cenário** |
| G | **Divisão sem guarda:** `retorno_anualizado_pct = ... * (dias_ano / dias_vencimento)`; com o default `t_min=0` da função, `dias_vencimento=0` causaria divisão por zero. A `Config` protege com `min_dias=7`, mas a função pública não. | `pipeline.py:79` | Baixo — robustez |
| H | **Filtro só OTM:** `distancia_strike_pct > 0` exclui ATM/ITM; buy-write defensivo às vezes usa ITM (mais prêmio/proteção). | `ranking.py:24` | Baixo — limitação de escopo |

---

## 7. Backtest — alcance e limitações

O backtest (`options/backtest.py`) é **baseado em modelo**: precifica o prêmio por
Black-Scholes com a volatilidade realizada de cada data, define o strike por uma
distância fixa e mantém até o vencimento. É útil como sanity-check da heurística de
strike, mas:

- **não usa o `score`/lógica real de seleção** que o produto entrega — valida um
  strike fixo, não o ranking;
- **não modela spread bid/ask nem custos**;
- **não usa o IV de mercado** (apenas vol realizada).

Há, portanto, um gap entre o que o backtest testa e o que o produto entrega.

---

## 8. Próximos passos propostos (foco: rigor + limpeza)

### P0 — Rigor, baixo risco
1. **Decidir bruto vs. líquido no score** (recomendado: **líquido**) e alinhar
   `ranking.py` ↔ README. *Req:* ajustar o cálculo do `score_venda` + atualizar/
   adicionar teste em `tests/test_pipeline_e2e.py`.
2. **Corrigir a divergência do filtro** documentado (A/B). *Req:* alinhar
   README e código (texto + filtro).
3. **Blindar a divisão por `dias_vencimento`** (garantir `T>0` / `dias_vencimento>0`)
   em `pipeline.py`. *Req:* guarda + teste de borda.
4. **Documentar premissas** (D mistura de medidas, E europeu vs. americano) no
   README.

### P0 — Limpeza
5. **Remover o Monte Carlo morto** (lógica em `pipeline.py`, parâmetros de config
   `mu`/`n_simulacoes`/`batch_size`/`usar_prob_mc`, arquivo `models/monte_carlo.py`
   e `tests/test_monte_carlo.py`). Alternativa: integrá-lo ao `prob_final` com
   `mu=r`. **Recomendado: remover.** *Req:* refator + ajustar testes, README e
   `config.toml`.
6. **Avaliar remover/agrupar `gamma` e `rho`** do output. *Req:* `report.py`.
7. **Decidir destino de `t1.py`/`functions.py`** — confirmar se há dependência
   externa (Databricks) antes de depreciar.

### P1 — Rigor alinhado ao cenário de carteiras
8. **Incorporar o cost basis na seleção:** penalizar/sinalizar no ranking calls
   com `strike < preco_medio_aquisicao` (evita travar prejuízo em posições
   existentes). *Req:* usar `Config.preco_medio_aquisicao` em `ranking.py`.
9. **Separar os modos covered call (posição existente) vs. buy-write (nova
   oportunidade)** no output: capital exigido por contrato, retorno sobre capital
   e breakeven distintos.
10. **Prob. empírica:** usar janelas não-sobrepostas ou corrigir a
    autocorrelação; documentar o método.
11. **Tornar o filtro OTM parametrizável** (permitir ATM/ITM opcionalmente).

### P2 — Rigor adicional (registrar, fora do foco imediato)
12. Modelar **exercício americano** (binomial / Barone-Adesi-Whaley) para ações
    com dividendo.
13. **Backtest mais fiel:** selecionar o strike pelo score real e incluir
    spread/custos.

---

## 9. Quadro de priorização

| Iniciativa | Impacto | Esforço | Prioridade |
|---|---|---|---|
| (5) Remover Monte Carlo morto | Alto | Baixo | **P0** |
| (1) Score bruto→líquido + alinhar README | Alto | Baixo | **P0** |
| (2) Corrigir filtro documentado | Médio | Baixo | **P0** |
| (3) Guarda de divisão | Baixo | Baixo | **P0** |
| (4) Documentar premissas | Médio | Baixo | **P0** |
| (8) Cost basis na seleção | Alto | Médio | **P1** |
| (9) Modos covered call vs. buy-write | Alto | Médio | **P1** |
| (10) Empírica sem sobreposição | Médio | Médio | **P1** |
| (11) Filtro OTM parametrizável | Médio | Baixo | **P1** |
| (6) Remover gamma/rho | Baixo | Baixo | **P1** |
| (7) Depreciar shims legados | Baixo | Baixo | **P1** |
| (12) Exercício americano | Médio | Alto | **P2** |
| (13) Backtest fiel | Médio | Alto | **P2** |

---

*Avaliação baseada no estado do repositório em 2026-06-02 (branch
`claude/cool-newton-5Rsdf`).*
