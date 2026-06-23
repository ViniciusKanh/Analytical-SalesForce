"""Integração opcional com ClickUp (criação de tarefas para alertas críticos).

IMPORTANTE — segurança operacional:
- Nada é criado automaticamente sem a flag ``ENABLE_CLICKUP_AUTO_CREATE=true``.
- Apenas alertas de severidade ``high`` viram tarefas.
- Esta é uma integração de SAÍDA controlada; não altera dados no Salesforce.

Enquanto a flag estiver desativada, as funções apenas registram a intenção
e retornam sem efeito colateral.
"""

from __future__ import annotations

from typing import Any

import requests

from ..config.settings import ClickUpSettings
from ..utils.logger import get_logger

logger = get_logger("delivery.clickup")

_URL_BASE = "https://api.clickup.com/api/v2"

# Rótulos e prioridades por severidade (ClickUp: 1=urgente ... 4=baixa).
_ROTULO_SEVERIDADE = {"high": "🔴 Alta", "medium": "🟠 Média", "low": "🟡 Baixa"}
_PRIORIDADE_SEVERIDADE = {"high": 1, "medium": 2, "low": 3}


def _link_salesforce(instance_url: str | None, record_id: str | None) -> str | None:
    """Monta o link direto para um registro no Salesforce (se possível)."""
    if not instance_url or not record_id:
        return None
    return f"{instance_url.rstrip('/')}/{record_id}"


def _detalhe_erro_clickup(exc: Exception) -> str:
    """Extrai status + mensagem do erro do ClickUp, para diagnóstico (sem segredos).

    A resposta de erro do ClickUp traz campos como ``err`` e ``ECODE`` — úteis
    para entender a recusa (token, lista, assignee, etc.).
    """
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            corpo = resp.json()
            msg = corpo.get("err") or corpo.get("error") or ""
            ecode = corpo.get("ECODE", "")
            return f"HTTP {resp.status_code} {ecode}: {msg}".strip()
        except Exception:
            texto = str(getattr(resp, "text", ""))[:300]
            return f"HTTP {getattr(resp, 'status_code', '?')}: {texto}"
    return f"{type(exc).__name__}: {exc}"


def _moeda(valor: Any) -> str:
    """Formata um número como moeda em Real (R$ 1.234,56)."""
    try:
        numero = float(valor or 0.0)
    except (TypeError, ValueError):
        return "R$ 0,00"
    texto = f"{numero:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _bloco_registros(
    registros: list[dict[str, Any]], instance_url: str | None
) -> list[str]:
    """Monta a lista Markdown dos registros afetados (dados concretos)."""
    linhas: list[str] = ["### Registros afetados"]
    for r in registros[:10]:
        partes: list[str] = [f"**{r.get('name') or r.get('id') or 'Registro'}**"]
        if r.get("amount") is not None:
            partes.append(_moeda(r.get("amount")))
        if r.get("stage"):
            partes.append(f"estágio: {r['stage']}")
        if r.get("owner"):
            partes.append(f"GC: {r['owner']}")
        if r.get("days_inactive") is not None:
            partes.append(f"{r['days_inactive']}d sem atividade")
        if r.get("next_action"):
            partes.append(f"próx. ação: {r['next_action']}")
        if r.get("info"):
            partes.append(str(r["info"]))
        texto = " — ".join(partes)
        link = r.get("url") or _link_salesforce(instance_url, r.get("id"))
        if link:
            texto += f" — [abrir no Salesforce]({link})"
        linhas.append(f"- {texto}")
    return linhas


def _descricao_markdown(
    alerta: dict[str, Any],
    instance_url: str | None,
    report_date: str | None,
) -> str:
    """Monta a descrição em Markdown rica e acionável para a tarefa do ClickUp.

    Inclui diagnóstico, ação recomendada, plano de ação por IA (quando houver),
    os registros concretos afetados (com link direto) e rodapé de rastreio.
    """
    severidade = alerta.get("severity", "low")
    rotulo = _ROTULO_SEVERIDADE.get(severidade, "🟡 Baixa")
    linhas: list[str] = [
        f"**Severidade:** {rotulo}  ",
        f"**Categoria:** {alerta.get('category', 'Geral')}",
        "",
        "### Diagnóstico",
        alerta.get("description", "—"),
        "",
        "### Ação recomendada",
        alerta.get("recommended_action", "—"),
    ]

    plano = alerta.get("action_plan")
    if plano:
        linhas += ["", "### Plano de ação sugerido", str(plano)]

    registros = alerta.get("affected_records") or []
    if registros:
        linhas.append("")
        linhas += _bloco_registros(registros, instance_url)
    else:
        # Sem detalhes por registro: usa origem/record id genérico.
        origem = alerta.get("source_object")
        record_id = alerta.get("source_record_id")
        if origem:
            texto_origem = origem + (f" ({record_id})" if record_id else "")
            linhas += ["", f"**Origem:** {texto_origem}"]
            link = _link_salesforce(instance_url, record_id)
            if link:
                linhas.append(f"**Registro no Salesforce:** [{record_id}]({link})")

    rodape = "_Gerado por Analytical-Force"
    if report_date:
        rodape += f" • relatório {report_date}"
    rodape += "_"
    linhas += ["", "---", rodape]
    return "\n".join(linhas)


