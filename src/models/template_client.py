"""Cliente de template (relatório sem IA).

Gera o relatório diário em Markdown a partir do JSON de métricas já calculado
em Python. É o modo mais confiável e obrigatório do MVP: funciona sempre,
mesmo sem nenhum modelo de IA instalado.

Quando uma narrativa de IA é fornecida (``narrativa_ia``), ela substitui
apenas a seção de Resumo Executivo/diagnóstico — todos os números das demais
seções continuam vindo do cálculo em Python.
"""

from __future__ import annotations

from typing import Any

# Rótulos de severidade em português para exibição.
_ROTULO_SEVERIDADE = {"high": "🔴 Alta", "medium": "🟠 Média", "low": "🟡 Baixa"}


# ----------------------------------------------------------------------
# Helpers de formatação
# ----------------------------------------------------------------------
def _moeda(valor: Any) -> str:
    """Formata um número como moeda em Real (R$ 1.234,56)."""
    try:
        numero = float(valor or 0.0)
    except (TypeError, ValueError):
        return "R$ 0,00"
    inteiro = f"{numero:,.2f}"
    # Converte do padrão en-US (1,234.56) para pt-BR (1.234,56).
    inteiro = inteiro.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {inteiro}"


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
    """Formata um percentual (ex.: ``12.5`` → ``12,5%``)."""
    if valor is None:
        return "—"
    try:
        return f"{float(valor):.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _variacao(metricas: dict[str, Any], chave: str) -> str:
    """Monta um texto curto de variação (vs dia anterior / vs 7 dias)."""
    comparacoes = metricas.get("comparisons", {})
    item = comparacoes.get(chave)
    if not item:
        return ""
    partes: list[str] = []
    vp = item.get("variation_percent_vs_previous")
    if vp is not None:
        seta = "▲" if vp > 0 else ("▼" if vp < 0 else "▬")
        partes.append(f"{seta} {abs(vp):.1f}% vs ontem".replace(".", ","))
    v7 = item.get("variation_percent_vs_7day_avg")
    if v7 is not None:
        seta = "▲" if v7 > 0 else ("▼" if v7 < 0 else "▬")
        partes.append(f"{seta} {abs(v7):.1f}% vs 7d".replace(".", ","))
    return f" ({'; '.join(partes)})" if partes else ""


def _linha(rotulo: str, valor: str, sufixo: str = "") -> str:
    """Linha de lista Markdown padronizada (fato)."""
    return f"- **{rotulo}:** {valor}{sufixo}"


def _insight(texto: str) -> str:
    """Linha de insight (storytelling por regras) ao fim de uma seção."""
    return f"\n> 💡 **Insight:** {texto}"


# ----------------------------------------------------------------------
# Seções do relatório
# ----------------------------------------------------------------------
def _secao_oportunidades(m: dict[str, Any]) -> list[str]:
    linhas = ["## 2. Oportunidades", ""]
    if not m:
        linhas.append("_Sem dados de oportunidades no período._")
        return linhas
    linhas += [
        _linha("Novas", _num(m.get("new_opportunities")), _variacao(m, "new_opportunities")),
        _linha("Abertas", _num(m.get("open_opportunities")), _variacao(m, "open_opportunities")),
        _linha("Ganhas", _num(m.get("won_opportunities")), _variacao(m, "won_opportunities")),
        _linha("Perdidas", _num(m.get("lost_opportunities")), _variacao(m, "lost_opportunities")),
        _linha("Pipeline aberto", _moeda(m.get("open_pipeline_amount")), _variacao(m, "open_pipeline_amount")),
        _linha("Valor ganho", _moeda(m.get("won_amount")), _variacao(m, "won_amount")),
        _linha("Valor perdido", _moeda(m.get("lost_amount"))),
        _linha("Win rate", _pct(m.get("win_rate"))),
        _linha("Loss rate", _pct(m.get("loss_rate"))),
        _linha("Paradas (sem atividade)", _num(m.get("stalled_opportunities"))),
        _linha("Sem próxima tarefa", _num(m.get("opportunities_without_next_task"))),
        _linha("Alto valor paradas", _num(m.get("high_value_stalled_opportunities"))),
        _linha("Fecham no mês", _num(m.get("opportunities_closing_this_month"))),
    ]
    won = int(m.get("won_opportunities") or 0)
    lost = int(m.get("lost_opportunities") or 0)
    alto = int(m.get("high_value_stalled_opportunities") or 0)
    if alto:
        linhas.append(_insight(
            f"{alto} oportunidade(s) de alto valor parada(s) concentram o risco do dia — "
            "priorize o contato antes que esfriem."))
    elif won > lost:
        linhas.append(_insight(f"Saldo positivo: {won} ganha(s) contra {lost} perdida(s) hoje."))
    elif lost > won:
        linhas.append(_insight(
            f"Mais perdas que ganhos hoje ({lost} x {won}) — vale revisar objeções recorrentes."))
    return linhas


