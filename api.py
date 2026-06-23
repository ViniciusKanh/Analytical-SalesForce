"""API HTTP (FastAPI) do Analytical-Force.

Expõe a execução do agente por API, para rodar 100% online (ex.: Hugging Face
Spaces tipo Docker) e ser acionado por um front-end.

Princípios:
- Toda a configuração vem de variáveis de ambiente (Secrets do Space).
- A execução é protegida por chave de API (cabeçalho ``X-API-Key``), pois
  dispara leitura no Salesforce e, opcionalmente, e-mail/ClickUp.
- O Salesforce continua somente leitura; nenhuma credencial é exposta.

Endpoints:
- ``GET  /``             página simples com instruções.
- ``GET  /health``       verificação de saúde.
- ``GET  /config/check`` validação da configuração (sem segredos).
- ``POST /run``          executa o pipeline diário (protegido por X-API-Key).
- ``GET  /docs``         documentação interativa (Swagger).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def raiz() -> str:
    """Página inicial com instruções básicas."""
    return """\
<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Analytical-Force API</title>
<style>body{font-family:Arial,Helvetica,sans-serif;max-width:720px;margin:40px auto;
padding:0 16px;color:#0f172a;line-height:1.5}code{background:#f1f5f9;padding:2px 6px;
border-radius:6px}a{color:#1f4fb2}</style></head><body>
<h1>📊 Analytical-Force API</h1>
<p>Agente de inteligência analítica (Salesforce → métricas em Python → Turso →
relatório). Opera <strong>somente leitura</strong> no Salesforce.</p>
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
        entregas["email_enviado"] = enviar_relatorio_email(
            config=settings.email,
            assunto=f"Analytical-Force — Relatório {resultado.dia}",
            report_date=str(resultado.dia),
            metrics=resultado.metricas,
            alerts=resultado.alertas,
            report_markdown=resultado.markdown,
            highlights=resultado.destaques,
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
