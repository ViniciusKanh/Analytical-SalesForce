"""Comparações históricas entre métricas.

Compara o valor atual de uma métrica com o dia anterior e com a média dos
últimos 7 dias, calculando variação absoluta, percentual e tendência.
"""

from __future__ import annotations

from typing import Any

from ..utils.validators import arredondar, divisao_segura

# Faixa de variação (em %) considerada "estável" para definição da tendência.
_LIMIAR_ESTAVEL_PERCENT = 1.0


def _tendencia(variacao_percent: float | None) -> str:
    """Classifica a tendência a partir da variação percentual.

    Returns:
        ``"up"``, ``"down"`` ou ``"stable"``.
    """
    if variacao_percent is None:
        return "stable"
    if variacao_percent > _LIMIAR_ESTAVEL_PERCENT:
        return "up"
    if variacao_percent < -_LIMIAR_ESTAVEL_PERCENT:
        return "down"
    return "stable"


def compare_metric(
    current_value: float | None,
    previous_value: float | None,
    seven_day_avg: float | None,
) -> dict[str, Any]:
    """Compara um valor atual com o dia anterior e com a média de 7 dias.

    Args:
        current_value: Valor atual da métrica.
        previous_value: Valor do dia anterior (ou None).
        seven_day_avg: Média dos últimos 7 dias (ou None).

    Returns:
        Dicionário com variações absolutas/percentuais e a tendência.
    """
    atual = current_value if current_value is not None else 0.0

    # --- Comparação com o dia anterior ---
    var_prev: float | None = None
    var_prev_pct: float | None = None
    if previous_value is not None:
        var_prev = arredondar(atual - previous_value, 2)
        var_prev_pct = arredondar(
            divisao_segura(atual - previous_value, abs(previous_value)) * 100.0, 2
        )

    # --- Comparação com a média de 7 dias ---
    var_avg: float | None = None
    var_avg_pct: float | None = None
    if seven_day_avg is not None:
        var_avg = arredondar(atual - seven_day_avg, 2)
        var_avg_pct = arredondar(
            divisao_segura(atual - seven_day_avg, abs(seven_day_avg)) * 100.0, 2
        )

    return {
        "current": arredondar(atual, 2),
        "previous": arredondar(previous_value, 2) if previous_value is not None else None,
        "seven_day_avg": arredondar(seven_day_avg, 2)
        if seven_day_avg is not None
        else None,
        "variation_vs_previous": var_prev,
        "variation_percent_vs_previous": var_prev_pct,
        "variation_vs_7day_avg": var_avg,
        "variation_percent_vs_7day_avg": var_avg_pct,
        "trend": _tendencia(var_prev_pct if var_prev_pct is not None else var_avg_pct),
    }


def aplicar_comparacoes(
    metricas_atuais: dict[str, Any],
    metricas_anteriores: dict[str, Any] | None,
    media_7_dias: dict[str, float] | None,
    chaves_numericas: list[str],
) -> dict[str, dict[str, Any]]:
    """Gera o bloco de comparações para um conjunto de métricas numéricas.

    Args:
        metricas_atuais: Métricas do dia atual (dict plano).
        metricas_anteriores: Métricas do dia anterior (ou None).
        media_7_dias: Médias de 7 dias por métrica (ou None).
        chaves_numericas: Quais chaves devem ser comparadas.

    Returns:
        Dicionário ``{chave: resultado_de_compare_metric}``.
    """
    anteriores = metricas_anteriores or {}
    medias = media_7_dias or {}
    resultado: dict[str, dict[str, Any]] = {}

    for chave in chaves_numericas:
        atual = metricas_atuais.get(chave)
        if not isinstance(atual, (int, float)):
            continue
        anterior = anteriores.get(chave)
        media = medias.get(chave)
        resultado[chave] = compare_metric(
            float(atual),
            float(anterior) if isinstance(anterior, (int, float)) else None,
            float(media) if isinstance(media, (int, float)) else None,
        )
    return resultado
