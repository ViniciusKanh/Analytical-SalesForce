"""Cliente Hugging Face Transformers (modelo público, opcional).

Carrega um modelo público de geração de texto via ``transformers`` e produz
a interpretação do relatório localmente, sem chamar nenhuma API comercial.

Cuidados:
- O modelo NÃO é fixado no código: vem de ``HF_MODEL_REPO_ID``.
- ``transformers``/``torch`` são dependências opcionais (import tardio).
- Erros de memória, modelo ausente ou dependência faltando levantam
  :class:`TransformersError` para acionar o fallback para template.

Princípio: este cliente NUNCA calcula indicadores. Apenas interpreta o prompt.
"""

from __future__ import annotations

from typing import Any

from ..utils.logger import get_logger

logger = get_logger("models.transformers")

# Cache de pipelines por (repo_id, device). Evita recarregar o modelo a cada
# chamada — o que era o principal custo quando há várias gerações por execução.
# Compartilhado por todas as instâncias no mesmo processo.
_PIPELINE_CACHE: dict[tuple[str, str], Any] = {}


class TransformersError(RuntimeError):
    """Erro controlado ao usar Hugging Face Transformers."""


class TransformersClient:
    """Encapsula um pipeline de ``text-generation`` da Hugging Face."""

    def __init__(
        self,
        repo_id: str,
        device: str = "cpu",
        max_new_tokens: int = 512,
    ) -> None:
        """Inicializa o cliente (sem carregar o modelo ainda).

        Args:
            repo_id: Identificador do modelo público (``HF_MODEL_REPO_ID``).
            device: ``cpu`` ou ``cuda`` (``HF_DEVICE``).
            max_new_tokens: Limite de tokens gerados na resposta.

        Raises:
            TransformersError: Se ``repo_id`` não for informado.
        """
        if not repo_id:
            raise TransformersError(
                "HF_MODEL_REPO_ID não configurado. Defina um modelo público válido."
            )
        self._repo_id = repo_id
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._pipeline = None  # carregamento preguiçoso (lazy)

    def _carregar_pipeline(self):
        """Carrega (uma única vez) o pipeline de geração de texto.

        Reaproveita um pipeline em cache para o mesmo (modelo, device), evitando
        recarregar o modelo a cada chamada.
        """
        if self._pipeline is not None:
            return self._pipeline

        chave = (self._repo_id, self._device)
        em_cache = _PIPELINE_CACHE.get(chave)
        if em_cache is not None:
            self._pipeline = em_cache
            return self._pipeline

        try:
            from transformers import pipeline  # import tardio
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise TransformersError(
                "Dependência ausente. Instale: pip install transformers torch"
            ) from exc

        try:
            # device=-1 força CPU; device=0 usa a primeira GPU.
            device_idx = 0 if self._device.lower().startswith("cuda") else -1
            self._pipeline = pipeline(
                "text-generation",
                model=self._repo_id,
                device=device_idx,
            )
        except Exception as exc:  # modelo ausente, sem memória, etc.
            raise TransformersError(
                f"Falha ao carregar o modelo '{self._repo_id}': {type(exc).__name__}."
            ) from exc
        _PIPELINE_CACHE[chave] = self._pipeline
        logger.info("Modelo Transformers carregado (repo=%s).", self._repo_id)
        return self._pipeline

    def gerar(self, prompt: str, system: str | None = None) -> str:
        """Gera a interpretação textual a partir do prompt.

        Args:
            prompt: Prompt completo (com o JSON de métricas).
            system: Instrução de sistema opcional (prefixada ao prompt).

        Returns:
            Texto interpretativo gerado pelo modelo.

        Raises:
            TransformersError: Em qualquer falha de carga/geração.
        """
        pipe = self._carregar_pipeline()
        entrada = f"{system}\n\n{prompt}" if system else prompt
        try:
            saida = pipe(
                entrada,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                return_full_text=False,
            )
        except Exception as exc:
            raise TransformersError(
                f"Falha na geração com Transformers: {type(exc).__name__}."
            ) from exc

        texto = ""
        if isinstance(saida, list) and saida:
            texto = str(saida[0].get("generated_text", "")).strip()
        if not texto:
            raise TransformersError("Transformers retornou resposta vazia.")
        logger.info("Interpretação gerada via Transformers (repo=%s).", self._repo_id)
        return texto
