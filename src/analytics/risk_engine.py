"""Motor de risco do Analytical-Force.

Recebe as métricas já calculadas em Python e gera uma lista de alertas
classificados em ``low``, ``medium`` e ``high``. NÃO recalcula indicadores —
apenas aplica regras de negócio sobre os números prontos.

Cada alerta segue o contrato:
    {
        "severity": "low|medium|high",
        "category": "Leads|Oportunidades|Tarefas|Satisfação|Cancelamentos",
        "title": str,
        "description": str,
        "recommended_action": str,
        "source_object": str | None,
        "source_record_id": str | None,
    }
"""

from __future__ import annotations

from typing import Any

from ..config.settings import RiskSettings
from ..utils.logger import get_logger
from ..utils.validators import normalizar_severidade

logger = get_logger("analytics.risk_engine")

# Ordem de severidade para ordenação final (maior primeiro).
_ORDEM_SEVERIDADE = {"high": 0, "medium": 1, "low": 2}


def _alerta(
    severity: str,
    category: str,
    title: str,
    description: str,
    recommended_action: str,
    source_object: str | None = None,
    source_record_id: str | None = None,
    affected_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Cria um dicionário de alerta padronizado.

    ``affected_records`` carrega os registros concretos relacionados ao alerta
    (nome, valor, dono, etc.), usados para montar tarefas ricas e acionáveis.
    """
    return {
        "severity": normalizar_severidade(severity),
        "category": category,
        "title": title,
        "description": description,
        "recommended_action": recommended_action,
        "source_object": source_object,
        "source_record_id": source_record_id,
        "affected_records": affected_records or [],
    }


def _var_percent_anterior(metricas: dict[str, Any], chave: str) -> float | None:
    """Lê a variação percentual vs dia anterior de uma métrica (ou None)."""
    comparacoes = metricas.get("comparisons", {})
    item = comparacoes.get(chave, {})
    return item.get("variation_percent_vs_previous")


def _var_percent_7dias(metricas: dict[str, Any], chave: str) -> float | None:
    """Lê a variação percentual vs média de 7 dias de uma métrica (ou None)."""
    comparacoes = metricas.get("comparisons", {})
    item = comparacoes.get(chave, {})
    return item.get("variation_percent_vs_7day_avg")


def _alertas_leads(m: dict[str, Any], risk: RiskSettings) -> list[dict[str, Any]]:
    """Regras de risco para Leads."""
    alertas: list[dict[str, Any]] = []
    sem_tarefa = int(m.get("leads_without_first_task", 0) or 0)
    if sem_tarefa > 0:
        severidade = "high" if sem_tarefa >= 5 else "medium"
        alertas.append(
            _alerta(
                severidade,
                "Leads",
                f"{sem_tarefa} lead(s) sem primeira tarefa",
                f"Há {sem_tarefa} lead(s) criados sem follow-up registrado, "
                f"acima do limite de {risk.lead_max_hours_without_task}h sem ação.",
                "Distribuir e agendar a primeira tarefa de contato para esses leads.",
                source_object="Lead",
            )
        )

    avg_first = m.get("avg_time_to_first_task_hours")
    if isinstance(avg_first, (int, float)) and avg_first > risk.lead_first_task_target_hours:
        alertas.append(
            _alerta(
                "medium",
                "Leads",
                "Tempo até primeira tarefa acima da meta",
                f"Tempo médio até a primeira tarefa é {avg_first}h, "
                f"acima da meta de {risk.lead_first_task_target_hours}h.",
                "Revisar a cadência de prospecção e a distribuição de leads.",
                source_object="Lead",
            )
        )

    var_conv = _var_percent_anterior(m, "conversion_rate")
    if var_conv is not None and var_conv <= -risk.conversion_drop_threshold_percent:
        alertas.append(
            _alerta(
                "medium",
                "Leads",
                "Queda na taxa de conversão",
                f"Conversão caiu {abs(var_conv):.1f}% em relação ao dia anterior "
                f"(limite de alerta: {risk.conversion_drop_threshold_percent:.0f}%).",
                "Investigar qualidade dos leads e abordagem comercial recente.",
                source_object="Lead",
            )
        )

    var_conv_7d = _var_percent_7dias(m, "conversion_rate")
    if var_conv_7d is not None and var_conv_7d < 0:
        alertas.append(
            _alerta(
                "medium",
                "Leads",
                "Conversão abaixo da média de 7 dias",
                f"Conversão está {abs(var_conv_7d):.1f}% abaixo da média dos últimos 7 dias.",
                "Comparar com origens de melhor desempenho e ajustar o foco.",
                source_object="Lead",
            )
        )
    return alertas


def _alertas_oportunidades(m: dict[str, Any], risk: RiskSettings) -> list[dict[str, Any]]:
    """Regras de risco para Oportunidades."""
    alertas: list[dict[str, Any]] = []

    alto_valor_paradas = int(m.get("high_value_stalled_opportunities", 0) or 0)
    if alto_valor_paradas > 0:
        # Usa os IDs/detalhes do SUBCONJUNTO de alto valor (não da lista geral).
        ids = m.get("high_value_stalled_opportunity_ids") or []
        detalhes = m.get("high_value_stalled_details") or []
        alertas.append(
            _alerta(
                "high",
                "Oportunidades",
                f"{alto_valor_paradas} oportunidade(s) de alto valor parada(s)",
                f"{alto_valor_paradas} oportunidade(s) acima de "
                f"R$ {risk.high_value_opportunity_amount:,.0f} sem atividade recente.",
                "Priorizar contato imediato e definir próximo passo nessas oportunidades.",
                source_object="Opportunity",
                source_record_id=str(ids[0]) if ids else None,
                affected_records=detalhes,
            )
        )

    paradas = int(m.get("stalled_opportunities", 0) or 0)
    if paradas > 0:
        ids = m.get("stalled_opportunity_ids") or []
        detalhes = m.get("stalled_opportunity_details") or []
        alertas.append(
            _alerta(
                "high",
                "Oportunidades",
                f"{paradas} oportunidade(s) parada(s)",
                f"{paradas} oportunidade(s) aberta(s) sem atividade há mais de "
                f"{risk.opportunity_max_days_without_activity} dias.",
                "Reengajar essas oportunidades ou reavaliar a previsão de fechamento.",
                source_object="Opportunity",
                source_record_id=str(ids[0]) if ids else None,
                affected_records=detalhes,
            )
        )

    sem_tarefa = int(m.get("opportunities_without_next_task", 0) or 0)
    if sem_tarefa > 0:
        ids = m.get("opportunities_without_task_ids") or []
        detalhes = m.get("opportunities_without_task_details") or []
        alertas.append(
            _alerta(
                "high",
                "Oportunidades",
                f"{sem_tarefa} oportunidade(s) sem próxima tarefa",
                f"{sem_tarefa} oportunidade(s) aberta(s) sem nenhuma atividade futura agendada.",
                "Agendar a próxima ação comercial para cada oportunidade aberta.",
                source_object="Opportunity",
                source_record_id=str(ids[0]) if ids else None,
                affected_records=detalhes,
            )
        )

    var_pipeline = _var_percent_anterior(m, "open_pipeline_amount")
    if var_pipeline is not None and var_pipeline <= -risk.pipeline_drop_threshold_percent:
        alertas.append(
            _alerta(
                "medium",
                "Oportunidades",
                "Queda no pipeline aberto",
                f"Pipeline aberto caiu {abs(var_pipeline):.1f}% vs dia anterior "
                f"(limite: {risk.pipeline_drop_threshold_percent:.0f}%).",
                "Verificar perdas recentes e ritmo de geração de novas oportunidades.",
                source_object="Opportunity",
            )
        )

    var_ganho = _var_percent_anterior(m, "won_amount")
    if var_ganho is not None and var_ganho < 0:
        alertas.append(
            _alerta(
                "medium",
                "Oportunidades",
                "Queda no valor ganho",
                f"Valor ganho caiu {abs(var_ganho):.1f}% em relação ao dia anterior.",
                "Analisar negócios fechados e foco da equipe comercial.",
                source_object="Opportunity",
            )
        )

    var_perdidas = _var_percent_anterior(m, "lost_opportunities")
    if var_perdidas is not None and var_perdidas > 0:
        alertas.append(
            _alerta(
                "medium",
                "Oportunidades",
                "Aumento de oportunidades perdidas",
                f"Oportunidades perdidas subiram {var_perdidas:.1f}% vs dia anterior.",
                "Revisar motivos de perda e objeções recorrentes.",
                source_object="Opportunity",
            )
        )
    return alertas


def _alertas_tarefas(m: dict[str, Any], risk: RiskSettings) -> list[dict[str, Any]]:
    """Regras de risco para Tarefas.

    Observação: por decisão do projeto, NÃO geramos alertas de "tarefas vencidas
    ligadas a oportunidades" nem de "responsável com mais tarefas vencidas" —
    o volume de tarefas vencidas é muito alto e gerava ruído. Esses números
    continuam disponíveis nas métricas, mas não viram alerta/tarefa.
    """
    alertas: list[dict[str, Any]] = []

    var_venc = _var_percent_anterior(m, "tasks_overdue")
    if var_venc is not None and var_venc > 0:
        alertas.append(
            _alerta(
                "medium",
                "Tarefas",
                "Aumento de tarefas vencidas",
                f"Tarefas vencidas aumentaram {var_venc:.1f}% em relação ao dia anterior.",
                "Mobilizar a equipe para zerar o backlog de tarefas vencidas.",
                source_object="Task",
            )
        )

    taxa = m.get("completion_rate")
    criadas = int(m.get("tasks_created", 0) or 0)
    if criadas > 0 and isinstance(taxa, (int, float)) and taxa < 50.0:
        alertas.append(
            _alerta(
                "medium",
                "Tarefas",
                "Baixa taxa de conclusão de tarefas",
                f"Apenas {taxa:.1f}% das tarefas criadas no dia foram concluídas.",
                "Verificar gargalos de execução e prioridades da equipe.",
                source_object="Task",
            )
        )
    return alertas


def _alertas_satisfacao(m: dict[str, Any], risk: RiskSettings) -> list[dict[str, Any]]:
    """Regra de risco ÚNICA para Satisfação (nota, negativas, comentários e queda).

    Tudo que diz respeito à nota/satisfação é consolidado em um único alerta,
    para não fragmentar (ex.: evitar "nota baixa" + "comentário crítico" separados).
    """
    if not m.get("configured"):
        return []

    avg = m.get("avg_score")
    negativos = int(m.get("negative_count") or 0)
    comentarios = m.get("critical_comments") or []
    var_7d = _var_percent_7dias(m, "avg_score")

    nota_baixa = isinstance(avg, (int, float)) and avg < risk.satisfaction_min_score
    caindo = var_7d is not None and var_7d < 0
    if not (nota_baixa or negativos or comentarios or caindo):
        return []

    partes: list[str] = []
    if nota_baixa:
        partes.append(f"nota média {avg} abaixo da meta ({risk.satisfaction_min_score})")
    if negativos:
        partes.append(f"{negativos} avaliação(ões) negativa(s)")
    if comentarios:
        partes.append(f"{len(comentarios)} comentário(s) crítico(s)")
    if caindo:
        partes.append(f"queda de {abs(var_7d):.1f}% vs média de 7 dias")

    severidade = "high" if (nota_baixa or comentarios) else "medium"
    return [
        _alerta(
            severidade,
            "Satisfação",
            "Satisfação em risco",
            "Pontos de atenção em satisfação: " + "; ".join(partes) + ".",
            "Acionar o CS: contatar os clientes negativos e revisar os "
            "comentários críticos do dia.",
        )
    ]


def _alertas_cancelamento(m: dict[str, Any], risk: RiskSettings) -> list[dict[str, Any]]:
    """Regras de risco para Cancelamentos (somente se configurado)."""
    if not m.get("configured"):
        return []
    alertas: list[dict[str, Any]] = []

    qtd = int(m.get("cancellations_count", 0) or 0)
    mrr = float(m.get("mrr_impact", 0.0) or 0.0)

    if qtd > 0 and mrr >= risk.high_value_opportunity_amount:
        alertas.append(
            _alerta(
                "high",
                "Cancelamentos",
                "Cancelamento com alto impacto financeiro",
                f"{qtd} cancelamento(s) somando impacto de R$ {mrr:,.0f} em MRR.",
                "Acionar retenção e revisar contratos de maior valor.",
            )
        )
    elif qtd > 0:
        alertas.append(
            _alerta(
                "medium",
                "Cancelamentos",
                f"{qtd} cancelamento(s) no período",
                f"Foram registrados {qtd} cancelamento(s). Motivo principal: "
                f"{m.get('top_reason') or 'não informado'}.",
                "Analisar motivos e iniciar ações de retenção.",
            )
        )

    # Mais de um cancelamento no mesmo produto.
    por_produto = m.get("cancellations_by_product") or {}
    for produto, total in por_produto.items():
        if isinstance(total, int) and total > 1:
            alertas.append(
                _alerta(
                    "high",
                    "Cancelamentos",
                    f"Cancelamentos recorrentes no produto {produto}",
                    f"{total} cancelamentos no produto {produto} no período.",
                    "Investigar causa específica do produto e priorizar correção.",
                )
            )
    return alertas


def generate_alerts(
    metrics: dict[str, Any],
    risk: RiskSettings,
    data_quality: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Gera todos os alertas a partir das métricas calculadas.

    Args:
        metrics: Métricas aninhadas ``{leads, opportunities, tasks,
            satisfaction, cancellations}``.
        risk: Limiares configuráveis do motor de risco.
        data_quality: Sinais de qualidade de dados (gera alertas informativos).

    Returns:
        Lista de alertas ordenada por severidade (high → low).
    """
    alertas: list[dict[str, Any]] = []

    alertas += _alertas_leads(metrics.get("leads", {}) or {}, risk)
    alertas += _alertas_oportunidades(metrics.get("opportunities", {}) or {}, risk)
    alertas += _alertas_tarefas(metrics.get("tasks", {}) or {}, risk)
    alertas += _alertas_satisfacao(metrics.get("satisfaction", {}) or {}, risk)
    alertas += _alertas_cancelamento(metrics.get("cancellations", {}) or {}, risk)

    # Alertas informativos de qualidade de dados (severidade baixa).
    if data_quality:
        if data_quality.get("salesforce_connection") not in (None, "ok"):
            alertas.append(
                _alerta(
                    "high",
                    "Dados",
                    "Falha de conexão com o Salesforce",
                    "A extração do Salesforce não foi concluída com sucesso.",
                    "Verificar credenciais e disponibilidade da API do Salesforce.",
                )
            )

    alertas.sort(key=lambda a: _ORDEM_SEVERIDADE.get(a["severity"], 99))
    logger.info("Motor de risco gerou %d alerta(s).", len(alertas))
    return alertas