def _secao_leads(m: dict[str, Any]) -> list[str]:
    linhas = ["## 3. Leads", ""]
    if not m:
        linhas.append("_Sem dados de leads no período._")
        return linhas
    linhas += [
        _linha("Novos", _num(m.get("new_leads")), _variacao(m, "new_leads")),
        _linha("Convertidos", _num(m.get("converted_leads")), _variacao(m, "converted_leads")),
        _linha("Taxa de conversão", _pct(m.get("conversion_rate")), _variacao(m, "conversion_rate")),
        _linha("Sem primeira tarefa", _num(m.get("leads_without_first_task"))),
        _linha("Tempo médio até 1ª tarefa (h)", _num(m.get("avg_time_to_first_task_hours"))),
        _linha("Tempo mediano até 1ª tarefa (h)", _num(m.get("median_time_to_first_task_hours"))),
        _linha("Origem de maior volume", _num(m.get("top_lead_source_by_volume"))),
        _linha("Melhor origem (conversão)", _num(m.get("best_lead_source_by_conversion"))),
        _linha("Pior origem (conversão)", _num(m.get("worst_lead_source_by_conversion"))),
    ]
    sem = int(m.get("leads_without_first_task") or 0)
    conv = m.get("conversion_rate")
    if sem:
        linhas.append(_insight(
            f"{sem} lead(s) sem a primeira tarefa — o follow-up rápido é o ganho mais barato hoje."))
    elif isinstance(conv, (int, float)):
        linhas.append(_insight(
            f"Conversão do dia em {_pct(conv)}; acompanhe a melhor origem para replicar o que funciona."))
    return linhas


def _secao_tarefas(m: dict[str, Any]) -> list[str]:
    linhas = ["## 4. Tarefas", ""]
    if not m:
        linhas.append("_Sem dados de tarefas no período._")
        return linhas
    linhas += [
        _linha("Criadas", _num(m.get("tasks_created")), _variacao(m, "tasks_created")),
        _linha("Concluídas", _num(m.get("tasks_completed"))),
        _linha("Taxa de conclusão", _pct(m.get("completion_rate"))),
        _linha("Vencidas", _num(m.get("tasks_overdue")), _variacao(m, "tasks_overdue")),
        _linha("Futuras", _num(m.get("tasks_future"))),
        _linha("Vencidas ligadas a leads", _num(m.get("overdue_tasks_linked_to_leads"))),
        _linha("Vencidas ligadas a oportunidades", _num(m.get("overdue_tasks_linked_to_opportunities"))),
        _linha("Atraso médio das vencidas (dias)", _num(m.get("avg_overdue_delay_days"))),
    ]
    if m.get("top_overdue_owner"):
        linhas.append(
            _linha(
                "Responsável com mais vencidas",
                f"{m.get('top_overdue_owner')} ({_num(m.get('top_overdue_owner_count'))})",
            )
        )
    venc = int(m.get("tasks_overdue") or 0)
    taxa = m.get("completion_rate")
    if venc:
        linhas.append(_insight(
            f"{venc} tarefa(s) vencida(s) no total — concentre o esforço nas ligadas a negócios de maior valor."))
    elif isinstance(taxa, (int, float)):
        linhas.append(_insight(f"Taxa de conclusão do dia em {_pct(taxa)}."))
    return linhas


def _secao_satisfacao(m: dict[str, Any]) -> list[str]:
    linhas = ["## 5. Satisfação", ""]
    if not m or not m.get("configured"):
        msg = (m or {}).get("message") or (
            "Fonte de satisfação ainda não configurada. "
            "Configure o objeto e os campos em object_mapping."
        )
        linhas.append(f"> ⚙️ {msg}")
        return linhas
    if not m.get("responses"):
        linhas.append(f"> {m.get('message') or 'Sem respostas no período.'}")
        return linhas
    linhas += [
        _linha("Nota média", _num(m.get("avg_score")), _variacao(m, "avg_score")),
        _linha("Respostas", _num(m.get("responses"))),
        _linha("Avaliações negativas", _num(m.get("negative_count"))),
    ]
    motivos = m.get("top_negative_reasons") or {}
    if motivos:
        itens = ", ".join(f"{k} ({v})" for k, v in motivos.items())
        linhas.append(_linha("Principais motivos negativos", itens))
    neg = int(m.get("negative_count") or 0)
    avg = m.get("avg_score")
    if neg:
        linhas.append(_insight(
            f"{neg} avaliação(ões) negativa(s) — acione o CS para os clientes em risco antes que virem churn."))
    elif isinstance(avg, (int, float)):
        linhas.append(_insight(f"Satisfação média saudável em {_num(avg)}."))
    return linhas


