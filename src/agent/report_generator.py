"""Geração do relatório diário em Markdown.

Orquestra a camada de modelos: monta o prompt, pede a interpretação ao
provider configurado (com fallback para template) e renderiza o Markdown
final a partir do JSON de métricas.

Garantia: os números do relatório vêm SEMPRE do template (Python). A IA
apenas substitui a narrativa do Resumo Executivo, quando disponível.
"""

from __future__ import annotations

from typing import Any

from ..config.settings import ModelSettings
from ..models.model_router import ModelRouter
from ..models.template_client import renderizar_relatorio
from ..utils.logger import get_logger
from .prompt_builder import construir_prompt, obter_system_prompt

logger = get_logger("agent.report_generator")


def gerar_relatorio(
    payload: dict[str, Any], model_settings: ModelSettings
) -> tuple[str, str]:
    """Gera o relatório Markdown do dia.

    Args:
        payload: JSON estruturado com métricas, alertas e qualidade de dados.
        model_settings: Configurações do provider de modelo.

    Returns:
        Tupla ``(markdown, provider_efetivo)``. ``provider_efetivo`` indica se
        a interpretação veio de ``ollama``, ``transformers`` ou ``template``.
    """
    narrativa: str | None = None
    provider = "template"

    if model_settings.usa_ia:
        prompt = construir_prompt(payload)
        router = ModelRouter(model_settings)
        narrativa, provider = router.interpretar(prompt, system=obter_system_prompt())

    markdown = renderizar_relatorio(payload, narrativa_ia=narrativa)
    logger.info("Relatório gerado (provider efetivo=%s).", provider)
    return markdown, provider
