"""Cliente do Ollama (modelo local).

Chama a API HTTP local do Ollama (``/api/generate``) para obter a
interpretação textual do relatório. Não exige autenticação em acesso local.

Princípio: este cliente NUNCA calcula indicadores. Ele apenas recebe um
prompt (já contendo o JSON de métricas calculado em Python) e devolve texto.
Em caso de falha, levanta :class:`OllamaError` para acionar o fallback.
"""

from __future__ import annotations

import requests

from ..utils.logger import get_logger

logger = get_logger("models.ollama")


class OllamaError(RuntimeError):
    """Erro controlado de comunicação com o Ollama."""


class OllamaClient:
    """Encapsula chamadas à API local do Ollama."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: int = 120,
    ) -> None:
        """Inicializa o cliente.

        Args:
            base_url: URL base do Ollama (ex.: ``http://localhost:11434``).
            model: Nome do modelo local (ex.: ``llama3.1:8b``).
            timeout: Tempo máximo (s) de espera pela resposta.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def gerar(self, prompt: str, system: str | None = None) -> str:
        """Envia um prompt ao Ollama e retorna o texto gerado.

        Args:
            prompt: Prompt completo (com o JSON de métricas).
            system: Mensagem de sistema opcional (papel/instruções gerais).

        Returns:
            Texto interpretativo gerado pelo modelo.

        Raises:
            OllamaError: Se o Ollama não responder ou retornar erro.
        """
        url = f"{self._base_url}/api/generate"
        corpo: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            corpo["system"] = system

        try:
            resposta = requests.post(url, json=corpo, timeout=self._timeout)
            resposta.raise_for_status()
            dados = resposta.json()
        except requests.exceptions.ConnectionError as exc:
            raise OllamaError(
                "Não foi possível conectar ao Ollama. Verifique se ele está em execução "
                f"em {self._base_url} (comando: 'ollama serve')."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaError("Tempo de resposta do Ollama excedido.") from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaError(f"Erro na chamada ao Ollama: {type(exc).__name__}.") from exc
        except ValueError as exc:  # JSON inválido
            raise OllamaError("Resposta do Ollama não é um JSON válido.") from exc

        texto = (dados or {}).get("response", "")
        if not texto or not texto.strip():
            raise OllamaError("Ollama retornou resposta vazia.")
        logger.info("Interpretação gerada pelo Ollama (modelo=%s).", self._model)
        return texto.strip()
