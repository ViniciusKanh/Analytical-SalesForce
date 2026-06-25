"""Queries SOQL parametrizáveis por data.

Cada função monta uma string SOQL pronta para execução. Os campos
customizados são injetados via :class:`FieldMapping`, permitindo que
organizações diferentes ajustem nomes sem alterar a lógica.

As datas/datetimes devem chegar já formatadas (ver ``utils.date_utils``):
- datetime: ISO 8601 com offset (ex.: ``2026-06-23T00:00:00-03:00``);
- date: ``YYYY-MM-DD``.
"""

from __future__ import annotations

from .field_mapping import FieldMapping

# Campos padrão por objeto (sempre presentes em orgs Salesforce).
_LEAD_BASE = [
    "Id",
    "Name",
    "Company",
    "Status",
    "LeadSource",
    "CreatedDate",
    "LastModifiedDate",
    "ConvertedDate",
    "IsConverted",
    "OwnerId",
    "Owner.Name",
]

_OPP_BASE = [
    "Id",
    "Name",
    "StageName",
    "Amount",
    "CreatedDate",
    "CloseDate",
    "LastModifiedDate",
    "LastActivityDate",
    "IsClosed",
    "IsWon",
    "HasOpenActivity",
    "HasOverdueTask",
    "OwnerId",
    "Probability",
    "ForecastCategory",
    "Type",
    "LeadSource",
    "Owner.Name",
]

_OPP_FECHADA = [
    "Id",
    "Name",
    "StageName",
    "Amount",
    "CreatedDate",
    "CloseDate",
    "LastModifiedDate",
    "IsClosed",
    "IsWon",
    "OwnerId",
]

_TASK_BASE = [
    "Id",
    "Subject",
    "Status",
    "Priority",
    "ActivityDate",
    "CreatedDate",
    "LastModifiedDate",
    "OwnerId",
    "WhoId",
    "WhatId",
    "IsClosed",
]


def _campos(*grupos: list[str]) -> str:
    """Concatena listas de campos em uma string SOQL, sem duplicar."""
    vistos: list[str] = []
    for grupo in grupos:
        for campo in grupo:
            if campo and campo not in vistos:
                vistos.append(campo)
    return ", ".join(vistos)


# ----------------------------------------------------------------------
# LEADS
# ----------------------------------------------------------------------
def leads_criados(start_datetime: str, end_datetime: str, fm: FieldMapping) -> str:
    """Leads criados no período [start, end)."""
    campos = _campos(_LEAD_BASE, fm.campos_lead_customizados())
    return (
        f"SELECT {campos} FROM Lead "
        f"WHERE CreatedDate >= {start_datetime} "
        f"AND CreatedDate < {end_datetime}"
    )


def leads_modificados(start_datetime: str, end_datetime: str, fm: FieldMapping) -> str:
    """Leads modificados no período [start, end)."""
    campos = _campos(_LEAD_BASE, fm.campos_lead_customizados())
    return (
        f"SELECT {campos} FROM Lead "
        f"WHERE LastModifiedDate >= {start_datetime} "
        f"AND LastModifiedDate < {end_datetime}"
    )


# ----------------------------------------------------------------------
# OPPORTUNITIES
# ----------------------------------------------------------------------
def oportunidades_abertas(fm: FieldMapping) -> str:
    """Todas as oportunidades abertas (IsClosed = false)."""
    campos = _campos(_OPP_BASE, fm.campos_opportunity_customizados())
    return f"SELECT {campos} FROM Opportunity WHERE IsClosed = false"


def oportunidades_criadas(
    start_datetime: str, end_datetime: str, fm: FieldMapping
) -> str:
    """Oportunidades criadas no período [start, end)."""
    campos = _campos(_OPP_BASE, fm.campos_opportunity_customizados())
    return (
        f"SELECT {campos} FROM Opportunity "
        f"WHERE CreatedDate >= {start_datetime} "
        f"AND CreatedDate < {end_datetime}"
    )


def oportunidades_fechadas(start_date: str, end_date: str, fm: FieldMapping) -> str:
    """Oportunidades fechadas no período [start, end) por CloseDate."""
    campos = _campos(_OPP_FECHADA, fm.campos_opportunity_customizados())
    return (
        f"SELECT {campos} FROM Opportunity "
        f"WHERE IsClosed = true "
        f"AND CloseDate >= {start_date} "
        f"AND CloseDate < {end_date}"
    )


# ----------------------------------------------------------------------
# TASKS
# ----------------------------------------------------------------------
def tarefas_do_periodo(start_datetime: str, end_datetime: str) -> str:
    """Tarefas criadas no período [start, end)."""
    campos = _campos(_TASK_BASE)
    return (
        f"SELECT {campos} FROM Task "
        f"WHERE CreatedDate >= {start_datetime} "
        f"AND CreatedDate < {end_datetime}"
    )


def tarefas_vencidas() -> str:
    """Tarefas vencidas (ActivityDate < TODAY) e ainda abertas."""
    campos = _campos(_TASK_BASE)
    return (
        f"SELECT {campos} FROM Task "
        f"WHERE ActivityDate < TODAY AND IsClosed = false"
    )


def tarefas_abertas_futuras() -> str:
    """Tarefas abertas com ActivityDate >= TODAY (próximas atividades)."""
    campos = _campos(_TASK_BASE)
    return (
        f"SELECT {campos} FROM Task "
        f"WHERE ActivityDate >= TODAY AND IsClosed = false"
    )


# ----------------------------------------------------------------------
# FONTES CONFIGURÁVEIS (Satisfação / Cancelamento)
# ----------------------------------------------------------------------
def registros_por_data(
    objeto: str, campos: list[str], date_field: str, dia_iso: str
) -> str:
    """Monta uma consulta por igualdade de data em um objeto configurável.

    Usada por fontes flexíveis (ex.: Satisfação por ``Reply_Date__c`` ou
    Cancelamento por ``DATA_CANCELAMENTO__c``). Os nomes de objeto/campos vêm
    de configuração validada — esta função não fixa nomes no código.

    Args:
        objeto: Nome da API do objeto (ex.: ``Satisfacao__c``).
        campos: Lista de campos a selecionar.
        date_field: Campo de data (tipo ``date``) usado no filtro.
        dia_iso: Data no formato ``YYYY-MM-DD``.

    Returns:
        String SOQL pronta (``SELECT ... WHERE date_field = dia``).
    """
    cols = _campos(campos)
    return f"SELECT {cols} FROM {objeto} WHERE {date_field} = {dia_iso}"
