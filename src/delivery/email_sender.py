"""Entrega do relatório por e-mail (SMTP). Opcional.

Monta um e-mail executivo em português (HTML com estilos inline + versão texto)
a partir das métricas e alertas já calculados em Python, e envia via SMTP.
Não quebra a execução se o SMTP não estiver configurado — apenas registra e
retorna ``False``.
"""

from __future__ import annotations

import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

from ..config.settings import EmailSettings
from ..utils.logger import get_logger

logger = get_logger("delivery.email")

# Cores por severidade (usadas em selos/badges no e-mail HTML).
_COR_SEVERIDADE = {"high": "#c0392b", "medium": "#e67e22", "low": "#f1c40f"}
_ROTULO_SEVERIDADE = {"high": "ALTA", "medium": "MÉDIA", "low": "BAIXA"}


# ----------------------------------------------------------------------
# Helpers de formatação (pt-BR)
# ----------------------------------------------------------------------
def _moeda(valor: Any) -> str:
    """Formata um número como moeda em Real (R$ 1.234,56)."""
    try:
        numero = float(valor or 0.0)
    except (TypeError, ValueError):
        return "R$ 0,00"
    texto = f"{numero:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _num(valor: Any, padrao: str = "—") -> str:
    """Formata um número inteiro/decimal de forma amigável."""
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return f"{valor:.2f}".rstrip("0").rstrip(".") if valor % 1 else str(int(valor))
    return str(valor)


def _pct(valor: Any) -> str:
    """Formata um percentual (ex.: 12.5 → 12,5%)."""
    if valor is None:
        return "—"
    try:
        return f"{float(valor):.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _escape(texto: Any) -> str:
    """Escapa caracteres HTML básicos para evitar quebra de layout."""
    s = str(texto or "")
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ----------------------------------------------------------------------
# Blocos do e-mail HTML
# ----------------------------------------------------------------------
def _linha_kpi(rotulo: str, valor: str, destaque: str = "#1f4fb2") -> str:
    """Célula de KPI (rótulo + valor) para a grade de números-chave."""
    return (
        '<td style="padding:10px 14px;border:1px solid #e6e8eb;'
        'border-radius:8px;background:#f8fafc;vertical-align:top;">'
        f'<div style="font-size:11px;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:.04em;">{_escape(rotulo)}</div>'
        f'<div style="font-size:20px;font-weight:700;color:{destaque};'
        f'margin-top:2px;">{_escape(valor)}</div></td>'
    )


def _grade_kpis(metrics: dict[str, Any]) -> str:
    """Monta a grade de números-chave (3 colunas por linha)."""
    leads = metrics.get("leads", {}) or {}
    opp = metrics.get("opportunities", {}) or {}
    tasks = metrics.get("tasks", {}) or {}
    sat = metrics.get("satisfaction", {}) or {}
    canc = metrics.get("cancellations", {}) or {}

    celulas: list[str] = [
        _linha_kpi("Leads novos", _num(leads.get("new_leads"))),
        _linha_kpi("Conversão de leads", _pct(leads.get("conversion_rate"))),
        _linha_kpi("Pipeline aberto", _moeda(opp.get("open_pipeline_amount"))),
        _linha_kpi("Oportunidades ganhas", _num(opp.get("won_opportunities")), "#15803d"),
        _linha_kpi("Oportunidades perdidas", _num(opp.get("lost_opportunities")), "#b91c1c"),
        _linha_kpi("Oportunidades paradas", _num(opp.get("stalled_opportunities")), "#b45309"),
        _linha_kpi("Tarefas vencidas", _num(tasks.get("tasks_overdue")), "#b45309"),
    ]
    if sat.get("configured") and sat.get("responses"):
        celulas.append(_linha_kpi("Satisfação (nota média)", _num(sat.get("avg_score"))))
    if canc.get("configured") and canc.get("cancellations_count"):
        celulas.append(
            _linha_kpi("Cancelamentos", _num(canc.get("cancellations_count")), "#b91c1c")
        )

    # Distribui as células em linhas de 3 colunas.
    linhas_html: list[str] = []
    for i in range(0, len(celulas), 3):
        grupo = celulas[i : i + 3]
        linhas_html.append(
            '<tr>' + "".join(grupo)
            + ('<td></td>' * (3 - len(grupo)))
            + '</tr>'
            + '<tr><td colspan="3" style="height:8px;"></td></tr>'
        )
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:separate;border-spacing:8px 0;">'
        + "".join(linhas_html)
        + "</table>"
    )