def _secao_cancelamentos(m: dict[str, Any]) -> list[str]:
    linhas = ["## 6. Cancelamentos", ""]
    if not m or not m.get("configured"):
        msg = (m or {}).get("message") or (
            "Fonte de cancelamento ainda não configurada. "
            "Configure o objeto e os campos em object_mapping."
        )
        linhas.append(f"> ⚙️ {msg}")
        return linhas
    linhas += [
        _linha("Cancelamentos", _num(m.get("cancellations_count")), _variacao(m, "cancellations_count")),
        _linha("Impacto em MRR", _moeda(m.get("mrr_impact"))),
        _linha("Impacto em ARR", _moeda(m.get("arr_impact"))),
        _linha("Motivo principal", _num(m.get("top_reason"))),
    ]
    por_produto = m.get("cancellations_by_product") or {}
    if por_produto:
        itens = ", ".join(f"{k} ({v})" for k, v in por_produto.items())
        linhas.append(_linha("Por produto", itens))
    qtd = int(m.get("cancellations_count") or 0)
    if qtd:
        linhas.append(_insight(
            f"{qtd} cancelamento(s) somando {_moeda(m.get('mrr_impact'))} em MRR — "
            "acione retenção e investigue o motivo principal."))
    return linhas


def _secao_alertas(alertas: list[dict[str, Any]]) -> list[str]:
    linhas = ["## 7. Principais Alertas", ""]
    if not alertas:
        linhas.append("Nenhum alerta gerado para o período. ✅")
        return linhas
    for a in alertas:
        rotulo = _ROTULO_SEVERIDADE.get(a.get("severity", "low"), "🟡 Baixa")
        linhas.append(f"### {rotulo} — {a.get('title', '')}")
        linhas.append(f"- **Categoria:** {a.get('category', 'Geral')}")
        linhas.append(f"- **Diagnóstico:** {a.get('description', '')}")
        if a.get("recommended_action"):
            linhas.append(f"- **Ação recomendada:** {a['recommended_action']}")
        if a.get("source_object"):
            origem = a["source_object"]
            if a.get("source_record_id"):
                origem += f" ({a['source_record_id']})"
            linhas.append(f"- **Origem:** {origem}")
        linhas.append("")
    return linhas


def _secao_prioridades(alertas: list[dict[str, Any]]) -> list[str]:
    """Lista as ações recomendadas priorizadas pela severidade dos alertas."""
    linhas = ["## 8. Prioridades para Hoje", ""]
    acoes = [a for a in alertas if a.get("recommended_action")]
    if not acoes:
        linhas.append("Sem prioridades críticas. Manter rotina comercial padrão.")
        return linhas
    # Já vêm ordenados por severidade; pega as 5 primeiras ações.
    for i, a in enumerate(acoes[:5], start=1):
        rotulo = _ROTULO_SEVERIDADE.get(a.get("severity", "low"), "🟡 Baixa")
        linhas.append(f"{i}. [{rotulo}] {a['recommended_action']}")
    return linhas


def _pipeline_valor(opp: dict[str, Any]) -> Any:
    """Usa o valor de produtos (recorrente+pontual) quando houver; senão Amount."""
    pv = opp.get("open_pipeline_product_value")
    return pv if pv else opp.get("open_pipeline_amount")


