"""API HTTP (FastAPI) do Analytical-Force.

Expõe a execução do agente por API, para rodar 100% online (ex.: Hugging Face
Spaces tipo Docker) e ser acionado por um front-end.

Princípios:
- Toda a configuração vem de variáveis de ambiente (Secrets do Space).
- A execução é protegida por chave de API (cabeçalho ``X-API-Key``), pois
  dispara leitura no Salesforce e, opcionalmente, e-mail/ClickUp.
- O Salesforce continua somente leitura; nenhuma credencial é exposta.

Endpoints:
- ``GET  /``             painel React (frontend-react/dist), quando compilado.
- ``GET  /api``          página simples com instruções (info da API).
- ``GET  /health``       verificação de saúde.
- ``GET  /config/check`` validação da configuração (sem segredos).
- ``POST /run``          executa o pipeline diário (protegido por X-API-Key).
- ``GET  /docs``         documentação interativa (Swagger).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Validação simples de formato de e-mail (não substitui confirmação real de
# entrega — apenas evita cadastrar valores claramente inválidos).
_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

from src.agent.analytical_force_agent import AnalyticalForceAgent
from src.config import get_settings
from src.delivery.clickup_sender import criar_tarefas_de_alertas
from src.delivery.email_sender import enviar_relatorio_email
from src.utils.date_utils import parse_data
from src.utils.logger import get_logger

logger = get_logger("api")

app = FastAPI(
    title="Analytical-Force API",
    description="Agente analítico diário (Salesforce + Turso). Somente leitura.",
    version="1.0.0",
)

# CORS: libere os domínios do seu front em CORS_ORIGINS (separados por vírgula).
# Padrão "*" facilita testes; em produção, restrinja aos seus domínios.
_origens = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# Autenticação simples por chave de API
# ----------------------------------------------------------------------
def _exigir_token(x_api_key: str | None) -> None:
    """Valida o cabeçalho ``X-API-Key`` contra ``APP_API_TOKEN`` (se definido).

    Comportamento:
    - Se ``APP_API_TOKEN`` NÃO estiver definido: a API fica em "modo aberto"
      (sem autenticação). Registra um aviso — nesse caso, mantenha o Space
      como **Private** para não expor a execução publicamente.
    - Se estiver definido: exige o cabeçalho ``X-API-Key`` correspondente.
    """
    token = os.environ.get("APP_API_TOKEN", "").strip()
    if not token:
        logger.warning(
            "APP_API_TOKEN não definido: /run está SEM autenticação (modo aberto). "
            "Recomenda-se deixar o Space Private."
        )
        return
    if not x_api_key or x_api_key != token:
        raise HTTPException(status_code=401, detail="Chave de API inválida ou ausente.")


# ----------------------------------------------------------------------
# Modelos de requisição/resposta
# ----------------------------------------------------------------------
class RunRequest(BaseModel):
    """Parâmetros para execução do pipeline diário."""

    date: str | None = None  # YYYY-MM-DD; vazio = ontem
    send_email: bool = False  # envia e-mail (se SMTP configurado)
    create_clickup: bool = False  # cria tarefas no ClickUp (se habilitado)


class EmailCcRequest(BaseModel):
    """Corpo para cadastrar um e-mail em cópia (Cc) no relatório diário."""

    email: str


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/api", response_class=HTMLResponse)
def raiz() -> str:
    """Página com instruções básicas da API (o painel React vive em ``/``)."""
    return """\
<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Analytical-Force API</title>
<style>body{font-family:Arial,Helvetica,sans-serif;max-width:720px;margin:40px auto;
padding:0 16px;color:#0f172a;line-height:1.5}code{background:#f1f5f9;padding:2px 6px;
border-radius:6px}a{color:#1f4fb2}</style></head><body>
<h1>📊 Analytical-Force API</h1>
<p>Agente de inteligência analítica (Salesforce → métricas em Python → Turso →
relatório). Opera <strong>somente leitura</strong> no Salesforce.</p>
<p>O painel web fica em <a href="/">/</a> (React, quando compilado).</p>
<ul>
<li><code>GET /health</code> — verificação de saúde</li>
<li><code>GET /config/check</code> — validação da configuração (sem segredos)</li>
<li><code>POST /run</code> — executa o pipeline (corpo JSON)</li>
<li><code>GET /run?date=YYYY-MM-DD</code> — executa pelo navegador (mais fácil)</li>
<li><code>GET /metrics/{data}</code> — lê as métricas já salvas (rápido, sem reexecutar)</li>
<li><a href="/docs">/docs</a> — documentação interativa (Swagger)</li>
</ul>
<p>Se <code>APP_API_TOKEN</code> estiver definido, envie o cabeçalho
<code>X-API-Key: SEU_TOKEN</code> nas chamadas de <code>/run</code> e
<code>/metrics</code>.</p>
</body></html>"""


@app.get("/health")
def health() -> dict[str, str]:
    """Verificação simples de disponibilidade."""
    return {"status": "ok", "service": "analytical-force"}


@app.get("/config/check")
def config_check() -> dict[str, Any]:
    """Resumo seguro da configuração + validação (não expõe segredos)."""
    settings = get_settings()
    return {
        "resumo": settings.resumo_seguro(),
        "validacao": settings.validar_tudo(),
    }


@app.get("/config/email-cc")
def listar_email_cc(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Lista os e-mails cadastrados para receber cópia (Cc) do relatório."""
    _exigir_token(x_api_key)
    from src.database.repositories import ConfigRepository
    from src.database.turso_client import get_turso_client

    try:
        repo = ConfigRepository(get_turso_client())
        return {"emails_cc": repo.listar_emails_cc()}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao ler e-mails em cópia: {type(exc).__name__}: {exc}",
        )


