# Plano de Evolução — Options

Documento de planejamento técnico para a evolução do projeto de análise e
ranking de **covered calls**. Organiza o trabalho em fases com objetivos,
entregáveis e critérios de pronto, partindo do estado atual do código.

---

## 1. Diagnóstico do estado atual

### O que já existe e funciona bem
- **Núcleo quantitativo sólido**: três modelos de probabilidade de exercício
  (Black-Scholes `d2`, Monte Carlo em batch e empírico histórico) com
  combinação conservadora `max(d2, empírica)`.
- **Vetorização**: cálculos em NumPy/pandas, Monte Carlo em batches para
  controlar memória.
- **Multi-ativo** com top-N por papel e ranking por `score_venda`.
- **Modo offline** com dados mock (CSV/JSON), bom para testes e demonstração.
- **Saídas úteis**: Excel ranqueado + gráfico de payoff da covered call.

### Limitações e dívidas técnicas
| Área | Limitação atual |
|---|---|
| Configuração | Parâmetros hardcoded no topo de `t1.py`; nenhuma validação |
| Arquitetura | `functions.py` concentra dados, modelos, relatório e gráfico |
| Testes | **Inexistentes** — nenhuma garantia contra regressões nos modelos |
| CLI / API | Sem interface de linha de comando nem função reutilizável de alto nível |
| Empacotamento | Sem `pyproject.toml`, sem instalação como pacote |
| Robustez de dados | Depende 100% do yfinance; sem cache, retry ou rate-limit |
| Observabilidade | `print()` espalhado; sem logging estruturado nem níveis |
| Tipagem | Sem type hints nem checagem estática |
| CI | Sem pipeline de lint/testes automatizado |
| Rigor quant | Exercício americano tratado como europeu; dividend yield único para todos os ativos; sem early-assignment; score não validado por backtest |
| Estratégias | Apenas covered call; sem cash-secured put nem outras estruturas |

---

## 2. Princípios norteadores
1. **Não quebrar o núcleo quant** — evoluir com testes que travam o comportamento atual antes de refatorar.
2. **Separação de responsabilidades** — dados, modelos, ranking e apresentação em módulos distintos.
3. **Reprodutibilidade** — seeds, cache versionado e configuração declarativa.
4. **Incremental e entregável** — cada fase produz algo usável de ponta a ponta.

---

## 3. Roadmap por fases

### Fase 0 — Fundação de engenharia (1–2 semanas)
**Objetivo:** criar a rede de segurança antes de qualquer refatoração.

- [ ] `pyproject.toml` (packaging, ruff, mypy, pytest configurados).
- [ ] Suíte de **testes unitários** dos modelos usando os mocks já existentes:
  - `prob d2` contra valores analíticos conhecidos;
  - Monte Carlo convergindo para `d2` quando `mu = r`;
  - empírica contra um histórico sintético controlado;
  - pipeline `preparar_calls_para_modelo` com snapshot do output mock.
- [ ] `ruff` (lint + format) e `mypy` em modo gradual.
- [ ] **CI no GitHub Actions**: lint + mypy + testes em cada PR.
- [ ] Logging estruturado (`logging`) substituindo os `print()` da biblioteca.

**Pronto quando:** `pytest` verde no CI e cobertura dos modelos numéricos.

---

### Fase 1 — Arquitetura e configuração (1–2 semanas)
**Objetivo:** tornar o código modular e a configuração declarativa.

- [ ] Reorganizar em pacote `options/`:
  ```
  options/
  ├── config.py        # dataclass/pydantic com validação dos parâmetros
  ├── data/            # providers (yfinance, mock) atrás de uma interface
  ├── models/          # d2, monte_carlo, empirica, payoff
  ├── ranking.py       # filtros + score + top-N
  ├── report.py        # Excel + gráficos
  └── cli.py           # entrypoint
  ```
