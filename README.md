---
title: Analytical Force
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Agente analítico diário Salesforce + Turso
---

<!-- O bloco acima é o metadata do Hugging Face Spaces. Não remova ao publicar no HF. -->

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2563eb,100:4f46e5&height=210&section=header&text=Analytical-Force&fontSize=54&fontColor=ffffff&fontAlignY=36&desc=Salesforce%20%E2%86%92%20IA%20%E2%86%92%20Diagn%C3%B3stico%20executivo%20di%C3%A1rio&descSize=18&descAlignY=56" width="100%" alt="Analytical-Force"/>

<img src="https://readme-typing-svg.demolab.com?font=Segoe+UI&weight=600&size=22&duration=3200&pause=700&color=2563EB&center=true&vCenter=true&width=720&lines=Python+calcula.;IA+interpreta.;Turso+armazena.;Salesforce+fornece+os+dados." alt="typing" />

<br/><br/>

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Salesforce](https://img.shields.io/badge/Salesforce-00A1E0?style=for-the-badge&logo=salesforce&logoColor=white)
![Turso](https://img.shields.io/badge/Turso%20%2F%20libSQL-4FF8D2?style=for-the-badge&logo=turso&logoColor=black)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)
![ClickUp](https://img.shields.io/badge/ClickUp-7B68EE?style=for-the-badge&logo=clickup&logoColor=white)
![Gmail API](https://img.shields.io/badge/Gmail%20API-EA4335?style=for-the-badge&logo=gmail&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<!-- Badges dinâmicos: ajuste o caminho do repositório se o seu for diferente. -->
![Último commit](https://img.shields.io/github/last-commit/ViniciusKhan/Analytical-Force?style=flat-square&color=2563eb)
![Linguagem](https://img.shields.io/github/languages/top/ViniciusKhan/Analytical-Force?style=flat-square)
![Tamanho](https://img.shields.io/github/repo-size/ViniciusKhan/Analytical-Force?style=flat-square)
![Status](https://img.shields.io/badge/status-em%20produção-16a34a?style=flat-square)

</div>

---

<div align="center">

### 🤖 Transforma dados do **Salesforce** em diagnóstico executivo diário, alertas de risco e ações recomendadas — com IA, banco Turso e entrega por e-mail e ClickUp.

</div>

> **Princípio central** &nbsp;·&nbsp; **Python calcula** · **IA interpreta** · **Turso armazena** · **Salesforce fornece os dados.**
> A IA **nunca** calcula indicadores — recebe um JSON com métricas prontas e produz a narrativa. O Salesforce opera em **modo somente leitura**.

## 🧭 Índice

<table>
<tr>
<td>

- [✨ Recursos](#-recursos)
- [🏗️ Arquitetura](#️-arquitetura)
- [🔄 Fluxo diário](#-fluxo-diário)
- [🧰 Stack](#-stack)

</td>
<td>

- [📁 Estrutura](#-estrutura-do-projeto)
- [⚙️ Configuração](#️-configuração-env)
- [🧩 Guia de replicação](#-guia-de-replicação)
- [▶️ Rodar local](#️-como-rodar-local)

</td>
<td>

- [🚀 Deploy (HF Spaces)](#-deploy-online-hugging-face-spaces)
- [🌐 API](#-api)
- [🖥️ Front-end](#️-front-end)
- [👨‍💻 Desenvolvedor](#-desenvolvedor)

</td>
</tr>
</table>

---

## ✨ Recursos

| | Recurso | Descrição |
|---|---------|-----------|
| 🔐 | **Autenticação** | Salesforce via OAuth Refresh Token (somente leitura) |
| 📈 | **Métricas** | Leads, oportunidades, tarefas, satisfação, cancelamentos + variações (dia anterior / média 7 dias) |
| 🚨 | **Motor de risco** | Alertas `low` / `medium` / `high` com ação recomendada |
| 🤖 | **IA** | Narrativa executiva (Hugging Face Inference · Ollama · Template) |
| 🗄️ | **Persistência** | Turso/libSQL — métricas, alertas, relatórios e snapshots |
| 📬 | **Entrega** | Arquivo `.md`, e-mail (Gmail API) e tarefas no ClickUp com links |
| 🌐 | **API + Front** | FastAPI + painel web multi-tela (lê o banco por GET) |

---

## 🏗️ Arquitetura

```mermaid
flowchart LR
    SF[("☁️ Salesforce<br/>somente leitura")] -->|OAuth + SOQL| EX[Extratores<br/>pandas]
    EX --> MET[Motor de métricas]
    MET --> RISK[Motor de risco]
    MET --> TURSO[("🗄️ Turso / libSQL")]
    RISK --> TURSO
    MET --> PB[Prompt Builder] --> IA{{"🤖 IA"}}
    IA --> REP[Relatório Markdown]
    MET --> REP
    RISK --> REP
    REP --> ENT[Entrega]
    ENT --> FILE[📄 Arquivo]
    ENT --> MAIL[📧 Gmail API]
    ENT --> CU[✅ ClickUp]
    FRONT[["🖥️ Front-end"]] <-->|REST| API[["🌐 API FastAPI"]] --> AG[Agente] --> EX
```

---

## 🔄 Fluxo diário

```mermaid
sequenceDiagram
    participant F as Front / Agendador
    participant API as API
    participant AG as Agente
    participant SF as Salesforce
    participant T as Turso
    participant IA as IA
    F->>API: POST /run (data)
    API->>AG: executar(dia)
    AG->>SF: OAuth + SOQL (leads, opps, tasks, satisfação, cancelamentos)
    SF-->>AG: DataFrames
    AG->>AG: métricas + comparações + riscos
    AG->>T: salva métricas, alertas, relatório, snapshots
    AG->>IA: prompt (JSON de métricas)
    IA-->>AG: narrativa executiva
    AG-->>API: relatório + alertas + destaques
    API-->>F: JSON (KPIs, links, relatório)
```

---

## 🧰 Stack

<div align="center">

<img height="44" src="https://cdn.simpleicons.org/python/3776AB" alt="Python" title="Python"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/fastapi/009688" alt="FastAPI" title="FastAPI"/>&nbsp;&nbsp;&nbsp;
<img height="34" src="https://upload.wikimedia.org/wikipedia/commons/f/f9/Salesforce.com_logo.svg" alt="Salesforce" title="Salesforce"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/turso/4FF8D2" alt="Turso" title="Turso"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/huggingface/FFD21E" alt="Hugging Face" title="Hugging Face"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/pandas/150458" alt="pandas" title="pandas"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/clickup/7B68EE" alt="ClickUp" title="ClickUp"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/gmail/EA4335" alt="Gmail" title="Gmail"/>&nbsp;&nbsp;&nbsp;
<img height="44" src="https://cdn.simpleicons.org/docker/2496ED" alt="Docker" title="Docker"/>

</div>

---

## 📁 Estrutura do projeto

```
analytical-force/
├── api.py                 # API FastAPI (deploy online) + serve o painel React em "/"
├── main.py                # CLI
├── frontend-react/        # Painel web (React + Vite) — ver frontend-react/README.md
├── frontend.html          # [LEGADO] painel single-file anterior; mantido apenas de referência
├── Dockerfile             # Imagem para HF Spaces (build Node do painel + imagem Python)
├── requirements.txt       # Deps (local)  ·  requirements-hf.txt (Space)
├── .env.example           # Modelo de variáveis (sem segredos)
├── scripts/               # test_salesforce_oauth · test_gmail_oauth · clean_db
└── src/
    ├── config/   database/   salesforce/   analytics/
    ├── models/   agent/      delivery/     utils/
```

---

## ⚙️ Configuração (.env) 

Copie `.env.example` → `.env`. **Nunca** faça commit do `.env`.

| Variável | Descrição |
| -------- | --------- |
| `SALESFORCE_AUTH_MODE` | `oauth_refresh_token` (padrão) |
| `SALESFORCE_INSTANCE_URL` · `_CLIENT_ID` · `_CLIENT_SECRET` · `_REFRESH_TOKEN` | OAuth Salesforce |
| `TURSO_DATABASE_URL` · `TURSO_AUTH_TOKEN` | Banco libSQL/Turso |
| `MODEL_PROVIDER` | `hf_inference` · `ollama` · `transformers` · `template` |
| `HF_INFERENCE_MODEL` · `HF_TOKEN` | IA hospedada |
| `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN/SENDER` | E-mail (Gmail API) |
| `CLICKUP_API_TOKEN` · `CLICKUP_LIST_ID` · `CLICKUP_ASSIGNEE_ID` | Tarefas |
| `OPPORTUNITY_MIN_AMOUNT` | Valor mínimo de oportunidade a analisar |

> Lista completa e comentada em [`.env.example`](.env.example).

---

## 🧩 Guia de replicação

<details>
<summary><b><img src="https://upload.wikimedia.org/wikipedia/commons/f/f9/Salesforce.com_logo.svg" height="14"/> &nbsp;1. Salesforce (OAuth Refresh Token)</b></summary>

1. **Setup → App Manager → New Connected App.**
2. Ative **Enable OAuth Settings**. Callback: `https://login.salesforce.com/services/oauth2/callback`.
3. Scopes: **`api`** e **`refresh_token, offline_access`**.
4. Copie **Consumer Key** (`CLIENT_ID`) e **Consumer Secret** (`CLIENT_SECRET`).
5. Gere o **Refresh Token** (fluxo OAuth) e preencha o `.env`.
6. Valide: `python scripts/test_salesforce_oauth.py`

> 💡 Use um **usuário de integração somente leitura**. O agente só faz `SELECT` (SOQL).
</details>

<details>
<summary><b><img src="https://cdn.simpleicons.org/turso/4FF8D2" height="14"/> &nbsp;2. Turso (banco)</b></summary>

```bash
turso db create analytical-force
turso db show analytical-force --url      # -> TURSO_DATABASE_URL
turso db tokens create analytical-force   # -> TURSO_AUTH_TOKEN
```
As tabelas são criadas automaticamente (migrations idempotentes) na 1ª execução.
</details>

<details>
<summary><b><img src="https://cdn.simpleicons.org/huggingface/FFD21E" height="14"/> &nbsp;3. IA — Hugging Face Inference</b></summary>

1. Token em **huggingface.co/settings/tokens** com permissão **Make calls to Inference Providers**.
2. No `.env`: `MODEL_PROVIDER=hf_inference`, `HF_INFERENCE_MODEL=Qwen/Qwen2.5-7B-Instruct`, `HF_TOKEN=...`.

> Alternativas: `ollama` (local), `transformers` (CPU) ou `template` (sem IA, instantâneo).
</details>

<details>
<summary><b><img src="https://cdn.simpleicons.org/gmail/EA4335" height="14"/> &nbsp;4. Gmail API (e-mail)</b></summary>

> O HF Spaces bloqueia SMTP — por isso o e-mail online usa a **Gmail API (HTTP)**.

1. Google Cloud Console → ative a **Gmail API**.
2. Tela de consentimento (**External**) → adicione seu e-mail em **Test users**.
3. Credencial **OAuth Client (Web)** com redirect `https://developers.google.com/oauthplayground`.
4. No **OAuth Playground**, autorize `https://www.googleapis.com/auth/gmail.send` e gere o **refresh token**.
5. `.env`: `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` + `GMAIL_SENDER` + `REPORT_RECIPIENT_EMAIL`.
6. Valide: `python scripts/test_gmail_oauth.py`
</details>

<details>
<summary><b><img src="https://cdn.simpleicons.org/clickup/7B68EE" height="14"/> &nbsp;5. ClickUp (tarefas)</b></summary>

1. ClickUp → **Settings → Apps → API Token** (`pk_...`).
2. **List ID** pela URL: `app.clickup.com/.../li/<LIST_ID>`.
3. `.env`: `CLICKUP_API_TOKEN`, `CLICKUP_LIST_ID`, `CLICKUP_ASSIGNEE_ID`, `ENABLE_CLICKUP_AUTO_CREATE=true`.
</details>

---

## ▶️ Como rodar (local)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # preencha

python main.py --check            # valida configuração
python main.py --date 2026-06-22  # executa o pipeline
uvicorn api:app --port 7860       # API + Swagger em /docs
```

Painel (React), em outro terminal:

```bash
cd frontend-react
npm install
npm run dev                       # http://localhost:5173 — aponte para a API (aba Configuração)
```

Em produção (Docker/Hugging Face), o build do painel (`npm run build`) já roda
dentro da imagem — não precisa rodar `npm` manualmente; a API serve o
`frontend-react/dist` em `/`.

---

## 🚀 Deploy online (Hugging Face Spaces)

Space tipo **Docker** (build leve). Em **Settings → Variables and secrets**:

| 🔒 Secrets | ⚙️ Variables |
| --------- | ----------- |
| `SALESFORCE_CLIENT_ID/SECRET/REFRESH_TOKEN` | `SALESFORCE_AUTH_MODE=oauth_refresh_token` |
| `TURSO_AUTH_TOKEN` · `HF_TOKEN` | `SALESFORCE_INSTANCE_URL` · `SALESFORCE_API_VERSION=64.0` |
| `GMAIL_*` · `CLICKUP_API_TOKEN` | `TURSO_DATABASE_URL` · `MODEL_PROVIDER=hf_inference` |
| `APP_API_TOKEN` (protege o `/run`) | `HF_INFERENCE_MODEL` · `CLICKUP_LIST_ID` … |

---

## 🌐 API

| Método | Rota | Descrição |
| ------ | ---- | --------- |
| `GET` | `/` | Painel React (`frontend-react/dist`), quando compilado |
| `GET` | `/api` | Página de instruções da API |
| `GET` | `/health` | Saúde |
| `GET` | `/config/check` | Validação (sem segredos) |
| `GET` | `/config/email-cc` | Lista e-mails em cópia (Cc) do relatório |
| `POST` | `/config/email-cc` | Cadastra um e-mail em cópia |
| `DELETE` | `/config/email-cc/{email}` | Remove um e-mail em cópia |
| `POST` | `/run` | Executa o pipeline |
| `GET` | `/run?date=` | Executa pelo navegador |
| `GET` | `/days` | Datas com relatório salvo |
| `GET` | `/day/{data}` | Todos os dados de um dia (do banco) |
| `GET` | `/metrics/{data}` | Métricas de um dia |
| `GET` | `/history?days=7` | Série histórica |
| `GET` | `/docs` | Swagger |

Header `X-API-Key` quando `APP_API_TOKEN` está definido.

---

## 🖥️ Front-end

O painel oficial é o **`frontend-react/`** (React + Vite) — ver
[`frontend-react/README.md`](frontend-react/README.md). Mesmas telas do painel
anterior: barra lateral, seletor de dia que lê o banco por `GET /day`, tema
claro/escuro, KPIs, filtro de alertas, gráfico de severidade, **Registros do
dia** com links ao Salesforce, **Tendências** (histórico do Turso), relatório
em abas e, agora, cadastro de **e-mails em cópia (Cc)** do relatório diário
(persistidos no Turso, sem precisar de redeploy).

Em produção, o backend serve o build do painel em `/` (mesmo Space/porta,
sem CORS entre os dois). O `frontend.html` single-file anterior foi mantido
no repositório apenas como referência histórica — não recebe mais atualizações.

---

## 🗄️ Banco de dados

Tabelas (Turso/libSQL): `agent_runs`, `daily_metrics`, `daily_alerts`,
`daily_reports`, `salesforce_snapshots`, `object_mapping`, `agent_config`.
Gravações **idempotentes** por dia. Manutenção: `python scripts/clean_db.py --snapshots`.

---

## 🔒 Segurança

- Sem segredos no código (apenas `.env` / Secrets do Space).
- Salesforce **somente leitura** (apenas `SELECT`).
- Logs mascaram senhas/tokens · `/run` protegível por `APP_API_TOKEN`.

---

## 👨‍💻 Desenvolvedor

<div align="center">

<img src="https://avatars.githubusercontent.com/u/66964047?s=400&u=ef769a81cacd810da6761e08129a1860dd11e36c&v=4" width="110" height="110" style="border-radius:50%" alt="Vinicius de Souza Santos"/>

### Vinicius de Souza Santos
**Criador e desenvolvedor do Analytical-Force**

[![GitHub](https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/ViniciusKhan)
[![Hugging Face](https://img.shields.io/badge/🤗%20Space-FFD21E?style=for-the-badge)](https://huggingface.co/spaces/ViniciusKhan/analytical_force)

</div>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:4f46e5,100:2563eb&height=110&section=footer" width="100%" alt=""/>

<div align="center"><sub>Feito com Python · Salesforce · Turso · Hugging Face &nbsp;·&nbsp; © Vinicius de Souza Santos</sub></div>