def _bloco_alertas(alerts: list[dict[str, Any]]) -> str:
    """Monta os cartões dos principais alertas (até 6)."""
    altos = [a for a in alerts if a.get("severity") == "high"]
    selecionados = (altos or alerts)[:6]
    if not selecionados:
        return (
            '<p style="color:#15803d;font-size:14px;">'
            "✅ Nenhum alerta crítico para o período.</p>"
        )

    cartoes: list[str] = []
    for a in selecionados:
        sev = a.get("severity", "low")
        cor = _COR_SEVERIDADE.get(sev, "#94a3b8")
        rotulo = _ROTULO_SEVERIDADE.get(sev, "INFO")
        acao = a.get("recommended_action")
        acao_html = (
            f'<div style="margin-top:6px;font-size:13px;color:#0f172a;">'
            f'<strong>Ação:</strong> {_escape(acao)}</div>'
            if acao
            else ""
        )
        cartoes.append(
            f'<div style="border-left:4px solid {cor};background:#f8fafc;'
            f'padding:10px 14px;margin-bottom:10px;border-radius:0 8px 8px 0;">'
            f'<span style="display:inline-block;background:{cor};color:#fff;'
            f'font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;'
            f'letter-spacing:.04em;">{rotulo}</span> '
            f'<span style="font-weight:700;color:#0f172a;font-size:14px;">'
            f'{_escape(a.get("title", ""))}</span>'
            f'<div style="margin-top:4px;font-size:13px;color:#475569;">'
            f'{_escape(a.get("description", ""))}</div>'
            f'{acao_html}</div>'
        )
    return "".join(cartoes)


def _bloco_prioridades(alerts: list[dict[str, Any]]) -> str:
    """Lista numerada das principais ações recomendadas (até 5)."""
    acoes = [a.get("recommended_action") for a in alerts if a.get("recommended_action")]
    if not acoes:
        return ""
    itens = "".join(
        f'<li style="margin-bottom:6px;font-size:13px;color:#0f172a;">{_escape(a)}</li>'
        for a in acoes[:5]
    )
    return (
        '<h3 style="font-size:15px;color:#0f172a;margin:22px 0 8px;">'
        "🎯 Prioridades para hoje</h3>"
        f'<ol style="margin:0;padding-left:20px;">{itens}</ol>'
    )