def _resumo_executivo_template(payload: dict[str, Any]) -> list[str]:
    """Resumo executivo em **storytelling**, por regras (sem IA).

    Constrói uma narrativa executiva a partir das métricas calculadas,
    adaptando o tom ao cenário do dia (tranquilo, atenção ou crítico) e
    destacando os pontos que exigem ação. Nenhum número é inventado.
    """
    metrics = payload.get("metrics", {})
    leads = metrics.get("leads", {}) or {}
    opp = metrics.get("opportunities", {}) or {}
    tasks = metrics.get("tasks", {}) or {}
    sat = metrics.get("satisfaction", {}) or {}
    canc = metrics.get("cancellations", {}) or {}
    alertas = payload.get("alerts", []) or []
    altos = sum(1 for a in alertas if a.get("severity") == "high")
    data = payload.get("report_date", "o dia")

    # Tom de abertura conforme o cenário.
    if altos == 0:
        abertura = (
            f"O dia **{data}** transcorreu sob controle: a operação comercial não "
            "acumulou riscos altos e segue dentro do ritmo esperado."
        )
    elif altos <= 2:
        abertura = (
            f"O dia **{data}** pede atenção pontual: surgiram **{altos} risco(s) alto(s)** "
            "que, se tratados hoje, evitam impacto no funil."
        )
    else:
        abertura = (
            f"O dia **{data}** exige ação imediata: são **{altos} riscos altos** "
            "concentrados que podem comprometer pipeline e receita se não forem endereçados."
        )

    # Capítulo Leads.
    novos = _num(leads.get("new_leads"))
    conv = _pct(leads.get("conversion_rate"))
    sem_tarefa = int(leads.get("leads_without_first_task") or 0)
    cap_leads = (
        f"Na entrada do funil, **{novos} novo(s) lead(s)** chegaram com conversão de "
        f"**{conv}**{_variacao(leads, 'conversion_rate')}."
    )
    if sem_tarefa:
        cap_leads += (
            f" Há **{sem_tarefa} lead(s) sem a primeira tarefa**, ou seja, contatos novos "
            "ainda sem follow-up — o ponto mais barato de corrigir agora."
        )

    # Capítulo Oportunidades.
    ganhas = _num(opp.get("won_opportunities"))
    perdidas = _num(opp.get("lost_opportunities"))
    pipeline = _moeda(_pipeline_valor(opp))
    paradas = int(opp.get("stalled_opportunities") or 0)
    alto_valor = int(opp.get("high_value_stalled_opportunities") or 0)
    cap_opp = (
        f"No pipeline, o valor em aberto soma **{pipeline}**"
        f"{_variacao(opp, 'open_pipeline_amount')}, com **{ganhas} ganha(s)** e "
        f"**{perdidas} perdida(s)** fechando no dia."
    )
    if alto_valor:
        cap_opp += (
            f" O sinal mais sensível: **{alto_valor} oportunidade(s) de alto valor parada(s)** — "
            "negócios relevantes que estão esfriando e merecem contato prioritário."
        )
    elif paradas:
        cap_opp += f" Ainda há **{paradas} oportunidade(s) parada(s)** aguardando reengajamento."

    # Capítulo operação (tarefas) — sem alarmismo.
    venc = int(tasks.get("tasks_overdue") or 0)
    cap_ops = ""
    if venc:
        cap_ops = (
            f"Na operação, o backlog registra **{venc} tarefa(s) vencida(s)**; o foco do dia "
            "deve recair sobre as ligadas a negócios de maior valor."
        )

    # Capítulo cliente (satisfação/cancelamento), se configurado.
    cap_cliente = ""
    if sat.get("configured") and sat.get("responses"):
        cap_cliente += (
            f"Do lado do cliente, a satisfação média ficou em **{_num(sat.get('avg_score'))}** "
            f"com **{_num(sat.get('negative_count'))} avaliação(ões) negativa(s)**."
        )
    if canc.get("configured") and canc.get("cancellations_count"):
        cap_cliente += (
            f" Foram **{_num(canc.get('cancellations_count'))} cancelamento(s)**, impacto de "
            f"**{_moeda(canc.get('mrr_impact'))}** em MRR — atenção à retenção."
        )

    # Fecho com direção.
    if altos:
        titulos = "; ".join(a.get("title", "") for a in alertas if a.get("severity") == "high")
        fecho = (
            f"**Direção para hoje:** priorizar {titulos.lower()}. As ações detalhadas estão "
            "na seção de Prioridades."
        )
    else:
        fecho = (
            "**Direção para hoje:** manter a cadência, acompanhar as variações sinalizadas e "
            "antecipar follow-ups dos negócios de maior valor."
        )

    paragrafos = [abertura, cap_leads, cap_opp]
    if cap_ops:
        paragrafos.append(cap_ops)
    if cap_cliente:
        paragrafos.append(cap_cliente.strip())
    paragrafos.append(fecho)
    return ["## 1. Resumo Executivo", "", "\n\n".join(paragrafos)]


