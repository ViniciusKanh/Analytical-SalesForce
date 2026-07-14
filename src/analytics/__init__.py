"""Motores de cálculo de métricas e risco do Analytical-Force.

Princípio do projeto: TODOS os indicadores são calculados aqui, em Python.
A IA nunca calcula números — apenas interpreta o JSON resultante.
"""

from .lead_metrics import calculate_lead_metrics
from .opportunity_metrics import calculate_opportunity_metrics
from .task_metrics import calculate_task_metrics
from .satisfaction_metrics import calculate_satisfaction_metrics
from .cancellation_metrics import calculate_cancellation_metrics
from .contract_metrics import calculate_contract_metrics
from .comparison_metrics import compare_metric, aplicar_comparacoes
from .risk_engine import generate_alerts

__all__ = [
    "calculate_lead_metrics",
    "calculate_opportunity_metrics",
    "calculate_task_metrics",
    "calculate_satisfaction_metrics",
    "calculate_cancellation_metrics",
    "calculate_contract_metrics",
    "compare_metric",
    "aplicar_comparacoes",
    "generate_alerts",
]