def _resolver_assignee_ids(config: ClickUpSettings) -> list[int]:
    """Resolve os IDs de usuário do ClickUp para atribuir às tarefas.

    Prioriza ``CLICKUP_ASSIGNEE_ID`` (numérico). Se ausente, resolve o
    ``CLICKUP_ASSIGNEE_EMAIL`` consultando os membros da lista configurada.

    Args:
        config: Configurações do ClickUp.

    Returns:
        Lista com o ID do responsável (vazia se não configurado/encontrado).
    """
    # 1) ID explícito tem prioridade (evita uma chamada à API).
    if config.assignee_id:
        try:
            return [int(config.assignee_id)]
        except ValueError:
            logger.warning("CLICKUP_ASSIGNEE_ID inválido (não numérico). Ignorando.")
            return []

    # 2) Resolução por e-mail via membros da lista.
    if not config.assignee_email:
        return []

    headers = {"Authorization": config.api_token}
    url = f"{_URL_BASE}/list/{config.list_id}/member"
    try:
        resposta = requests.get(url, headers=headers, timeout=30)
        resposta.raise_for_status()
        membros = resposta.json().get("members", [])
    except Exception as exc:  # não derruba o agente
        logger.error(
            "Falha ao buscar membros da lista no ClickUp: %s", type(exc).__name__
        )
        return []

    alvo = config.assignee_email.strip().lower()
    for membro in membros:
        if (membro.get("email") or "").lower() == alvo:
            uid = membro.get("id")
            if uid is not None:
                return [int(uid)]

    logger.warning(
        "Responsável não encontrado na lista pelo e-mail informado "
        "(verifique se o usuário é membro da lista no ClickUp)."
    )
    return []


def criar_tarefas_de_alertas(
    alertas: list[dict[str, Any]],
    config: ClickUpSettings,
    habilitado: bool,
    instance_url: str | None = None,
    report_date: str | None = None,
) -> int:
    """Cria tarefas no ClickUp para alertas de severidade alta.

    Args:
        alertas: Lista de alertas gerada pelo motor de risco.
        config: Configurações do ClickUp (token + list_id).
        habilitado: Flag ``ENABLE_CLICKUP_AUTO_CREATE``. Se False, não cria nada.
        instance_url: URL da org Salesforce, para montar link direto ao registro.
        report_date: Data do relatório (referência exibida na tarefa).

    Returns:
        Quantidade de tarefas criadas (0 quando desabilitado/erro).
    """
    if not habilitado:
        logger.info("ClickUp desabilitado (ENABLE_CLICKUP_AUTO_CREATE=false). Nada criado.")
        return 0
    if not config.is_configured:
        logger.info("ClickUp não configurado (token/list_id ausentes). Nada criado.")
        return 0

    criticos = [a for a in alertas if a.get("severity") == "high"]
    if not criticos:
        logger.info("Sem alertas de severidade alta para enviar ao ClickUp.")
        return 0

    headers = {"Authorization": config.api_token, "Content-Type": "application/json"}
    url = f"{_URL_BASE}/list/{config.list_id}/task"
    criadas = 0

    # Resolve o responsável uma única vez (reaproveitado em todas as tarefas).
    assignees = _resolver_assignee_ids(config)
    if assignees:
        logger.info("Tarefas do ClickUp serão atribuídas ao responsável configurado.")

    for alerta in criticos:
        severidade = alerta.get("severity", "high")
        markdown = _descricao_markdown(alerta, instance_url, report_date)
        corpo: dict[str, Any] = {
            "name": f"[Analytical-Force] {alerta.get('title', 'Alerta crítico')}",
            # ClickUp usa 'markdown_content' para a descrição em Markdown;
            # mantemos 'description' como texto simples de fallback.
            "description": str(alerta.get("description") or alerta.get("title", "")),
            "markdown_content": markdown,
            "priority": _PRIORIDADE_SEVERIDADE.get(severidade, 1),
        }
        if assignees:
            corpo["assignees"] = assignees
        try:
            resposta = requests.post(url, json=corpo, headers=headers, timeout=30)
            resposta.raise_for_status()
            criadas += 1
            # Loga a URL da tarefa para facilitar a localização no ClickUp.
            try:
                dados = resposta.json()
                if dados.get("url"):
                    logger.info("Tarefa ClickUp criada: %s", dados["url"])
            except Exception:  # resposta sem JSON não deve quebrar o fluxo
                pass
        except Exception as exc:  # não derruba o agente
            # Surface do motivo real do ClickUp (status + mensagem), sem segredos.
            logger.error("Falha ao criar tarefa no ClickUp: %s", _detalhe_erro_clickup(exc))

    logger.info("Tarefas criadas no ClickUp: %d.", criadas)
    return criadas