def gerar_plano_acao(alerta: dict[str, Any]) -> str:
    """Gera um plano de ação em storytelling para um alerta (por regras, sem IA).

    Usa o diagnóstico, a ação recomendada e os registros afetados do próprio
    alerta para montar um texto acionável — sem inventar dados.
    """
    categoria = alerta.get("category", "Geral")
    descricao = alerta.get("description", "").strip()
    acao = alerta.get("recommended_action", "").strip()
    registros = alerta.get("affected_records") or []

    linhas: list[str] = []
    if descricao:
        linhas.append(f"**O que está acontecendo:** {descricao}")
    # Por que importa (por categoria).
    porques = {
        "Oportunidades": "Cada dia parado reduz a probabilidade de fechamento e trava o pipeline.",
        "Leads": "Lead sem follow-up rápido esfria — a janela de conversão é curta.",
        "Tarefas": "Tarefas vencidas acumulam e mascaram o que é realmente prioritário.",
        "Satisfação": "Clientes insatisfeitos hoje são risco de churn amanhã.",
        "Cancelamentos": "Cancelamentos atacam diretamente a receita recorrente.",
    }
    if porques.get(categoria):
        linhas.append(f"**Por que importa:** {porques[categoria]}")
    if acao:
        linhas.append(f"**Plano sugerido:** {acao}")
    if registros:
        linhas.append("**Comece por (maior valor/risco primeiro):**")
        for r in registros[:5]:
            partes = [str(r.get("name") or r.get("id") or "registro")]
            if r.get("info"):
                partes.append(str(r["info"]))
            if r.get("amount") is not None:
                partes.append(_moeda(r["amount"]))
            if r.get("owner"):
                partes.append(f"resp.: {r['owner']}")
            linhas.append("- " + " — ".join(partes))
    return "\n".join(linhas).strip()


def _conclusao_template(payload: dict[str, Any]) -> list[str]:
    """Conclusão objetiva, sempre ligada a métricas/alertas."""
    alertas = payload.get("alerts", []) or []
    altos = [a for a in alertas if a.get("severity") == "high"]
    linhas = ["## 9. Conclusão", ""]
    if altos:
        titulos = "; ".join(a.get("title", "") for a in altos[:3])
        linhas.append(
            f"O dia apresenta **{len(altos)} risco(s) alto(s)** que devem ser tratados "
            f"prioritariamente: {titulos}. As ações da seção 8 atacam esses pontos."
        )
    else:
        linhas.append(
            "Sem riscos altos no período. Manter o ritmo e monitorar as variações "
            "indicadas nas seções anteriores."
        )
    return linhas


# ----------------------------------------------------------------------
# Função principal
# ----------------------------------------------------------------------
def renderizar_relatorio(
    payload: dict[str, Any], narrativa_ia: str | None = None
) -> str:
    """Renderiza o relatório diário completo em Markdown.

    Args:
        payload: JSON estruturado com ``metrics``, ``alerts`` e ``data_quality``.
        narrativa_ia: Texto interpretativo opcional gerado por um modelo de IA.
            Quando presente, substitui o Resumo Executivo baseado em regras.

    Returns:
        Relatório completo em Markdown (9 seções obrigatórias).
    """
    metrics = payload.get("metrics", {})
    alertas = payload.get("alerts", []) or []
    data_report = payload.get("report_date", "")

    linhas: list[str] = [
        "# Relatório Diário — Analytical-Force",
        "",
        f"**Data de referência:** {data_report}  ",
        f"**Fuso:** {payload.get('timezone', 'America/Sao_Paulo')}",
        "",
    ]

    # 1. Resumo Executivo (IA ou template).
    if narrativa_ia and narrativa_ia.strip():
        linhas += ["## 1. Resumo Executivo", "", narrativa_ia.strip()]
    else:
        linhas += _resumo_executivo_template(payload)
    linhas.append("")

    # 2-6. Seções factuais (sempre calculadas em Python).
    linhas += _secao_oportunidades(metrics.get("opportunities", {}) or {})
    linhas.append("")
    linhas += _secao_leads(metrics.get("leads", {}) or {})
    linhas.append("")
    linhas += _secao_tarefas(metrics.get("tasks", {}) or {})
    linhas.append("")
    linhas += _secao_satisfacao(metrics.get("satisfaction", {}) or {})
    linhas.append("")
    linhas += _secao_cancelamentos(metrics.get("cancellations", {}) or {})
    linhas.append("")

    # 7-9. Alertas, prioridades e conclusão.
    linhas += _secao_alertas(alertas)
    linhas.append("")
    linhas += _secao_prioridades(alertas)
    linhas.append("")
    linhas += _conclusao_template(payload)
    linhas.append("")

    # Rodapé de rastreabilidade.
    dq = payload.get("data_quality", {})
    linhas += [
        "---",
        f"_Gerado por Analytical-Force • conexão Salesforce: "
        f"{dq.get('salesforce_connection', 'desconhecida')} • "
        f"satisfação configurada: {dq.get('satisfaction_configured', False)} • "
        f"cancelamento configurado: {dq.get('cancellation_configured', False)}._",
    ]
    return "\n".join(linhas)