@app.post("/config/email-cc")
def adicionar_email_cc(
    req: EmailCcRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Cadastra um e-mail em cópia (Cc) do relatório diário."""
    _exigir_token(x_api_key)
    email = req.email.strip().lower()
    if not _REGEX_EMAIL.match(email):
        raise HTTPException(status_code=400, detail=f"E-mail inválido: {req.email!r}")

    from src.database.repositories import ConfigRepository
    from src.database.turso_client import get_turso_client

    try:
        repo = ConfigRepository(get_turso_client())
        atuais = repo.listar_emails_cc()
        if email not in atuais:
            atuais.append(email)
        emails_cc = repo.definir_emails_cc(atuais)
        return {"emails_cc": emails_cc}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao cadastrar e-mail em cópia: {type(exc).__name__}: {exc}",
        )


@app.delete("/config/email-cc/{email}")
def remover_email_cc(
    email: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Remove um e-mail da lista de cópia (Cc) do relatório diário."""
    _exigir_token(x_api_key)
    from src.database.repositories import ConfigRepository
    from src.database.turso_client import get_turso_client

    try:
        repo = ConfigRepository(get_turso_client())
        restantes = [e for e in repo.listar_emails_cc() if e != email.strip().lower()]
        emails_cc = repo.definir_emails_cc(restantes)
        return {"emails_cc": emails_cc}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao remover e-mail em cópia: {type(exc).__name__}: {exc}",
        )


def _executar_pipeline(req: RunRequest) -> dict[str, Any]:
    """Executa o pipeline e devolve o JSON de resultado (com erros tratados)."""
    settings = get_settings()
    agente = AnalyticalForceAgent(settings)

    erros = agente.validar_prerequisitos()
    if erros:
        raise HTTPException(status_code=400, detail={"prerequisitos": erros})

    try:
        dia = parse_data(req.date) if req.date else None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Data inválida: {exc}")

    try:
        resultado = agente.executar(dia)
    except Exception as exc:  # rede/lib inesperada — resposta limpa, sem stacktrace
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao executar o agente: {type(exc).__name__}: {exc}",
        )
    if resultado.status != "success":
        raise HTTPException(status_code=502, detail=f"Execução falhou: {resultado.erro}")

    entregas: dict[str, Any] = {}
    if req.send_email and settings.email.is_configured:
        from src.database.repositories import ConfigRepository
        from src.database.turso_client import get_turso_client

        try:
            emails_cc = ConfigRepository(get_turso_client()).listar_emails_cc()
        except Exception as exc:  # não deve impedir o envio ao destinatário principal
            logger.warning("Falha ao ler e-mails em cópia no Turso: %s", type(exc).__name__)
            emails_cc = []

        entregas["email_enviado"] = enviar_relatorio_email(
            config=settings.email,
            assunto=f"Analytical-Force — Relatório {resultado.dia}",
            report_date=str(resultado.dia),
            metrics=resultado.metricas,
            alerts=resultado.alertas,
            report_markdown=resultado.markdown,
            highlights=resultado.destaques,
            cc_emails=emails_cc,
        )
    if req.create_clickup and settings.clickup.auto_create:
        entregas["clickup_tarefas"] = criar_tarefas_de_alertas(
            resultado.alertas,
            settings.clickup,
            settings.clickup.auto_create,
            instance_url=settings.salesforce.instance_url,
            report_date=str(resultado.dia),
        )

    return {
        "status": resultado.status,
        "date": str(resultado.dia),
        "provider": resultado.provider,
        "alerts_count": len(resultado.alertas),
        "alerts": [
            {
                "severity": a.get("severity"),
                "category": a.get("category"),
                "title": a.get("title"),
                "description": a.get("description"),
                "recommended_action": a.get("recommended_action"),
                "affected_records": a.get("affected_records") or [],
                "action_plan": a.get("action_plan"),
            }
            for a in resultado.alertas
        ],
        "metrics": resultado.metricas,
        "highlights": resultado.destaques,
        "report_markdown": resultado.markdown,
        "deliveries": entregas,
    }


