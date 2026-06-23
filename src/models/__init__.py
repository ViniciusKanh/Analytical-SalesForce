"""Camada de modelos do Analytical-Force.

Apenas modelos locais/públicos gratuitos. Sem APIs comerciais pagas.

- ``template_client``: relatório por regras, sem IA (obrigatório/sempre funciona).
- ``ollama_client``: modelo local via HTTP.
- ``transformers_client``: modelo público via Hugging Face (opcional).
- ``model_router``: seleção do provider com fallback automático para template.
"""

from .model_router import ModelRouter
from .ollama_client import OllamaClient, OllamaError
from .template_client import renderizar_relatorio
from .transformers_client import TransformersClient, TransformersError

__all__ = [
    "ModelRouter",
    "OllamaClient",
    "OllamaError",
    "TransformersClient",
    "TransformersError",
    "renderizar_relatorio",
]
