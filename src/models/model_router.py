"""Roteador de modelos do Analytical-Force.

Lê o provider configurado (``MODEL_PROVIDER``) e decide qual cliente usar
para interpretar o relatório:

- ``template``      -> não usa IA (retorna None; o template assume).
- ``ollama``        -> modelo local via HTTP.
- ``transformers``  -> modelo público via Hugging Face.

Regra de robustez: se o provider de IA falhar por qualquer motivo, o roteador
NÃO quebra a execução — ele cai automaticamente para o modo template,
retornando ``None`` como narrativa e ``"template"`` como provider efetivo.
"""

from __future__ import annotations

from ..config.settings import ModelSettings
from ..utils.logger import get_logger
from .hf_inference_client import HFInferenceClient, HFInferenceError
from .ollama_client import OllamaClient, OllamaError
from .transformers_client import TransformersClient, TransformersError

logger = get_logger("models.router")


class ModelRouter:
    """Seleciona e executa o provider de modelo configurado."""

    def __init__(self, model_settings: ModelSettings) -> None:
        """Inicializa o roteador com as configurações de modelo."""
        self._cfg = model_settings

    def interpretar(
        self, prompt: str, system: str | None = None
    ) -> tuple[str | None, str]:
        """Obtém a interpretação textual do relatório.

        Args:
            prompt: Prompt já montado (com o JSON de métricas calculado).
            system: Instrução de sistema opcional (papel do modelo).

        Returns:
            Tupla ``(narrativa, provider_efetivo)``. ``narrativa`` é ``None``
            quando o modo é template ou quando houve fallback por falha.
        """
        provider = self._cfg.provider

        # Modo sem IA (ou IA desabilitada): template assume integralmente.
        if not self._cfg.usa_ia:
            logger.info("Provider efetivo: template (sem IA).")
            return None, "template"

        try:
            if provider == "ollama":
                cliente = OllamaClient(
                    base_url=self._cfg.ollama_base_url,
                    model=self._cfg.ollama_model,
                )
                return cliente.gerar(prompt, system=system), "ollama"

            if provider == "transformers":
                cliente = TransformersClient(
                    repo_id=self._cfg.hf_model_repo_id,
                    device=self._cfg.hf_device,
                    max_new_tokens=self._cfg.hf_max_new_tokens,
                )
                return cliente.gerar(prompt, system=system), "transformers"

            if provider == "hf_inference":
                cliente_hf = HFInferenceClient(
                    model=self._cfg.hf_inference_model,
                    token=self._cfg.hf_token,
                    max_tokens=self._cfg.hf_max_new_tokens,
                    provider=self._cfg.hf_inference_provider or None,
                )
                return cliente_hf.gerar(prompt, system=system), "hf_inference"

            # Provider desconhecido: trata como template por segurança.
            logger.warning("Provider '%s' não reconhecido. Usando template.", provider)
            return None, "template"

        except (OllamaError, TransformersError, HFInferenceError) as exc:
            # Falha controlada -> fallback para template.
            logger.warning(
                "Falha no provider '%s' (%s). Caindo para template.",
                provider,
                exc,
            )
            return None, "template"
        except Exception as exc:  # rede inesperada, etc. — nunca quebra o agente
            logger.warning(
                "Erro inesperado no provider '%s' (%s). Caindo para template.",
                provider,
                type(exc).__name__,
            )
            return None, "template"
