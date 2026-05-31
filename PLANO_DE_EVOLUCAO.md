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

### Fase 0 — Fundação de engenharia ✅ concluída
**Objetivo:** criar a rede de segurança antes de qualquer refatoração.

- [x] `pyproject.toml` (packaging, ruff, mypy, pytest configurados).
- [x] Suíte de **testes unitários** dos modelos usando os mocks já existentes:
  - `prob d2` contra valores analíticos conhecidos;
  - Monte Carlo convergindo para `d2` quando `mu = r`;
  - empírica contra um histórico sintético controlado;
  - pipeline `preparar_calls_para_modelo` validado com os dados mock.
- [x] `ruff` (lint + format) e `mypy`.
- [x] **CI no GitHub Actions**: lint + mypy + testes em cada PR.
- [x] Logging estruturado (`logging`) substituindo os `print()` da biblioteca.

**Pronto:** `pytest` verde no CI e cobertura dos modelos numéricos.

---

### Fase 1 — Arquitetura e configuração ✅ concluída
**Objetivo:** tornar o código modular e a configuração declarativa.

- [x] Reorganizado em pacote `options/` (config, data, models, ranking, report,
  runner, cli).
- [x] **Configuração via arquivo** (`config.toml`) + override por CLI,
  substituindo as constantes de `t1.py`. Validação de tipos e faixas.
- [x] **CLI** (`argparse`): `options --config config.toml`, `--offline`,
  `--salvar-mock`, `--ativos IBIT,AAPL`, `--sem-cache`.
- [x] Camada de **dados com cache** (parquet em disco, TTL) e retry/back-off
  para o yfinance; interface `ProvedorDados` permitindo trocar a fonte.

**Pronto:** fluxo completo roda via CLI lendo o arquivo de config, sem editar
código. Shims (`t1.py`/`functions.py`) preservam compatibilidade.

---

### Fase 2 — Rigor quantitativo ✅ concluída
**Objetivo:** aumentar a confiança nos números e no score.

- [x] **Greeks** (delta, gamma, theta, vega, rho) por contrato —
  `options/models/greeks.py`, validados por diferenças finitas.
- [x] **Early assignment / dividend yield por ativo**: `dividend_yield` aceita
  valor único ou dict por ativo (`Config.dividend_para`); flag
  `risco_atribuicao_antecipada` para calls com dividendo e delta alto.
- [x] **Volatilidade histórica como fallback**: `options/models/volatility.py`;
  o pipeline usa IV implícita e cai para vol realizada quando ausente
  (coluna `fonte_vol`).
- [x] **Backtest do score**: `options/backtest.py` + subcomando
  `options backtest`; reporta retorno realizado, taxa de exercício, taxa de
  acerto e comparação com buy & hold.
- [ ] *(futuro)* IV smile/term-structure completa e análise de sensibilidade
  multivariada de `r`/`mu`/IV.

**Pronto:** Greeks e flags no output, backtest reproduzível via CLI, 41 testes
verdes.

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
