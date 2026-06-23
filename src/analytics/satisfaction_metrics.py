"""Cálculo de métricas de Satisfação (módulo configurável).

A fonte de satisfação pode estar em objetos diferentes do Salesforce e por
isso é configurada via ``object_mapping`` no banco. Enquanto não houver
mapeamento, o módulo retorna um aviso técnico — sem inventar dados.

Estrutura esperada de ``mapping`` (vinda de ObjectMappingRepository):
    {
        "salesforce_object": "<Objeto__c>",
        "field_mapping": {
            "score": "<Campo__c>",       # nota numérica
            "reason": "<Campo__c>",      # motivo (opcional)
            "comment": "<Campo__c>",     # comentário (opcional)
            "negative_threshold": 6      # nota < limite é considerada negativa
        }
    }
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .comparison_metrics import aplicar_comparacoes
from ..utils.validators import arredondar, coluna_existe, is_dataframe_vazio

MENSAGEM_NAO_CONFIGURADO = (
    "Fonte de satisfação ainda não configurada. "
    "Configure o objeto e os campos em object_mapping."
)

_CHAVES_COMPARAVEIS = ["avg_score", "responses", "negative_count"]


def calculate_satisfaction_metrics(
    mapping: dict[str, Any] | None = None,
    df: pd.DataFrame | None = None,
    previous_metrics: dict[str, Any] | None = None,
    seven_day_average: dict[str, float] | None = None,
    min_score: float = 7.0,
) -> dict[str, Any]:
    """Calcula métricas de satisfação quando há mapeamento configurado.

    Args:
        mapping: Mapeamento do objeto/campos de satisfação (ou None).
        df: DataFrame com as respostas de satisfação do período (ou None).
        previous_metrics: Métricas do dia anterior (para variação).
        seven_day_average: Média de 7 dias por métrica (para variação).
        min_score: Nota mínima aceitável (usada como limite padrão de negativo).

    Returns:
        Dicionário de métricas. Quando não configurado, traz ``configured=False``
        e uma mensagem técnica.
    """
    if not mapping:
        return {"configured": False, "message": MENSAGEM_NAO_CONFIGURADO}

    campos = mapping.get("field_mapping", {}) if isinstance(mapping, dict) else {}
    campo_score = campos.get("score")
    campo_motivo = campos.get("reason")
    campo_comentario = campos.get("comment")
    limite_negativo = float(campos.get("negative_threshold", min_score))

    base: dict[str, Any] = {
        "configured": True,
        "salesforce_object": mapping.get("salesforce_object"),
    }

    if is_dataframe_vazio(df) or not campo_score or not coluna_existe(df, campo_score):
        base.update(
            {
                "message": "Mapeamento configurado, mas sem dados de satisfação no período.",
                "responses": 0,
                "avg_score": None,
                "negative_count": 0,
                "top_negative_reasons": {},
                "critical_comments": [],
            }
        )
        return base

    scores = pd.to_numeric(df[campo_score], errors="coerce").dropna()
    responses = int(len(scores))
    avg_score = arredondar(float(scores.mean()), 2) if responses else None

    negativos_mask = pd.to_numeric(df[campo_score], errors="coerce") < limite_negativo
    df_negativos = df[negativos_mask.fillna(False)]
    negative_count = int(len(df_negativos))

    top_negative_reasons: dict[str, int] = {}
    if campo_motivo and coluna_existe(df_negativos, campo_motivo):
        contagem = df_negativos[campo_motivo].fillna("Sem motivo").value_counts().head(5)
        top_negative_reasons = {str(k): int(v) for k, v in contagem.items()}

    critical_comments: list[str] = []
    if campo_comentario and coluna_existe(df_negativos, campo_comentario):
        comentarios = df_negativos[campo_comentario].dropna().astype(str).tolist()
        critical_comments = [c for c in comentarios if c.strip()][:10]

    metricas: dict[str, Any] = {
        **base,
        "message": None,
        "responses": responses,
        "avg_score": avg_score,
        "negative_count": negative_count,
        "top_negative_reasons": top_negative_reasons,
        "critical_comments": critical_comments,
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