@app.post("/run")
def run_post(
    req: RunRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Executa o pipeline diário (corpo JSON). Requer ``X-API-Key`` se definido."""
    _exigir_token(x_api_key)
    return _executar_pipeline(req)


@app.get("/run")
def run_get(
    date: str | None = None,
    send_email: bool = False,
    create_clickup: bool = False,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Versão por query string: ``/run?date=YYYY-MM-DD`` (facilita testes)."""
    _exigir_token(x_api_key)
    return _executar_pipeline(
        RunRequest(date=date, send_email=send_email, create_clickup=create_clickup)
    )


@app.get("/days")
def days(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Lista as datas que já têm relatório salvo no Turso (para o seletor)."""
    _exigir_token(x_api_key)
    from src.database.repositories import ReportRepository
    from src.database.turso_client import get_turso_client

    try:
        repo = ReportRepository(get_turso_client())
        return {"dates": repo.listar_datas(90)}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao listar dias: {type(exc).__name__}: {exc}"
        )


@app.get("/day/{data}")
def day(
    data: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Retorna TODOS os dados salvos de um dia (sem reexecutar o agente).

    Lê o relatório salvo no Turso e devolve métricas, alertas, destaques e o
    Markdown — é o que alimenta as telas do front a partir do banco.
    """
    _exigir_token(x_api_key)
    from src.database.repositories import ReportRepository
    from src.database.turso_client import get_turso_client

    try:
        dia = parse_data(data)
        repo = ReportRepository(get_turso_client())
        registro = repo.buscar_relatorio(dia)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao ler o dia: {type(exc).__name__}: {exc}"
        )
    if not registro:
        raise HTTPException(status_code=404, detail=f"Sem relatório salvo para {data}.")

    p = registro.get("payload") or {}
    return {
        "date": str(dia),
        "provider": registro.get("provider"),
        "report_markdown": registro.get("markdown", ""),
        "metrics": p.get("metrics", {}),
        "alerts": p.get("alerts", []),
        "highlights": p.get("highlights", {}),
        "data_quality": p.get("data_quality", {}),
        "alerts_count": len(p.get("alerts", []) or []),
    }


@app.get("/history")
def history(
    days: int = 7,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Série histórica de métricas salvas no Turso (para gráficos de tendência).

    Lê ``daily_metrics`` dos últimos ``days`` dias (sem reexecutar o pipeline).
    """
    _exigir_token(x_api_key)
    from datetime import timedelta

    from src.config import get_settings
    from src.database.repositories import MetricsRepository
    from src.database.turso_client import get_turso_client
    from src.utils.date_utils import agora_tz

    try:
        n = max(1, min(int(days), 60))
        settings = get_settings()
        base = agora_tz(settings.report_timezone).date()
        repo = MetricsRepository(get_turso_client())
        serie: list[dict[str, Any]] = []
        for i in range(n - 1, -1, -1):
            dia = base - timedelta(days=i)
            metricas = repo.buscar_metricas_do_dia(dia)
            if metricas:
                serie.append({"date": str(dia), "metrics": metricas})
        return {"days": serie}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao ler histórico: {type(exc).__name__}: {exc}"
        )


@app.get("/metrics/{data}")
def metrics_do_dia(
    data: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Leitura rápida das métricas já salvas no Turso para uma data.

    Não reexecuta o Salesforce nem a IA — útil para o front carregar
    rapidamente um dia já processado.
    """
    _exigir_token(x_api_key)
    from src.database.repositories import MetricsRepository
    from src.database.turso_client import get_turso_client

    try:
        dia = parse_data(data)
        repo = MetricsRepository(get_turso_client())
        return {"date": str(dia), "metrics": repo.buscar_metricas_do_dia(dia)}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao ler métricas: {type(exc).__name__}: {exc}"
        )


# ----------------------------------------------------------------------
# Painel React (estático) — serve frontend-react/dist em "/", se compilado.
# ----------------------------------------------------------------------
# Precisa ser o ÚLTIMO registro de rota: o Starlette tenta as rotas nesta
# ordem, então os endpoints acima (``/health``, ``/days`` etc.) continuam
# tendo prioridade sobre o mount; só cai aqui o que não bateu com nenhuma
# rota explícita (ou seja, os arquivos do painel).
_DIST_PAINEL = Path(__file__).resolve().parent / "frontend-react" / "dist"
if _DIST_PAINEL.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_PAINEL), html=True), name="painel")
else:
    logger.warning(
        "frontend-react/dist não encontrado — painel React não será servido em '/'. "
        "Rode 'npm run build' em frontend-react/ (o Dockerfile já faz isso no deploy)."
    )