def _montar_html(
    report_date: str,
    metrics: dict[str, Any],
    alerts: list[dict[str, Any]],
    resumo_ia: str = "",
    highlights: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Monta o corpo HTML completo do e-mail executivo (pt-BR)."""
    altos = sum(1 for a in alerts if a.get("severity") == "high")
    resumo = (
        f"Foram gerados <strong>{len(alerts)} alerta(s)</strong>, "
        f"sendo <strong>{altos} de severidade alta</strong>."
    )
    # Bloco de análise da IA (insights), quando houver.
    bloco_ia = ""
    if resumo_ia.strip():
        texto_ia = _escape(resumo_ia).replace("\n\n", "</p><p style='margin:0 0 10px'>")
        texto_ia = texto_ia.replace("\n", "<br>")
        bloco_ia = (
            "<div style='background:#eef4ff;border:1px solid #dbe5fb;border-radius:10px;"
            "padding:14px 16px;margin:0 0 18px;'>"
            "<div style='font-size:12px;color:#1f4fb2;font-weight:700;text-transform:uppercase;"
            "letter-spacing:.04em;margin-bottom:6px;'>🤖 Análise da IA</div>"
            f"<p style='margin:0 0 10px;font-size:14px;color:#0f172a;line-height:1.55;'>{texto_ia}</p>"
            "</div>"
        )
    return f"""\
<div style="background:#f1f5f9;padding:24px 0;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="640" align="center" cellspacing="0" cellpadding="0"
         style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;
                overflow:hidden;border:1px solid #e2e8f0;">
    <tr>
      <td style="background:#1f4fb2;padding:22px 28px;">
        <div style="color:#ffffff;font-size:20px;font-weight:700;">Analytical-Force</div>
        <div style="color:#c7d2fe;font-size:13px;margin-top:2px;">
          Relatório diário de performance comercial — {_escape(report_date)}
        </div>
      </td>
    </tr>
    <tr>
      <td style="padding:24px 28px;">
        <h3 style="font-size:15px;color:#0f172a;margin:0 0 8px;">📌 Resumo executivo</h3>
        <p style="font-size:14px;color:#475569;margin:0 0 14px;line-height:1.5;">{resumo}</p>
        {bloco_ia}

        <h3 style="font-size:15px;color:#0f172a;margin:0 0 10px;">📊 Números-chave</h3>
        {_grade_kpis(metrics)}

        <h3 style="font-size:15px;color:#0f172a;margin:22px 0 8px;">🚨 Principais alertas</h3>
        {_bloco_alertas(alerts)}

        {_bloco_prioridades(alerts)}

        {_bloco_destaques_html(highlights or {})}
      </td>
    </tr>
    <tr>
      <td style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0;">
        <div style="font-size:12px;color:#94a3b8;">
          Relatório gerado automaticamente pelo agente <strong>Analytical-Force</strong>.
          Os números são calculados em Python a partir do Salesforce; a interpretação
          é gerada por modelo local. O relatório completo está anexado/registrado no sistema.
        </div>
      </td>
    </tr>
  </table>
</div>"""


def _montar_texto(
    report_date: str,
    metrics: dict[str, Any],
    alerts: list[dict[str, Any]],
    resumo_ia: str = "",
) -> str:
    """Monta uma versão em texto puro (fallback para clientes sem HTML)."""
    opp = metrics.get("opportunities", {}) or {}
    leads = metrics.get("leads", {}) or {}
    altos = sum(1 for a in alerts if a.get("severity") == "high")
    linhas = [
        f"Analytical-Force — Relatório diário ({report_date})",
        "",
    ]
    if resumo_ia.strip():
        linhas += ["ANÁLISE DA IA:", resumo_ia.strip(), ""]
    linhas += [
        f"Alertas: {len(alerts)} (sendo {altos} de severidade alta).",
        f"Leads novos: {_num(leads.get('new_leads'))} | "
        f"Conversão: {_pct(leads.get('conversion_rate'))}",
        f"Pipeline aberto: {_moeda(opp.get('open_pipeline_amount'))} | "
        f"Ganhas: {_num(opp.get('won_opportunities'))} | "
        f"Perdidas: {_num(opp.get('lost_opportunities'))}",
        "",
        "Principais alertas:",
    ]
    for a in [x for x in alerts if x.get("severity") == "high"][:6] or alerts[:6]:
        linhas.append(f"- [{_ROTULO_SEVERIDADE.get(a.get('severity'), 'INFO')}] {a.get('title', '')}")
        if a.get("recommended_action"):
            linhas.append(f"    Ação: {a['recommended_action']}")
    return "\n".join(linhas)


# ----------------------------------------------------------------------
# Envio
# ----------------------------------------------------------------------
def _extrair_resumo_ia(report_markdown: str) -> str:
    """Extrai o texto da seção '## 1. Resumo Executivo' do relatório.

    É o trecho interpretado pela IA (insights). Retorna vazio se não achar.
    """
    if not report_markdown:
        return ""
    linhas = report_markdown.split("\n")
    capturando = False
    buffer: list[str] = []
    for ln in linhas:
        if ln.lstrip().startswith("## "):
            if capturando:
                break  # chegou na próxima seção
            if "resumo executivo" in ln.lower():
                capturando = True
            continue
        if capturando:
            buffer.append(ln)
    return "\n".join(buffer).strip()


_ROTULO_DESTAQUE = {
    "leads_criados": "🆕 Leads criados",
    "leads_sem_tarefa": "⏳ Leads sem 1ª tarefa",
    "oportunidades_travadas": "🚧 Oportunidades travadas",
    "oportunidades_ganhas": "🏆 Oportunidades ganhas",
    "cancelamentos": "❌ Cancelamentos",
    "satisfacoes_piores": "😟 Piores satisfações",
}


def _bloco_destaques_html(highlights: dict[str, list[dict[str, Any]]]) -> str:
    """Renderiza 'Registros do dia' com links diretos por categoria."""
    if not highlights:
        return ""
    secoes: list[str] = []
    for chave, rotulo in _ROTULO_DESTAQUE.items():
        itens = highlights.get(chave) or []
        if not itens:
            continue
        linhas_li: list[str] = []
        for r in itens[:15]:
            nome = _escape(r.get("name") or r.get("id") or "registro")
            info = f" <span style='color:#64748b'>({_escape(r['info'])})</span>" if r.get("info") else ""
            url = r.get("url")
            alvo = (
                f"<a href='{_escape(url)}' style='color:#1f4fb2;text-decoration:none'>{nome}</a>"
                if url
                else nome
            )
            linhas_li.append(f"<li style='margin-bottom:3px'>{alvo}{info}</li>")
        secoes.append(
            f"<div style='margin-bottom:12px'>"
            f"<div style='font-size:13px;font-weight:700;color:#0f172a;margin-bottom:4px'>"
            f"{rotulo} <span style='color:#94a3b8;font-weight:400'>({len(itens)})</span></div>"
            f"<ul style='margin:0;padding-left:18px;font-size:13px;color:#334155'>{''.join(linhas_li)}</ul>"
            f"</div>"
        )
    if not secoes:
        return ""
    return (
        "<h3 style='font-size:15px;color:#0f172a;margin:22px 0 8px;'>🔗 Registros do dia</h3>"
        "<div style='font-size:12px;color:#94a3b8;margin-bottom:8px'>"
        "Links diretos no Salesforce (tarefas vencidas omitidas pelo volume).</div>"
        + "".join(secoes)
    )


def enviar_relatorio_email(
    config: EmailSettings,
    assunto: str,
    report_date: str,
    metrics: dict[str, Any],
    alerts: list[dict[str, Any]],
    report_markdown: str = "",
    highlights: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """Envia o relatório executivo por e-mail.

    Prefere a **Gmail API (HTTP)** quando configurada — funciona em ambientes
    que bloqueiam SMTP (ex.: Hugging Face Spaces). Caso contrário, usa SMTP.

    Args:
        config: Configurações de e-mail (Gmail API e/ou SMTP).
        assunto: Assunto do e-mail.
        report_date: Data de referência do relatório (texto).
        metrics: Métricas calculadas (leads/opportunities/tasks/...).
        alerts: Lista de alertas gerada pelo motor de risco.

    Returns:
        ``True`` se enviado; ``False`` se não configurado ou em caso de erro.
    """
    if not config.is_configured:
        logger.info("Envio de e-mail ignorado: nenhum método configurado.")
        return False

    resumo_ia = _extrair_resumo_ia(report_markdown)
    html = _montar_html(report_date, metrics, alerts, resumo_ia, highlights or {})
    texto = _montar_texto(report_date, metrics, alerts, resumo_ia)

    remetente = config.gmail_sender or config.smtp_user or "analytical-force@localhost"
    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto
    mensagem["From"] = remetente
    mensagem["To"] = config.recipient_email
    mensagem.attach(MIMEText(texto, "plain", "utf-8"))
    mensagem.attach(MIMEText(html, "html", "utf-8"))

    # Gmail API tem prioridade (HTTPS; passa por firewalls que bloqueiam SMTP).
    if config.gmail_api_configured:
        return _enviar_via_gmail_api(config, mensagem)
    return _enviar_via_smtp(config, mensagem)


def _enviar_via_smtp(config: EmailSettings, mensagem: MIMEMultipart) -> bool:
    """Envia a mensagem via SMTP (STARTTLS). Usado em ambiente local."""
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as servidor:
            servidor.starttls()
            if config.smtp_user and config.smtp_password:
                servidor.login(config.smtp_user, config.smtp_password)
            servidor.sendmail(
                mensagem["From"], [config.recipient_email], mensagem.as_string()
            )
        logger.info("Relatório enviado por e-mail (SMTP) para %s.", config.recipient_email)
        return True
    except Exception as exc:  # não deve derrubar o agente
        # Surface do tipo de erro (sem expor senha). OSError costuma indicar
        # SMTP bloqueado pelo ambiente (ex.: Hugging Face) — use a Gmail API.
        logger.error("Falha ao enviar e-mail (SMTP): %s", type(exc).__name__)
        return False


def _obter_access_token_gmail(config: EmailSettings) -> str:
    """Obtém um access_token do Google via refresh_token (OAuth).

    Não registra o token nem o payload (contêm segredos).
    """
    resposta = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "client_id": config.gmail_client_id,
            "client_secret": config.gmail_client_secret,
            "refresh_token": config.gmail_refresh_token,
        },
        timeout=30,
    )
    if resposta.status_code != 200:
        try:
            erro = resposta.json()
            detalhe = f"{erro.get('error')} - {erro.get('error_description', '')}".strip(" -")
        except ValueError:
            detalhe = "resposta inválida do servidor OAuth do Google."
        raise RuntimeError(f"OAuth Google falhou (status {resposta.status_code}): {detalhe}")
    return resposta.json()["access_token"]


def _enviar_via_gmail_api(config: EmailSettings, mensagem: MIMEMultipart) -> bool:
    """Envia a mensagem usando a Gmail API (HTTP), via OAuth refresh token."""
    try:
        token = _obter_access_token_gmail(config)
        raw = base64.urlsafe_b64encode(mensagem.as_bytes()).decode("utf-8")
        resposta = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": raw},
            timeout=30,
        )
        resposta.raise_for_status()
        logger.info(
            "Relatório enviado por e-mail (Gmail API) para %s.", config.recipient_email
        )
        return True
    except Exception as exc:  # não deve derrubar o agente
        # Surface do tipo de erro, sem expor token.
        logger.error("Falha ao enviar e-mail (Gmail API): %s", type(exc).__name__)
        return False
