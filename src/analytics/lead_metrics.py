"""Cálculo de métricas de Leads.

Todos os indicadores são calculados em Python a partir de DataFrames pandas.
A função principal é :func:`calculate_lead_metrics`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .comparison_metrics import aplicar_comparacoes
from ..utils.validators import arredondar, is_dataframe_vazio, percentual

# Chaves numéricas comparáveis contra histórico.
_CHAVES_COMPARAVEIS = [
    "new_leads",
    "converted_leads",
    "conversion_rate",
    "leads_without_first_task",
    "avg_time_to_first_task_hours",
    "median_time_to_first_task_hours",
]


def _tem_primeira_tarefa(valor: Any) -> bool:
    """Indica se o campo de primeira tarefa está preenchido.

    Aceita datetime, string não vazia ou booleano verdadeiro.
    """
    if valor is None:
        return False
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, float) and valor != valor:  # NaN
        return False
    texto = str(valor).strip().lower()
    return texto not in {"", "nan", "nat", "none", "false", "0"}


def _horas_ate_primeira_tarefa(
    df: pd.DataFrame, first_task_field: str
) -> list[float]:
    """Calcula, em horas, o tempo entre criação do lead e a primeira tarefa.

    Considera apenas linhas em que o campo de primeira tarefa é uma data válida.
    """
    if is_dataframe_vazio(df) or first_task_field not in df.columns:
        return []
    if "CreatedDate" not in df.columns:
        return []

    criado = pd.to_datetime(df["CreatedDate"], errors="coerce", utc=True)
    primeira = pd.to_datetime(df[first_task_field], errors="coerce", utc=True)
    delta = (primeira - criado).dt.total_seconds() / 3600.0
    # Mantém apenas valores válidos e não negativos.
    validos = delta[(delta.notna()) & (delta >= 0)]
    return [float(h) for h in validos.tolist()]


def _conversao_por_origem(df_modificados: pd.DataFrame) -> dict[str, float]:
    """Calcula a taxa de conversão (%) por LeadSource nos leads modificados."""
    if is_dataframe_vazio(df_modificados):
        return {}
    if "LeadSource" not in df_modificados.columns or "IsConverted" not in df_modificados.columns:
        return {}

    df = df_modificados.copy()
    df["LeadSource"] = df["LeadSource"].fillna("Sem origem")
    df["IsConverted"] = df["IsConverted"].fillna(False).astype(bool)

    resultado: dict[str, float] = {}
    for origem, grupo in df.groupby("LeadSource"):
        total = len(grupo)
        convertidos = int(grupo["IsConverted"].sum())
        if total > 0:
            resultado[str(origem)] = percentual(convertidos, total)
    return resultado


def calculate_lead_metrics(
    leads_created_df: pd.DataFrame,
    leads_modified_df: pd.DataFrame,
    previous_metrics: dict[str, Any] | None = None,
    seven_day_average: dict[str, float] | None = None,
    first_task_field: str = "FirstTask__c",
) -> dict[str, Any]:
    """Calcula as métricas diárias de Leads.

    Args:
        leads_created_df: Leads criados no dia.
        leads_modified_df: Leads modificados no dia (usado para conversão).
        previous_metrics: Métricas de Leads do dia anterior (para variação).
        seven_day_average: Média de 7 dias por métrica (para variação).
        first_task_field: Nome do campo customizado de primeira tarefa.

    Returns:
        Dicionário de métricas de Leads, incluindo comparações.
    """
    # --- Volume e conversão ---
    new_leads = 0 if is_dataframe_vazio(leads_created_df) else int(len(leads_created_df))

    converted_leads = 0
    if not is_dataframe_vazio(leads_modified_df) and "IsConverted" in leads_modified_df.columns:
        converted_leads = int(
            leads_modified_df["IsConverted"].fillna(False).astype(bool).sum()
        )

    conversion_rate = percentual(converted_leads, new_leads) if new_leads else 0.0

    # --- Leads sem primeira tarefa (entre os criados) ---
    leads_without_first_task = 0
    if not is_dataframe_vazio(leads_created_df) and first_task_field in leads_created_df.columns:
        sem_tarefa = ~leads_created_df[first_task_field].apply(_tem_primeira_tarefa)
        leads_without_first_task = int(sem_tarefa.sum())
    elif new_leads:
        # Campo não disponível: assume que todos estão sem tarefa registrada.
        leads_without_first_task = new_leads

    # --- Tempo até a primeira tarefa ---
    horas = _horas_ate_primeira_tarefa(leads_created_df, first_task_field)
    serie_horas = pd.Series(horas, dtype="float64")
    avg_time = arredondar(float(serie_horas.mean()), 2) if horas else None
    median_time = arredondar(float(serie_horas.median()), 2) if horas else None

    # --- Origens ---
    top_source = None
    if not is_dataframe_vazio(leads_created_df) and "LeadSource" in leads_created_df.columns:
        contagem = leads_created_df["LeadSource"].fillna("Sem origem").value_counts()
        if not contagem.empty:
            top_source = str(contagem.index[0])

    conversao_origem = _conversao_por_origem(leads_modified_df)
    best_source = None
    worst_source = None
    if conversao_origem:
        best_source = max(conversao_origem, key=conversao_origem.get)
        worst_source = min(conversao_origem, key=conversao_origem.get)

    # --- Montagem ---
    metricas: dict[str, Any] = {
        "new_leads": new_leads,
        "converted_leads": converted_leads,
        "conversion_rate": conversion_rate,
        "leads_without_first_task": leads_without_first_task,
        "avg_time_to_first_task_hours": avg_time,
        "median_time_to_first_task_hours": median_time,
        "top_lead_source_by_volume": top_source,
        "best_lead_source_by_conversion": best_source,
        "worst_lead_source_by_conversion": worst_source,
        "conversion_rate_by_source": conversao_origem,
    }

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