- [ ] **Configuração via arquivo** (`config.yaml`/`.toml`) + override por CLI,
  substituindo as constantes de `t1.py`. Validação de tipos e faixas.
- [ ] **CLI** (`argparse`/`typer`): `options run --config config.yaml`,
  `--offline`, `--save-mock`, `--ativos IBIT,AAPL`.
- [ ] Camada de **dados com cache** (parquet em disco, TTL) e retry/back-off
  para o yfinance; interface `DataProvider` permitindo trocar a fonte.

**Pronto quando:** rodar o fluxo completo via CLI lendo um arquivo de config,
sem editar código.

---

### Fase 2 — Rigor quantitativo (2–3 semanas)
**Objetivo:** aumentar a confiança nos números e no score.

- [ ] **Greeks** (delta, gamma, theta, vega) por contrato — delta como proxy
  rápido e intuitivo de probabilidade de exercício.
- [ ] **Exercício americano / early assignment**: alerta de risco de
  atribuição antecipada perto de ex-dividendo; dividend yield **por ativo**.
- [ ] **Modelagem de volatilidade**: usar a IV smile/term-structure real em vez
  de uma IV pontual; opção de vol histórica como fallback.
- [ ] **Backtest do score**: validar se `score_venda` historicamente seleciona
  calls com melhor retorno ajustado ao risco; reportar métricas
  (retorno realizado, taxa de exercício, drawdown).
- [ ] **Sensibilidade**: análise de como o ranking muda com `r`, `mu`, IV.

**Pronto quando:** relatório de backtest reproduzível e Greeks no output.

---

### Fase 3 — Estratégias e portfólio (2–3 semanas)
**Objetivo:** ir além da covered call isolada.

- [ ] **Cash-secured puts** (estrutura simétrica, grande reuso do núcleo).
- [ ] **Visão de portfólio**: alocação entre papéis, capital exigido por
  contrato, exposição agregada (delta total, concentração por setor).
- [ ] **Rolagem**: sugerir roll de contratos próximos do vencimento/ITM.
- [ ] **Filtros configuráveis** de liquidez e perfil de risco por usuário.

**Pronto quando:** o usuário consegue ranquear covered calls e CSPs no mesmo
fluxo e ver o impacto no portfólio.

---

### Fase 4 — Experiência e distribuição (2–4 semanas)
**Objetivo:** tornar o uso acessível e contínuo.

- [ ] **Dashboard interativo** (Streamlit): tabela ranqueada, payoff
  interativo, sliders de parâmetros.
- [ ] **Relatório agendado** (ex.: GitHub Action diária) gerando o ranking e
  publicando o Excel/HTML como artefato.
- [ ] **Persistência opcional** dos resultados (banco/parquet) para histórico e
  comparação temporal.
- [ ] Documentação de usuário e exemplos.

**Pronto quando:** usuário não-técnico consegue rodar e interpretar via UI.

---

## 4. Quadro de priorização

| Iniciativa | Impacto | Esforço | Prioridade |
|---|---|---|---|
| Testes + CI (Fase 0) | Alto | Baixo | **P0** |
| Config declarativa + CLI (Fase 1) | Alto | Médio | **P0** |
| Cache/retry de dados (Fase 1) | Médio | Baixo | **P1** |
| Greeks + dividendo por ativo (Fase 2) | Alto | Médio | **P1** |
| Backtest do score (Fase 2) | Alto | Alto | **P1** |
| Cash-secured puts (Fase 3) | Médio | Médio | **P2** |
| Dashboard (Fase 4) | Médio | Alto | **P2** |

---

## 5. Próximo passo recomendado
Começar pela **Fase 0**: introduzir `pyproject.toml`, escrever os primeiros
testes dos três modelos de probabilidade usando os dados mock já versionados
(`mock_IBIT_*`) e ligar o CI. Isso destrava com segurança todas as refatorações
seguintes sem risco de regressão no núcleo quantitativo.
