"""Cálculo de métricas de Oportunidades.

Todos os indicadores são calculados em Python a partir de DataFrames pandas.
A função principal é :func:`calculate_opportunity_metrics`.

Regra do projeto: a IA nunca calcula números. Este módulo é a fonte da
verdade para os indicadores de Opportunity.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from .comparison_metrics import aplicar_comparacoes
from ..utils.date_utils import agora_tz
from ..utils.validators import (
    arredondar,
    coluna_existe,
    is_dataframe_vazio,
    percentual,
)

# Prefixo de Id de Opportunity no Salesforce (usado para vincular tarefas).
PREFIXO_ID_OPPORTUNITY = "006"

# Chaves numéricas comparáveis contra histórico (dia anterior / média 7 dias).
_CHAVES_COMPARAVEIS = [
    "new_opportunities",
    "open_opportunities",
    "won_opportunities",
    "lost_opportunities",
    "open_pipeline_amount",
    "won_amount",
    "lost_amount",
    "win_rate",
    "loss_rate",
    "stalled_opportunities",
    "opportunities_without_next_task",
    "opportunities_closing_this_month",
    "high_value_stalled_opportunities",
]


def _soma_amount(df: pd.DataFrame) -> float:
    """Soma a coluna ``Amount`` de forma segura (trata ausência/NaN)."""
    if not coluna_existe(df, "Amount"):
        return 0.0
    serie = pd.to_numeric(df["Amount"], errors="coerce").fillna(0.0)
    return float(serie.sum())


def _idade_em_dias(serie_datas: pd.Series, referencia: datetime) -> pd.Series:
    """Calcula a idade (em dias) entre cada data e a referência.

    As datas são interpretadas em UTC para uma comparação consistente.
    """
    convertido = pd.to_datetime(serie_datas, errors="coerce", utc=True)
    ref_utc = pd.Timestamp(referencia).tz_convert("UTC")
    return (ref_utc - convertido).dt.total_seconds() / 86400.0


def _texto(valor: Any) -> str:
    """Converte um valor de célula em texto limpo (trata NaN/None)."""
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valor).strip()


def _para_float(valor: Any) -> float | None:
    """Converte um valor em float, retornando None se não numérico."""
    num = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return None if pd.isna(num) else float(num)


def _para_int(valor: Any) -> int | None:
    """Converte um valor em int, retornando None se não numérico."""
    num = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return None if pd.isna(num) else int(num)


def _nome_owner(valor: Any) -> str | None:
    """Extrai o nome do dono a partir de ``Owner.Name`` (dict) ou texto."""
    if isinstance(valor, dict):
        nome = str(valor.get("Name") or "").strip()
        return nome or None
    if valor is None:
        return None
    txt = str(valor).strip()
    return txt or None


def _campo_valor(df: pd.DataFrame) -> str:
    """Define o campo de valor a usar: ValorProdutos (preferido) ou Amount."""
    return "ValorProdutos" if coluna_existe(df, "ValorProdutos") else "Amount"


def _detalhes_oportunidades(df: pd.DataFrame, limite: int = 10) -> list[dict[str, Any]]:
    """Extrai detalhes legíveis das oportunidades para alertas/tarefas.

    Ordena pelo valor (ValorProdutos quando disponível, senão Amount) desc.
    Cada item traz nome, valor, estágio, responsável (vendedor/GC), dias sem
    atividade e a próxima ação — dados concretos para uma tarefa acionável.
    """
    if is_dataframe_vazio(df):
        return []
    trabalho = df.copy()
    campo = _campo_valor(trabalho)
    tem_valor = coluna_existe(trabalho, campo)
    if tem_valor:
        trabalho["_amt"] = pd.to_numeric(trabalho[campo], errors="coerce").fillna(0.0)
        trabalho = trabalho.sort_values("_amt", ascending=False)
    detalhes: list[dict[str, Any]] = []
    for _, row in trabalho.head(limite).iterrows():
        dono = _nome_owner(row.get("Owner")) or _texto(row.get("GC_Nome__c")) or _texto(row.get("OwnerId"))
        detalhes.append(
            {
                "id": _texto(row.get("Id")),
                "name": _texto(row.get("Name")) or "(sem nome)",
                "amount": _para_float(row.get(campo)) if tem_valor else None,
                "stage": _texto(row.get("StageName")) or None,
                "owner": dono or None,
                "days_inactive": _para_int(row.get("OppDiasSemAtividade__c")),
                "next_action": _texto(row.get("Proxima_acao__c")) or None,
            }
        )
    return detalhes


def calculate_opportunity_metrics(
    opps_open_df: pd.DataFrame,
    opps_created_df: pd.DataFrame,
    opps_closed_df: pd.DataFrame,
    open_task_what_ids: set[str] | None = None,
    previous_metrics: dict[str, Any] | None = None,
    seven_day_average: dict[str, float] | None = None,
    high_value_amount: float = 50000.0,
    max_days_without_activity: int = 7,
    min_amount: float = 0.0,
    product_value_threshold: float = 20000.0,
    reference_date: date | None = None,
    timezone: str = "America/Sao_Paulo",
) -> dict[str, Any]:
    """Calcula as métricas diárias de Oportunidades.

    Args:
        opps_open_df: Oportunidades atualmente abertas (IsClosed = false).
        opps_created_df: Oportunidades criadas no dia.
        opps_closed_df: Oportunidades fechadas no dia (por CloseDate).
        open_task_what_ids: Conjunto de ``WhatId`` de tarefas abertas/futuras,
            usado para detectar oportunidades sem próxima tarefa.
        previous_metrics: Métricas do dia anterior (para variação).
        seven_day_average: Média de 7 dias por métrica (para variação).
        high_value_amount: Limite para considerar oportunidade de alto valor.
        max_days_without_activity: Dias sem atividade para marcar como parada.
        min_amount: Valor mínimo para a oportunidade entrar na análise de
            pipeline/risco (0 = sem filtro). Evita ruído de itens de baixo valor.
        reference_date: Data de referência (para "fechamento no mês").
        timezone: Fuso para cálculo de idade/atividade.

    Returns:
        Dicionário de métricas de Oportunidades, incluindo comparações.
    """
    agora = agora_tz(timezone)
    ref = reference_date or agora.date()

    # Filtro opcional: analisar apenas oportunidades abertas acima de um valor.
    if min_amount and min_amount > 0 and not is_dataframe_vazio(opps_open_df) and coluna_existe(opps_open_df, "Amount"):
        _amt = pd.to_numeric(opps_open_df["Amount"], errors="coerce").fillna(0.0)
        opps_open_df = opps_open_df[_amt >= float(min_amount)]

    # --- Volumes básicos ---
    new_opportunities = 0 if is_dataframe_vazio(opps_created_df) else int(len(opps_created_df))
    open_opportunities = 0 if is_dataframe_vazio(opps_open_df) else int(len(opps_open_df))

    # --- Fechadas no dia: ganhas x perdidas ---
    won_opportunities = 0
    lost_opportunities = 0
    won_amount = 0.0
    lost_amount = 0.0
    if not is_dataframe_vazio(opps_closed_df) and coluna_existe(opps_closed_df, "IsWon"):
        ganhas = opps_closed_df[opps_closed_df["IsWon"].fillna(False).astype(bool)]
        perdidas = opps_closed_df[~opps_closed_df["IsWon"].fillna(False).astype(bool)]
        won_opportunities = int(len(ganhas))
        lost_opportunities = int(len(perdidas))
        won_amount = _soma_amount(ganhas)
        lost_amount = _soma_amount(perdidas)

    total_fechadas = won_opportunities + lost_opportunities
    win_rate = percentual(won_opportunities, total_fechadas) if total_fechadas else 0.0
    loss_rate = percentual(lost_opportunities, total_fechadas) if total_fechadas else 0.0

    # --- Pipeline aberto ---
    open_pipeline_amount = arredondar(_soma_amount(opps_open_df), 2) or 0.0

    # Pipeline por VALOR DE PRODUTOS (recorrente+pontual) e por VENDEDOR (dono).
    open_pipeline_product_value = 0.0
    pipeline_by_owner: dict[str, float] = {}
    if not is_dataframe_vazio(opps_open_df):
        campo_pl = _campo_valor(opps_open_df)
        if coluna_existe(opps_open_df, campo_pl):
            tmp = opps_open_df.copy()
            tmp["_v"] = pd.to_numeric(tmp[campo_pl], errors="coerce").fillna(0.0)
            open_pipeline_product_value = arredondar(float(tmp["_v"].sum()), 2) or 0.0
            if coluna_existe(tmp, "Owner") or coluna_existe(tmp, "OwnerId"):
                tmp["_owner"] = tmp.apply(
                    lambda r: _nome_owner(r.get("Owner")) or _texto(r.get("OwnerId")) or "—",
                    axis=1,
                )
                agrup = tmp.groupby("_owner")["_v"].sum().sort_values(ascending=False)
                pipeline_by_owner = {
                    str(k): (arredondar(float(v), 2) or 0.0) for k, v in agrup.head(20).items()
                }

    # --- Oportunidades paradas (sem atividade recente) ---
    stalled_opportunities = 0
    high_value_stalled_opportunities = 0
    stalled_ids: list[str] = []
    high_value_stalled_ids: list[str] = []
    stalled_details: list[dict[str, Any]] = []
    high_value_stalled_details: list[dict[str, Any]] = []
    if not is_dataframe_vazio(opps_open_df) and coluna_existe(opps_open_df, "LastModifiedDate"):
        idade = _idade_em_dias(opps_open_df["LastModifiedDate"], agora)
        paradas = opps_open_df[(idade >= float(max_days_without_activity)).fillna(False)]
        stalled_opportunities = int(len(paradas))
        if coluna_existe(paradas, "Id"):
            stalled_ids = [str(i) for i in paradas["Id"].tolist()]
        stalled_details = _detalhes_oportunidades(paradas)
        # ALTO VALOR: usa o VALOR TOTAL DOS PRODUTOS (recorrente+pontual) quando
        # disponível, com limiar próprio (ex.: 20k); senão cai para Amount.
        campo_v = _campo_valor(paradas)
        limiar = (
            float(product_value_threshold)
            if campo_v == "ValorProdutos"
            else float(high_value_amount)
        )
        if coluna_existe(paradas, campo_v):
            valores = pd.to_numeric(paradas[campo_v], errors="coerce").fillna(0.0)
            alto = paradas[(valores >= limiar).values]
            high_value_stalled_opportunities = int(len(alto))
            if coluna_existe(alto, "Id"):
                high_value_stalled_ids = [str(i) for i in alto["Id"].tolist()]
            high_value_stalled_details = _detalhes_oportunidades(alto)

    # --- Oportunidades sem próxima tarefa ---
    opportunities_without_next_task = 0
    opps_without_task_ids: list[str] = []
    opps_without_task_details: list[dict[str, Any]] = []
    if not is_dataframe_vazio(opps_open_df) and coluna_existe(opps_open_df, "Id"):
        com_tarefa = open_task_what_ids or set()
        sem_tarefa = opps_open_df[~opps_open_df["Id"].astype(str).isin(com_tarefa)]
        opportunities_without_next_task = int(len(sem_tarefa))
        opps_without_task_ids = [str(i) for i in sem_tarefa["Id"].tolist()]
        opps_without_task_details = _detalhes_oportunidades(sem_tarefa)

    # --- Oportunidades com fechamento no mês corrente ---
    opportunities_closing_this_month = 0
    if not is_dataframe_vazio(opps_open_df) and coluna_existe(opps_open_df, "CloseDate"):
        close = pd.to_datetime(opps_open_df["CloseDate"], errors="coerce")
        mesmo_mes = (close.dt.year == ref.year) & (close.dt.month == ref.month)
        opportunities_closing_this_month = int(mesmo_mes.fillna(False).sum())

    # --- Montagem ---
    metricas: dict[str, Any] = {
        "new_opportunities": new_opportunities,
        "open_opportunities": open_opportunities,
        "won_opportunities": won_opportunities,
        "lost_opportunities": lost_opportunities,
        "open_pipeline_amount": open_pipeline_amount,
        "open_pipeline_product_value": open_pipeline_product_value,
        "pipeline_by_owner": pipeline_by_owner,
        "won_amount": arredondar(won_amount, 2) or 0.0,
        "lost_amount": arredondar(lost_amount, 2) or 0.0,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "stalled_opportunities": stalled_opportunities,
        "opportunities_without_next_task": opportunities_without_next_task,
        "opportunities_closing_this_month": opportunities_closing_this_month,
        "high_value_stalled_opportunities": high_value_stalled_opportunities,
        # Listas auxiliares para o motor de risco apontar registros de origem.
        "stalled_opportunity_ids": stalled_ids[:50],
        "high_value_stalled_opportunity_ids": high_value_stalled_ids[:50],
        "opportunities_without_task_ids": opps_without_task_ids[:50],
        # Detalhes por registro (nome, valor, dono, dias, próxima ação) para
        # alimentar tarefas/alertas acionáveis. Não são persistidos (não-escalares).
        "stalled_opportunity_details": stalled_details,
        "high_value_stalled_details": high_value_stalled_details,
        "opportunities_without_task_details": opps_without_task_details,
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
