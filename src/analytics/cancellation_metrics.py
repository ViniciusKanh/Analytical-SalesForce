"""Cálculo de métricas de Cancelamentos (módulo configurável).

A fonte de cancelamento pode estar em objetos diferentes do Salesforce e por
isso é configurada via ``object_mapping`` no banco. Enquanto não houver
mapeamento, o módulo retorna um aviso técnico — sem inventar dados.

Estrutura esperada de ``mapping`` (vinda de ObjectMappingRepository):
    {
        "salesforce_object": "<Objeto__c>",
        "field_mapping": {
            "mrr": "<Campo__c>",       # impacto mensal (opcional)
            "reason": "<Campo__c>",    # motivo (opcional)
            "product": "<Campo__c>",   # produto (opcional)
            "owner": "<Campo__c>"      # responsável (opcional)
        }
    }
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .comparison_metrics import aplicar_comparacoes
from ..utils.validators import arredondar, coluna_existe, is_dataframe_vazio

MENSAGEM_NAO_CONFIGURADO = (
    "Fonte de cancelamento ainda não configurada. "
    "Configure o objeto e os campos em object_mapping."
)

_CHAVES_COMPARAVEIS = ["cancellations_count", "mrr_impact", "arr_impact"]


def _contagem_por_campo(df: pd.DataFrame, campo: str | None) -> dict[str, int]:
    """Conta registros agrupados por um campo (produto/responsável)."""
    if not campo or not coluna_existe(df, campo):
        return {}
    contagem = df[campo].fillna("Não informado").value_counts().head(10)
    return {str(k): int(v) for k, v in contagem.items()}


def calculate_cancellation_metrics(
    mapping: dict[str, Any] | None = None,
    df: pd.DataFrame | None = None,
    previous_metrics: dict[str, Any] | None = None,
    seven_day_average: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calcula métricas de cancelamento quando há mapeamento configurado.

    Args:
        mapping: Mapeamento do objeto/campos de cancelamento (ou None).
        df: DataFrame com os cancelamentos do período (ou None).
        previous_metrics: Métricas do dia anterior (para variação).
        seven_day_average: Média de 7 dias por métrica (para variação).

    Returns:
        Dicionário de métricas. Quando não configurado, traz ``configured=False``
        e uma mensagem técnica.
    """
    if not mapping:
        return {"configured": False, "message": MENSAGEM_NAO_CONFIGURADO}

    campos = mapping.get("field_mapping", {}) if isinstance(mapping, dict) else {}
    campo_mrr = campos.get("mrr")
    campo_motivo = campos.get("reason")
    campo_produto = campos.get("product")
    campo_owner = campos.get("owner")

    base: dict[str, Any] = {
        "configured": True,
        "salesforce_object": mapping.get("salesforce_object"),
    }

    if is_dataframe_vazio(df):
        base.update(
            {
                "message": "Mapeamento configurado, mas sem cancelamentos no período.",
                "cancellations_count": 0,
                "mrr_impact": 0.0,
                "arr_impact": 0.0,
                "top_reason": None,
                "cancellations_by_product": {},
                "cancellations_by_owner": {},
            }
        )
        return base

    cancellations_count = int(len(df))

    mrr_impact = 0.0
    if campo_mrr and coluna_existe(df, campo_mrr):
        mrr_impact = float(pd.to_numeric(df[campo_mrr], errors="coerce").fillna(0.0).sum())
    arr_impact = mrr_impact * 12.0

    top_reason = None
    if campo_motivo and coluna_existe(df, campo_motivo):
        contagem = df[campo_motivo].fillna("Sem motivo").value_counts()
        if not contagem.empty:
            top_reason = str(contagem.index[0])

    metricas: dict[str, Any] = {
        **base,
        "message": None,
        "cancellations_count": cancellations_count,
        "mrr_impact": arredondar(mrr_impact, 2) or 0.0,
        "arr_impact": arredondar(arr_impact, 2) or 0.0,
        "top_reason": top_reason,
        "cancellations_by_product": _contagem_por_campo(df, campo_produto),
        "cancellations_by_owner": _contagem_por_campo(df, campo_owner),
    }

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
