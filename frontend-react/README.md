# Analytical-Force — Painel (React)

Painel web do agente Analytical-Force. Substitui o antigo `frontend.html`
(single-file) por um app React + Vite, mantendo o mesmo contrato com a API
(FastAPI): a URL do Space e a `X-API-Key` continuam guardadas no
`localStorage` do navegador — nenhum segredo fica embutido no build.

## Telas

Dashboard, Oportunidades, Leads, Tarefas, Satisfação, Cancelamentos, Alertas,
Tendências, Relatório e Configuração (incluindo o cadastro de e-mails em
cópia — Cc — do relatório diário, persistido no Turso).

## Desenvolvimento local

```bash
npm install
npm run dev
```

Abre em `http://localhost:5173`. Configure a URL da API e a `X-API-Key` na
tela **Configuração** (mesmo comportamento do `frontend.html` anterior).

## Build de produção

```bash
npm run build
```

Gera `dist/`. Em produção, o backend (FastAPI) serve esse `dist/` como
arquivos estáticos no mesmo container do Hugging Face Space — ver
`src/delivery/static_app.py` e o `Dockerfile` na raiz do projeto (etapa de
build Node + cópia do `dist/` para a imagem final). Isso evita precisar de
um segundo host/CORS: a API e o painel passam a responder na mesma porta.
