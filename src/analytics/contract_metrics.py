"""Cálculo de métricas de Contratos (``Contrato_oPT__c``).

Calcula, a partir dos DataFrames já extraídos do Salesforce:

- quantos contratos foram modificados no dia e quem modificou cada um
  (usa apenas campos padrão: ``LastModifiedDate``/``LastModifiedBy``);
- o total de reajuste aplicado no MÊS corrente, quando o módulo configurável
  de reajuste estiver ativo (``value_field``/``previous_value_field``);
- um alerta de qualidade de dados quando o reajuste informado no contrato
  diverge do delta calculado (valor atual - valor anterior), que costuma
  indicar erro de preenchimento (ex.: valor anterior errado).

Segue o princípio do projeto: Python calcula, a IA apenas interpreta o JSON
resultante. Este módulo NUNCA deve ser chamado pela camada de IA.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Aviso fixo, exibido sempre que o módulo de reajuste está ativo — o cálculo
# é uma ESTIMATIVA (delta de valores), não um dado oficial do contrato.
AVISO_REAJUSTE = (
    "Os valores de reajuste são estimados pela diferença entre o valor atual "
    "e o valor anterior do contrato. Podem não refletir com 100% de precisão "
    "o reajuste real caso haja erro de preenchimento no contrato (ex.: valor "
    "anterior lançado incorretamente)."
)

# Tolerância (em R$) para considerar o reajuste informado e o delta calculado
# como equivalentes — acima disso, o contrato é sinalizado como inconsistente.
_TOLERANCIA_CENTAVOS = 0.01


def _valor_relacionamento(linha: Any, campo: str) -> Any:
    """Resolve um campo simples ou de relacionamento (ex.: ``Conta__r.Name``).

    O Salesforce retorna relacionamentos como dicionários aninhados (ex.:
    ``{"LastModifiedBy": {"Name": "Fulano", "attributes": {...}}}``), não como
    chave plana ``"LastModifiedBy.Name"``. Esta função navega essa estrutura.
    """
    atual: Any = linha
    for parte in campo.split("."):
        if atual is None:
            return None
        if isinstance(atual, dict):
            atual = atual.get(parte)
        elif hasattr(atual, "get"):
            atual = atual.get(parte)
        else:
            return None
    return atual


def _serializar_data(valor: Any) -> str | None:
    """Converte um valor de data/datetime em texto ISO, tolerando nulos."""
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return valor.isoformat()
    except AttributeError:
        texto = str(valor).strip()
        return texto or None


def _listar_contratos_modificados(
    df: pd.DataFrame, account_name_field: str
) -> list[dict[str, Any]]:
    """Monta a listagem 'quem modificou o quê' dos contratos do dia."""
    if df is None or df.empty:
        return []
    itens: list[dict[str, Any]] = []
    for _, linha in df.iterrows():
        item: dict[str, Any] = {
            "id": linha.get("Id"),
            "name": linha.get("Name") or linha.get("Id"),
            "modified_by": _valor_relacionamento(linha, "LastModifiedBy.Name"),
            "modified_at": _serializar_data(linha.get("LastModifiedDate")),
        }
        if account_name_field:
            item["account_name"] = _valor_relacionamento(linha, account_name_field)
        itens.append(item)
    return itens


def calculate_contract_metrics(
    df_modificados: pd.DataFrame | None,
    df_reajustados: pd.DataFrame | None,
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calcula as métricas diárias de contratos (modificações + reajuste).

    Args:
        df_modificados: Contratos com ``LastModifiedDate`` no dia de referência.
        df_reajustados: Contratos com reajuste aplicado no mês corrente (vazio
            se o módulo de reajuste não estiver configurado).
        source: Configuração ``contract_source`` (ver ``config.settings``).

    Returns:
        Dicionário JSON-serializável com as métricas já calculadas, pronto
        para persistência no Turso e uso pelo relatório/e-mail/painel.
    """
    source = source or {}
    account_name_field = source.get("account_name_field") or ""
    value_field = source.get("value_field") or ""
    previous_field = source.get("previous_value_field") or ""
    readjustment_field = source.get("readjustment_field") or ""
    readjustment_configured = bool(
        value_field and previous_field and source.get("readjustment_date_field")
    )

    modificados = _listar_contratos_modificados(df_modificados, account_name_field)

    resultado: dict[str, Any] = {
        "configured": bool(source.get("object")),
        "modified_today_count": len(modificados),
        "modified_today": modificados,
        "readjustment_configured": readjustment_configured,
        "readjustment_month_count": 0,
        "readjustment_month_total": 0.0,
        "readjustment_month_avg_percent": None,
        "readjustment_inconsistent_count": 0,
        "readjustment_contracts": [],
        "readjustment_disclaimer": AVISO_REAJUSTE,
    }

    if not readjustment_configured or df_reajustados is None or df_reajustados.empty:
        return resultado

    df = df_reajustados.copy()
    df["_valor_atual"] = pd.to_numeric(df.get(value_field), errors="coerce")
    df["_valor_anterior"] = pd.to_numeric(df.get(previous_field), errors="coerce")
    validos = df.dropna(subset=["_valor_atual", "_valor_anterior"])
    if validos.empty:
        return resultado

    validos = validos.copy()
    validos["_delta"] = validos["_valor_atual"] - validos["_valor_anterior"]
    if readjustment_field and readjustment_field in validos.columns:
        validos["_informado"] = pd.to_numeric(validos[readjustment_field], errors="coerce")
    else:
        validos["_informado"] = validos["_delta"]

    contratos: list[dict[str, Any]] = []
    percentuais: list[float] = []
    inconsistentes = 0
    for _, linha in validos.iterrows():
        anterior = float(linha["_valor_anterior"])
        atual = float(linha["_valor_atual"])
        delta = float(linha["_delta"])
        informado = linha.get("_informado")
        informado_val = None if informado is None or pd.isna(informado) else float(informado)
        inconsistente = (
            informado_val is not None
            and abs(informado_val - delta) > _TOLERANCIA_CENTAVOS
        )
        if inconsistente:
            inconsistentes += 1
        pct = (delta / anterior * 100.0) if anterior else None
        if pct is not None:
            percentuais.append(pct)
        item: dict[str, Any] = {
            "id": linha.get("Id"),
            "name": linha.get("Name") or linha.get("Id"),
            "previous_value": anterior,
            "current_value": atual,
            "delta": delta,
            "reported_readjustment": informado_val,
            "percent": pct,
            "inconsistent": inconsistente,
        }
        if account_name_field:
            item["account_name"] = _valor_relacionamento(linha, account_name_field)
        contratos.append(item)

    resultado["readjustment_month_count"] = len(contratos)
    resultado["readjustment_month_total"] = float(validos["_delta"].sum())
    resultado["readjustment_month_avg_percent"] = (
        sum(percentuais) / len(percentuais) if percentuais else None
    )
    resultado["readjustment_inconsistent_count"] = inconsistentes
    # Ordena por delta (maior reajuste primeiro) — mais relevante para leitura.
    resultado["readjustment_contracts"] = sorted(
        contratos, key=lambda c: abs(c["delta"]), reverse=True
    )
    return resultado
