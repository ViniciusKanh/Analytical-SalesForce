"""Cálculo de métricas de Tarefas (Task).

Todos os indicadores são calculados em Python a partir de DataFrames pandas.
A função principal é :func:`calculate_task_metrics`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from .comparison_metrics import aplicar_comparacoes
from ..utils.date_utils import agora_tz
from ..utils.validators import arredondar, coluna_existe, is_dataframe_vazio

# Prefixos de Id do Salesforce usados para classificar o vínculo da tarefa.
PREFIXO_ID_LEAD = "00Q"          # WhoId de Lead
PREFIXO_ID_OPPORTUNITY = "006"   # WhatId de Opportunity

# Chaves numéricas comparáveis contra histórico.
_CHAVES_COMPARAVEIS = [
    "tasks_created",
    "tasks_completed",
    "tasks_overdue",
    "tasks_future",
    "overdue_tasks_linked_to_leads",
    "overdue_tasks_linked_to_opportunities",
    "avg_overdue_delay_days",
]


def _eh_concluida(df: pd.DataFrame) -> pd.Series:
    """Série booleana indicando tarefas concluídas (IsClosed ou Status)."""
    if coluna_existe(df, "IsClosed"):
        return df["IsClosed"].fillna(False).astype(bool)
    if coluna_existe(df, "Status"):
        return df["Status"].astype(str).str.lower().eq("completed")
    return pd.Series([False] * len(df), index=df.index)


def _contagem_por_responsavel(df: pd.DataFrame) -> dict[str, int]:
    """Conta tarefas por ``OwnerId`` (responsável)."""
    if not coluna_existe(df, "OwnerId"):
        return {}
    contagem = df["OwnerId"].fillna("Sem responsável").value_counts()
    return {str(k): int(v) for k, v in contagem.items()}


def _atraso_medio_dias(df: pd.DataFrame, referencia: datetime) -> float | None:
    """Atraso médio (em dias) das tarefas vencidas, com base em ActivityDate.

    As datas são interpretadas em UTC para evitar erro de soma entre datas
    com e sem timezone (o extrator normaliza datas para tz-aware).
    """
    if is_dataframe_vazio(df) or not coluna_existe(df, "ActivityDate"):
        return None
    datas = pd.to_datetime(df["ActivityDate"], errors="coerce", utc=True)
    ref = pd.Timestamp(referencia.date(), tz="UTC")
    atraso = (ref - datas).dt.total_seconds() / 86400.0
    validos = atraso[atraso.notna() & (atraso >= 0)]
    if validos.empty:
        return None
    return arredondar(float(validos.mean()), 2)


def _vinculadas_por_prefixo(df: pd.DataFrame, coluna: str, prefixo: str) -> int:
    """Conta registros cujo Id na coluna começa com o prefixo informado."""
    if not coluna_existe(df, coluna):
        return 0
    serie = df[coluna].dropna().astype(str)
    return int(serie.str.startswith(prefixo).sum())


def calculate_task_metrics(
    tasks_created_df: pd.DataFrame,
    tasks_overdue_df: pd.DataFrame,
    tasks_future_df: pd.DataFrame,
    previous_metrics: dict[str, Any] | None = None,
    seven_day_average: dict[str, float] | None = None,
    reference_date: date | None = None,
    timezone: str = "America/Sao_Paulo",
) -> dict[str, Any]:
    """Calcula as métricas diárias de Tarefas.

    Args:
        tasks_created_df: Tarefas criadas no dia.
        tasks_overdue_df: Tarefas vencidas e ainda abertas.
        tasks_future_df: Tarefas abertas com data futura (próximas atividades).
        previous_metrics: Métricas do dia anterior (para variação).
        seven_day_average: Média de 7 dias por métrica (para variação).
        reference_date: Data de referência (apenas informativa).
        timezone: Fuso para cálculo de atraso.

    Returns:
        Dicionário de métricas de Tarefas, incluindo comparações.
    """
    agora = agora_tz(timezone)

    tasks_created = 0 if is_dataframe_vazio(tasks_created_df) else int(len(tasks_created_df))
    tasks_overdue = 0 if is_dataframe_vazio(tasks_overdue_df) else int(len(tasks_overdue_df))
    tasks_future = 0 if is_dataframe_vazio(tasks_future_df) else int(len(tasks_future_df))

    # --- Concluídas entre as criadas ---
    tasks_completed = 0
    if not is_dataframe_vazio(tasks_created_df):
        tasks_completed = int(_eh_concluida(tasks_created_df).sum())

    # --- Por responsável (criadas e vencidas) ---
    tasks_by_owner = _contagem_por_responsavel(tasks_created_df) if not is_dataframe_vazio(
        tasks_created_df
    ) else {}
    overdue_by_owner = _contagem_por_responsavel(tasks_overdue_df) if not is_dataframe_vazio(
        tasks_overdue_df
    ) else {}

    # --- Vencidas ligadas a Lead / Opportunity ---
    overdue_linked_leads = _vinculadas_por_prefixo(
        tasks_overdue_df, "WhoId", PREFIXO_ID_LEAD
    )
    overdue_linked_opps = _vinculadas_por_prefixo(
        tasks_overdue_df, "WhatId", PREFIXO_ID_OPPORTUNITY
    )

    # --- Atraso médio das vencidas ---
    avg_overdue_delay = _atraso_medio_dias(tasks_overdue_df, agora)

    # --- Responsável com mais tarefas vencidas (auxílio ao motor de risco) ---
    top_overdue_owner = None
    top_overdue_owner_count = 0
    if overdue_by_owner:
        top_overdue_owner = max(overdue_by_owner, key=overdue_by_owner.get)
        top_overdue_owner_count = int(overdue_by_owner[top_overdue_owner])

    metricas: dict[str, Any] = {
        "tasks_created": tasks_created,
        "tasks_completed": tasks_completed,
        "tasks_overdue": tasks_overdue,
        "tasks_future": tasks_future,
        "completion_rate": 0.0,
        "overdue_tasks_linked_to_leads": overdue_linked_leads,
        "overdue_tasks_linked_to_opportunities": overdue_linked_opps,
        "avg_overdue_delay_days": avg_overdue_delay,
        "tasks_by_owner": tasks_by_owner,
        "overdue_by_owner": overdue_by_owner,
        "top_overdue_owner": top_overdue_owner,
        "top_overdue_owner_count": top_overdue_owner_count,
    }
    # Taxa de conclusão sobre o que foi criado no dia.
    if tasks_created:
        metricas["completion_rate"] = round(tasks_completed / tasks_created * 100.0, 2)

    # --- Comparações históricas ---
    comparacoes = aplicar_comparacoes(
        metricas, previous_metrics, seven_day_average, _CHAVES_COMPARAVEIS
    )
    metricas["variation_vs_previous_day"] = {
        k: v["variation_vs_previous"] for k, v in comparacoes.items()
    }
    metricas["variation_vs_7day_average"] = {
        k: v["variation_vs_7day_avg"] for k, v in comparacoes.items()
    }
    metricas["comparisons"] = comparacoes
    return metricas
