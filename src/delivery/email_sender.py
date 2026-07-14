"""Entrega do relatório por e-mail (SMTP). Opcional.

Monta um e-mail executivo em português (HTML com estilos inline + versão texto)
a partir das métricas e alertas já calculados em Python, e envia via SMTP.
Não quebra a execução se o SMTP não estiver configurado — apenas registra e
retorna ``False``.
"""

from __future__ import annotations

import base64
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

from ..config.settings import EmailSettings
from ..utils.logger import get_logger

logger = get_logger("delivery.email")

# ----------------------------------------------------------------------
# Identidade visual (Penso) — paleta oficial da marca.
# ----------------------------------------------------------------------
# Cores "vivas" (uso em fundos/selos) e variantes escurecidas para texto
# sobre fundo branco (mantém contraste de leitura sem perder a identidade).
_PENSO_BLUE = "#0018FF"
_BLUE_TECH = "#0004DD"
_PENSO_BLACK = "#171717"
_BLACK_INTENSE = "#060606"
_SUCESSO = "#16C79A"
_SUCESSO_TXT = "#0d8a6d"
_ERRO = "#F05454"
_ERRO_TXT = "#c62f2f"
_ALERTA = "#FFC453"
_ALERTA_TXT = "#a15c00"
_DIVISORIA = "#E6EAEE"
_HOVER = "#F7F8FA"

# Logo do Salesforce (fonte de dados) — mesma URL pública já usada no painel React.
_LOGO_SALESFORCE_URL = "https://upload.wikimedia.org/wikipedia/commons/f/f9/Salesforce.com_logo.svg"

# Cores por severidade (usadas em selos/badges no e-mail HTML).
_COR_SEVERIDADE = {"high": _ERRO, "medium": _ALERTA, "low": "#94a3b8"}
# Texto do selo: escuro sobre o Alerta (amarelo) para manter contraste; branco nos demais.
_TEXTO_SEVERIDADE = {"high": "#ffffff", "medium": _PENSO_BLACK, "low": "#ffffff"}
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


