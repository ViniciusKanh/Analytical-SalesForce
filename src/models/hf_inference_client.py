"""Cliente de inferência hospedada (Hugging Face Inference Providers).

Em vez de rodar o modelo localmente (lento em CPU), envia o prompt para um
modelo bom hospedado nos provedores roteados pela Hugging Face (GPU), via API
compatível com OpenAI (``chat.completions``). Rápido e 100% online.

Requisitos:
- ``HF_TOKEN`` com permissão de uso de Inference Providers.
- ``HF_INFERENCE_MODEL`` (ex.: ``Qwen/Qwen2.5-7B-Instruct``).

Princípio do projeto: a IA apenas interpreta; nunca calcula indicadores.
Qualquer falha levanta :class:`HFInferenceError` para acionar o fallback.
"""

from __future__ import annotations

from ..utils.logger import get_logger

logger = get_logger("models.hf_inference")


class HFInferenceError(RuntimeError):
    """Erro controlado ao usar a inferência hospedada da Hugging Face."""


class HFInferenceClient:
    """Encapsula chamadas de chat à Inference API da Hugging Face."""

    def __init__(
        self,
        model: str,
        token: str,
        max_tokens: int = 320,
        provider: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        """Inicializa o cliente.

        Args:
            model: Repo do modelo (ex.: ``Qwen/Qwen2.5-7B-Instruct``).
            token: Token da Hugging Face (``HF_TOKEN``).
            max_tokens: Limite de tokens da resposta.
            provider: Provedor específico (opcional; ``None`` = roteamento automático).
            temperature: Temperatura de amostragem (baixa = mais objetivo).

        Raises:
            HFInferenceError: Se faltar token ou modelo.
        """
        if not token:
            raise HFInferenceError(
                "HF_TOKEN não configurado para inferência hospedada."
            )
        if not model:
            raise HFInferenceError(
                "HF_INFERENCE_MODEL não configurado. Ex.: Qwen/Qwen2.5-7B-Instruct."
            )
        self._model = model
        self._token = token
        self._max_tokens = max_tokens
        self._provider = provider or None
        self._temperature = temperature

    def gerar(self, prompt: str, system: str | None = None) -> str:
        """Gera a interpretação via chat completion hospedada.

        Args:
            prompt: Prompt com o JSON de métricas já calculado.
            system: Instrução de sistema (papel do modelo).

        Returns:
            Texto interpretativo gerado pelo modelo.

        Raises:
            HFInferenceError: Em qualquer falha de dependência, rede ou resposta.
        """
        try:
            from huggingface_hub import InferenceClient  # import tardio
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise HFInferenceError(
                "Dependência ausente. Instale: pip install huggingface_hub"
            ) from exc

        mensagens: list[dict[str, str]] = []
        if system:
            mensagens.append({"role": "system", "content": system})
        mensagens.append({"role": "user", "content": prompt})

        try:
            kwargs: dict[str, object] = {"token": self._token}
            if self._provider:
                kwargs["provider"] = self._provider
            cliente = InferenceClient(**kwargs)
            resposta = cliente.chat.completions.create(
                model=self._model,
                messages=mensagens,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as exc:  # rede, modelo indisponível, créditos, etc.
            # Não vaza o token; apenas o tipo/mensagem do erro.
            raise HFInferenceError(
                f"Falha na inferência hospedada: {type(exc).__name__}: {exc}"
            ) from exc

        try:
            texto = (resposta.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError) as exc:
            raise HFInferenceError("Resposta de inferência sem conteúdo.") from exc
        if not texto:
            raise HFInferenceError("Inferência hospedada retornou resposta vazia.")
        logger.info("Interpretação gerada via HF Inference (model=%s).", self._model)
        return texto
