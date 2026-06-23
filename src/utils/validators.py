"""Validadores e helpers numéricos do Analytical-Force.

Funções pequenas e puras usadas pelos motores de métricas para evitar
divisões por zero, normalizar valores ausentes e arredondar com segurança.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def safe_float(valor: Any, padrao: float = 0.0) -> float:
    """Converte um valor para float de forma segura.

    Trata None, NaN e strings inválidas retornando o padrão.
    """
    if valor is None:
        return padrao
    try:
        resultado = float(valor)
    except (TypeError, ValueError):
        return padrao
    # Protege contra NaN.
    if resultado != resultado:  # NaN != NaN
        return padrao
    return resultado


def safe_int(valor: Any, padrao: int = 0) -> int:
    """Converte um valor para int de forma segura."""
    try:
        return int(safe_float(valor, float(padrao)))
    except (TypeError, ValueError):
        return padrao


def divisao_segura(numerador: float, denominador: float, padrao: float = 0.0) -> float:
    """Divide dois números evitando divisão por zero.

    Args:
        numerador: Valor do numerador.
        denominador: Valor do denominador.
        padrao: Valor retornado quando o denominador é zero.

    Returns:
        Resultado da divisão ou o padrão.
    """
    if not denominador:
        return padrao
    return numerador / denominador


def percentual(parte: float, total: float, casas: int = 2) -> float:
    """Calcula o percentual de ``parte`` sobre ``total`` (0-100)."""
    return round(divisao_segura(parte, total) * 100.0, casas)


def arredondar(valor: float | None, casas: int = 2) -> float | None:
    """Arredonda um número, preservando None."""
    if valor is None:
        return None
    return round(float(valor), casas)


def is_dataframe_vazio(df: pd.DataFrame | None) -> bool:
    """Indica se um DataFrame é None ou está vazio."""
    return df is None or df.empty


def coluna_existe(df: pd.DataFrame | None, coluna: str) -> bool:
    """Verifica se uma coluna existe em um DataFrame não vazio."""
    return not is_dataframe_vazio(df) and coluna in df.columns


def normalizar_severidade(severidade: str) -> str:
    """Garante que a severidade esteja em {low, medium, high}.

    Valores desconhecidos são tratados como ``low``.
    """
    valor = (severidade or "").strip().lower()
    return valor if valor in {"low", "medium", "high"} else "low"