def _md_inline(texto: str) -> str:
    """Converte marcações inline básicas (negrito) em HTML, com escape."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _escape(texto))


def _md_para_html(texto: str) -> str:
    """Converte um trecho Markdown simples em HTML (para o e-mail).

    Trata títulos (``#``..``###``), negrito (``**``), listas (``-``/``*``) e
    parágrafos — evitando que marcações apareçam cruas (ex.: ``### Resumo``).
    """
    html: list[str] = []
    bullets: list[str] = []

    def _flush() -> None:
        if bullets:
            itens = "".join(
                f"<li style='margin-bottom:4px'>{b}</li>" for b in bullets
            )
            html.append(
                f"<ul style='margin:4px 0 10px;padding-left:18px;font-size:14px;"
                f"line-height:1.55;color:#334155'>{itens}</ul>"
            )
            bullets.clear()

    for bruto in (texto or "").split("\n"):
        linha = bruto.strip()
        if not linha:
            continue
        sem_hash = linha.lstrip("#").strip()
        # Ignora um eventual cabeçalho "Resumo Executivo" repetido.
        if sem_hash.lower() in ("resumo executivo", "1. resumo executivo"):
            continue
        if linha.startswith("#"):
            _flush()
            html.append(
                f"<div style='font-weight:700;color:#0f172a;margin:10px 0 4px;"
                f"font-size:14px'>{_md_inline(sem_hash)}</div>"
            )
        elif linha[:2] in ("- ", "* ") or linha.startswith("•"):
            bullets.append(_md_inline(linha.lstrip("-*• ").strip()))
        else:
            _flush()
            html.append(
                f"<p style='margin:0 0 10px;font-size:14px;line-height:1.6;"
                f"color:#334155'>{_md_inline(linha)}</p>"
            )
    _flush()
    return "".join(html)


# ----------------------------------------------------------------------
# Blocos do e-mail HTML
# ----------------------------------------------------------------------
def _linha_kpi(rotulo: str, valor: str, destaque: str = _PENSO_BLUE) -> str:
    """Célula de KPI (rótulo + valor) para a grade de números-chave.

    Recebe a classe ``af-kpi-cell`` (dark mode + empilhamento em telas
    pequenas via CSS em ``<head>``) além do estilo inline (fallback para
    clientes que ignoram ``<style>``, ex.: Outlook desktop).
    """
    return (
        '<td class="af-kpi-cell" style="padding:10px 14px;border:1px solid #e6e8eb;'
        'border-radius:8px;background:#f8fafc;vertical-align:top;">'
        f'<div class="af-kpi-label" style="font-size:11px;color:#64748b;text-transform:uppercase;'
        f'letter-spacing:.04em;">{_escape(rotulo)}</div>'
        f'<div style="font-size:20px;font-weight:700;color:{destaque};'
        f'margin-top:2px;">{_escape(valor)}</div></td>'
    )


def _grade_kpis(metrics: dict[str, Any]) -> str:
    """Monta a grade de números-chave (3 colunas por linha, empilha no mobile).

    Não inclui mais "Tarefas vencidas" (removido a pedido — volume alto
    demais para um KPI de topo); em seu lugar entram "Oportunidades criadas".
    """
    leads = metrics.get("leads", {}) or {}
    opp = metrics.get("opportunities", {}) or {}
    sat = metrics.get("satisfaction", {}) or {}
    canc = metrics.get("cancellations", {}) or {}
    contratos = metrics.get("contracts", {}) or {}

    celulas: list[str] = [
        _linha_kpi("Leads novos", _num(leads.get("new_leads"))),
        _linha_kpi("Conversão de leads", _pct(leads.get("conversion_rate"))),
        _linha_kpi(
            "Pipeline aberto",
            _moeda(opp.get("open_pipeline_product_value") or opp.get("open_pipeline_amount")),
        ),
        _linha_kpi("Oportunidades criadas", _num(opp.get("new_opportunities"))),
        _linha_kpi("Oportunidades ganhas", _num(opp.get("won_opportunities")), _SUCESSO_TXT),
        _linha_kpi("Oportunidades perdidas", _num(opp.get("lost_opportunities")), _ERRO_TXT),
        _linha_kpi("Oportunidades paradas", _num(opp.get("stalled_opportunities")), _ALERTA_TXT),
    ]
    if sat.get("configured") and sat.get("responses"):
        celulas.append(_linha_kpi("Satisfação (nota média)", _num(sat.get("avg_score"))))
    if canc.get("configured") and canc.get("cancellations_count"):
        celulas.append(
            _linha_kpi("Cancelamentos", _num(canc.get("cancellations_count")), _ERRO_TXT)
        )
    if contratos.get("configured"):
        celulas.append(_linha_kpi("Contratos modificados hoje", _num(contratos.get("modified_today_count"))))

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


def _bloco_contratos(metrics: dict[str, Any]) -> str:
    """Bloco de Contratos: modificações do dia + reajuste do mês (se configurado).

    Sempre traz o aviso de que o valor de reajuste é uma ESTIMATIVA (delta de
    valores), nunca um dado 100% garantido — regra 3/16/17 do projeto.
    """
    m = metrics.get("contracts", {}) or {}
    if not m.get("configured"):
        return ""

    partes: list[str] = []
    modificados = m.get("modified_today") or []
    if modificados:
        itens = "".join(
            f"<li style='margin-bottom:3px'>"
            f"<strong>{_escape(c.get('name') or c.get('id') or '—')}</strong>"
            f" <span style='color:#64748b'>— modificado por "
            f"{_escape(c.get('modified_by') or 'responsável não identificado')}</span></li>"
            for c in modificados[:15]
        )
        partes.append(
            f"<div class='af-altcard' style='background:{_HOVER};border-radius:10px;padding:12px 14px;margin-bottom:10px;'>"
            f"<div style='font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px;'>"
            f"📄 Contratos modificados hoje "
            f"<span style='color:#94a3b8;font-weight:400'>({m.get('modified_today_count', 0)})</span></div>"
            f"<ul style='margin:0;padding-left:18px;font-size:13px;color:#334155'>{itens}</ul>"
            f"</div>"
        )

    if m.get("readjustment_configured"):
        qtd = m.get("readjustment_month_count") or 0
        if qtd:
            inconsist = int(m.get("readjustment_inconsistent_count") or 0)
            reaj_itens = "".join(
                f"<li style='margin-bottom:3px'>"
                f"<strong>{_escape(c.get('name') or c.get('id') or '—')}</strong>: "
                f"{_moeda(c.get('previous_value'))} → {_moeda(c.get('current_value'))} "
                f"(<span style='color:{_SUCESSO_TXT if (c.get('delta') or 0) >= 0 else _ERRO_TXT}'>"
                f"{_moeda(c.get('delta'))}</span>"
                + (
                    f" · <span style='color:{_ALERTA_TXT}'>⚠ possível inconsistência</span>"
                    if c.get("inconsistent")
                    else ""
                )
                + ")</li>"
                for c in (m.get("readjustment_contracts") or [])[:10]
            )
            partes.append(
                f"<div class='af-altcard' style='background:{_HOVER};border-radius:10px;padding:12px 14px;margin-bottom:10px;'>"
                f"<div style='font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px;'>"
                f"💹 Reajuste de contratos no mês "
                f"<span style='color:#94a3b8;font-weight:400'>({qtd} contrato(s) · "
                f"{_moeda(m.get('readjustment_month_total'))})</span></div>"
                f"<ul style='margin:0 0 8px;padding-left:18px;font-size:13px;color:#334155'>{reaj_itens}</ul>"
                + (
                    f"<div style='font-size:12px;color:{_ALERTA_TXT};margin-bottom:6px;'>"
                    f"⚠ {inconsist} contrato(s) com possível inconsistência entre o reajuste "
                    "informado e o valor calculado.</div>"
                    if inconsist
                    else ""
                )
                + f"<div style='font-size:11px;color:#94a3b8;'>⚠ {_escape(m.get('readjustment_disclaimer', ''))}</div>"
                + "</div>"
            )
        else:
            partes.append(
                f"<div style='font-size:12px;color:#94a3b8;margin-bottom:10px;'>"
                "Nenhum contrato com reajuste identificado no mês corrente.</div>"
            )

    if not partes:
        return ""
    return (
        "<h3 class='af-h' style=\"font-size:14px;color:#0f172a;margin:22px 0 10px;padding-left:10px;"
        f"border-left:3px solid {_PENSO_BLUE};\">📄 Contratos</h3>"
        + "".join(partes)
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
        cor_texto_selo = _TEXTO_SEVERIDADE.get(sev, "#ffffff")
        rotulo = _ROTULO_SEVERIDADE.get(sev, "INFO")
        acao = a.get("recommended_action")
        acao_html = (
            f'<div style="margin-top:6px;font-size:13px;color:#0f172a;">'
            f'<strong>Ação:</strong> {_escape(acao)}</div>'
            if acao
            else ""
        )
        cartoes.append(
            f'<div style="border-left:4px solid {cor};background:{_HOVER};'
            f'padding:10px 14px;margin-bottom:10px;border-radius:0 8px 8px 0;">'
            f'<span style="display:inline-block;background:{cor};color:{cor_texto_selo};'
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


def _estilo_cabecalho() -> str:
    """CSS embutido no ``<head>``: dark mode, responsivo e animação sutil.

    Usa classes com ``!important`` para sobrepor os estilos inline em
    clientes que suportam ``<style>``/media queries (Apple Mail, Gmail
    app/web, Outlook.com/iOS). Clientes que ignoram ``<style>`` (ex.: Outlook
    desktop clássico) continuam vendo o layout claro fixo via inline — nunca
    quebram, apenas não ganham o tema escuro/empilhamento.
    """
    return f"""\
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-scheme" content="light dark">
    <style>
      body {{ margin:0; padding:0; }}
      @keyframes afFade {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:translateY(0); }} }}
      .af-animate {{ animation:afFade .5s ease-out both; }}
      .af-animate2 {{ animation:afFade .5s ease-out .12s both; }}
      .af-animate3 {{ animation:afFade .5s ease-out .24s both; }}
      @media screen and (max-width:600px) {{
        .af-container {{ width:100% !important; max-width:100% !important; border-radius:0 !important; }}
        .af-px {{ padding-left:18px !important; padding-right:18px !important; }}
        .af-kpi-cell {{ display:block !important; width:100% !important; margin-bottom:8px !important; }}
      }}
      @media (prefers-color-scheme: dark) {{
        .af-wrap {{ background:#0a0e18 !important; }}
        .af-card {{ background:#141a2b !important; border-color:#242c42 !important; }}
        .af-body h3 {{ color:#e8ecf5 !important; }}
        .af-body p, .af-body div, .af-body li, .af-body span {{ color:#c3ccdf !important; }}
        .af-kpi-cell {{ background:#1a2138 !important; border-color:#2a3350 !important; }}
        .af-kpi-label {{ color:#8fa0c2 !important; }}
        .af-altcard {{ background:#171e33 !important; }}
        .af-footer {{ background:#0e1424 !important; border-color:#242c42 !important; }}
        .af-muted {{ color:#7d8aa8 !important; }}
        a.af-link {{ color:#9fb6ff !important; }}
      }}
    </style>"""


def _montar_html(
    report_date: str,
    metrics: dict[str, Any],
    alerts: list[dict[str, Any]],
    resumo_ia: str = "",
    highlights: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Monta o e-mail executivo completo (documento HTML, pt-BR).

    Responsivo (empilha em telas pequenas) e com suporte a tema escuro dos
    clientes de e-mail (``prefers-color-scheme``), preservando o layout claro
    como fallback via estilos inline.
    """
    altos = sum(1 for a in alerts if a.get("severity") == "high")
    resumo = (
        f"Foram gerados <strong>{len(alerts)} alerta(s)</strong>, "
        f"sendo <strong>{altos} de severidade alta</strong>."
    )
    # Bloco de análise (insights) — converte o Markdown do resumo em HTML.
    bloco_ia = ""
    corpo_ia = _md_para_html(resumo_ia) if resumo_ia.strip() else ""
    if corpo_ia:
        bloco_ia = (
            f"<div style='background:{_HOVER};border:1px solid {_DIVISORIA};border-left:4px solid {_PENSO_BLUE};"
            "border-radius:10px;padding:14px 16px;margin:0 0 18px;' class='af-altcard'>"
            f"<div style='font-size:12px;color:{_PENSO_BLUE};font-weight:700;text-transform:uppercase;"
            "letter-spacing:.04em;margin-bottom:8px;'>🧠 Análise do dia</div>"
            f"{corpo_ia}"
            "</div>"
        )
    # Cabeçalho: identidade visual da Penso (marca-texto) + Analytical-Force.
    # TODO: quando o arquivo do logo real da Penso estiver disponível, trocar
    # este bloco por um <img> com o PNG/SVG oficial (base64 ou hospedado).
    # Por ora, usa apenas cores da marca (Penso Blue/Black) — sem inventar formas.
    cabecalho = f"""\
      <td class="af-px af-animate" style="background:linear-gradient(120deg,{_BLACK_INTENSE},{_BLUE_TECH} 55%,{_PENSO_BLUE});padding:26px 28px;">
        <table role="presentation" cellspacing="0" cellpadding="0"><tr>
          <td style="width:34px;height:34px;background:#ffffff;border-radius:9px;text-align:center;
                     vertical-align:middle;font-weight:800;font-size:16px;color:{_PENSO_BLUE};">P</td>
          <td style="padding-left:10px;color:#ffffff;font-size:13px;font-weight:700;letter-spacing:.03em;">PENSO</td>
        </tr></table>
        <div style="color:#ffffff;font-size:22px;font-weight:800;letter-spacing:.2px;margin-top:12px;">📊 Analytical-Force</div>
        <div style="color:#dbe4ff;font-size:13px;margin-top:4px;">Relatório diário de performance comercial</div>
        <span style="display:inline-block;margin-top:12px;background:rgba(255,255,255,.18);color:#ffffff;
              font-size:12px;font-weight:600;padding:5px 12px;border-radius:999px;">📅 {_escape(report_date)}</span>
      </td>"""
    rodape = f"""\
      <td class="af-footer af-px" style="background:{_HOVER};padding:16px 28px;border-top:1px solid {_DIVISORIA};">
        <table role="presentation" cellspacing="0" cellpadding="0"><tr>
          <td style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;padding-right:8px;">Fonte de dados</td>
          <td><img src="{_LOGO_SALESFORCE_URL}" alt="Salesforce" style="height:14px;vertical-align:middle;" /></td>
        </tr></table>
        <div class="af-muted" style="font-size:12px;color:#94a3b8;margin-top:10px;">
          Relatório gerado automaticamente pelo agente <strong>Analytical-Force</strong> (Penso).
          Os números são calculados em Python a partir do Salesforce; a interpretação
          é gerada por modelo local. O relatório completo está anexado/registrado no sistema.
        </div>
      </td>"""
    return f"""\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
{_estilo_cabecalho()}
</head>
<body class="af-wrap" style="margin:0;padding:0;background:#f1f5f9;">
<div class="af-wrap" style="background:#f1f5f9;padding:24px 0;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="640" align="center" cellspacing="0" cellpadding="0" class="af-container"
         style="max-width:640px;margin:0 auto;">
    <tr><td class="af-card" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid {_DIVISORIA};">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
{cabecalho}
    </tr>
    <tr>
      <td class="af-body af-px" style="padding:24px 28px;">
        <h3 style="font-size:14px;color:#0f172a;margin:0 0 10px;padding-left:10px;border-left:3px solid {_PENSO_BLUE};">Resumo executivo</h3>
        <p style="font-size:14px;color:#475569;margin:0 0 14px;line-height:1.55;">{resumo}</p>
        {bloco_ia}

        <h3 style="font-size:14px;color:#0f172a;margin:22px 0 10px;padding-left:10px;border-left:3px solid {_PENSO_BLUE};">Números-chave</h3>
        {_grade_kpis(metrics)}

        {_bloco_contratos(metrics)}

        <h3 style="font-size:14px;color:#0f172a;margin:22px 0 10px;padding-left:10px;border-left:3px solid {_ERRO};">Principais alertas</h3>
        {_bloco_alertas(alerts)}

        {_bloco_prioridades(alerts)}

        {_bloco_destaques_html(highlights or {})}
      </td>
    </tr>
    <tr>
{rodape}
    </tr>
    </table>
    </td></tr>
  </table>
</div>
</body>
</html>"""


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
    "oportunidades_criadas": "✨ Oportunidades criadas",
    "oportunidades_travadas": "🚧 Oportunidades travadas",
    "oportunidades_ganhas": "🏆 Oportunidades ganhas",
    "oportunidades_perdidas": "📉 Oportunidades perdidas",
    "cancelamentos": "❌ Cancelamentos",
    "satisfacoes_do_dia": "😊 Satisfações do dia",
    "satisfacoes_piores": "😟 Piores satisfações",
    "contratos_modificados": "📄 Contratos modificados",
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
    cc_emails: list[str] | None = None,
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
        cc_emails: E-mails adicionais em cópia (persistidos no Turso via
            ``ConfigRepository``, cadastrados pelo painel). Opcional.

    Returns:
        ``True`` se enviado; ``False`` se não configurado ou em caso de erro.
    """
    if not config.is_configured:
        logger.info("Envio de e-mail ignorado: nenhum método configurado.")
        return False

    resumo_ia = _extrair_resumo_ia(report_markdown)
    html = _montar_html(report_date, metrics, alerts, resumo_ia, highlights or {})
    texto = _montar_texto(report_date, metrics, alerts, resumo_ia)

    # Remove duplicados/vazios e evita repetir o destinatário principal em Cc.
    cc_limpo = sorted(
        {
            e.strip()
            for e in (cc_emails or [])
            if e.strip() and e.strip().lower() != config.recipient_email.strip().lower()
        }
    )

    remetente = config.gmail_sender or config.smtp_user or "analytical-force@localhost"
    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto
    mensagem["From"] = remetente
    mensagem["To"] = config.recipient_email
    if cc_limpo:
        mensagem["Cc"] = ", ".join(cc_limpo)
    mensagem.attach(MIMEText(texto, "plain", "utf-8"))
    mensagem.attach(MIMEText(html, "html", "utf-8"))

    # Gmail API tem prioridade (HTTPS; passa por firewalls que bloqueiam SMTP).
    if config.gmail_api_configured:
        return _enviar_via_gmail_api(config, mensagem)
    return _enviar_via_smtp(config, mensagem, cc_limpo)


def _enviar_via_smtp(
    config: EmailSettings, mensagem: MIMEMultipart, cc_emails: list[str] | None = None
) -> bool:
    """Envia a mensagem via SMTP (STARTTLS). Usado em ambiente local."""
    destinatarios = [config.recipient_email, *(cc_emails or [])]
    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as servidor:
            servidor.starttls()
            if config.smtp_user and config.smtp_password:
                servidor.login(config.smtp_user, config.smtp_password)
            servidor.sendmail(mensagem["From"], destinatarios, mensagem.as_string())
        logger.info(
            "Relatório enviado por e-mail (SMTP) para %s (cc=%d).",
            config.recipient_email,
            len(cc_emails or []),
        )
        return True
    except Exception as exc:  # não deve derrubar o agente
        # Loga o tipo e a mensagem do erro — o filtro de log já mascara
        # padrões de senha/token, então isso não expõe segredos. OSError
        # costuma indicar SMTP bloqueado pelo ambiente (ex.: Hugging Face).
        logger.error("Falha ao enviar e-mail (SMTP): %s: %s", type(exc).__name__, exc)
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
        # Loga o tipo e a mensagem do erro (sem expor token/segredo). O
        # RuntimeError de _obter_access_token_gmail já traz só o código de
        # erro OAuth (ex.: "invalid_grant") e a descrição do Google — o
        # filtro de log mascara qualquer padrão de token/senha por segurança.
        logger.error("Falha ao enviar e-mail (Gmail API): %s: %s", type(exc).__name__, exc)
        return False
