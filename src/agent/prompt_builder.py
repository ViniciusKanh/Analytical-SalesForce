"""Construção do prompt enviado ao modelo de IA.

O modelo recebe APENAS o JSON estruturado com métricas já calculadas em
Python. Ele jamais deve recalcular números — apenas interpretar.

O texto base (system + instrução) fica embutido como constante, mas pode ser
sobrescrito por arquivos em ``prompts/`` (system_prompt.md e report_prompt.md)
para facilitar ajustes sem alterar o código.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger("agent.prompt_builder")

# Raiz do projeto (…/analytical-force).
_RAIZ_PROJETO = Path(__file__).resolve().parents[2]
_DIR_PROMPTS = _RAIZ_PROJETO / "prompts"

# Papel do modelo (mensagem de sistema padrão).
SYSTEM_PROMPT = (
    "Você é um analista comercial sênior. Recebe um JSON com métricas diárias "
    "JÁ CALCULADAS de um CRM (Salesforce). Sua tarefa é escrever, em Português "
    "do Brasil, um RESUMO EXECUTIVO interpretativo e acionável.\n"
    "Regras inegociáveis:\n"
    "1. NUNCA recalcule, invente ou altere números. Use apenas os valores do JSON.\n"
    "2. Separe claramente: fatos, diagnóstico, riscos e ações recomendadas.\n"
    "3. Toda conclusão deve estar ligada a uma métrica ou alerta presente no JSON.\n"
    "4. Seja direto e técnico. Não use saudações nem linguagem genérica.\n"
    "5. Produza no máximo 3 parágrafos curtos. Não repita a tabela de métricas."
)

# Instrução padrão que acompanha o JSON.
INSTRUCAO_PADRAO = (
    "A seguir está o JSON com as métricas, alertas e qualidade de dados do dia. "
    "Escreva o Resumo Executivo conforme as regras. Comece direto pelo conteúdo, "
    "sem títulos de seção."
)


def _ler_arquivo_opcional(caminho: Path) -> str | None:
    """Lê um arquivo de prompt opcional, retornando None se ausente."""
    try:
        if caminho.is_file():
            return caminho.read_text(encoding="utf-8").strip()
    except OSError as exc:  # pragma: no cover - depende do ambiente
        logger.warning("Falha ao ler prompt %s: %s", caminho.name, type(exc).__name__)
    return None


def obter_system_prompt() -> str:
    """Retorna o system prompt (de ``prompts/system_prompt.md`` ou padrão)."""
    return _ler_arquivo_opcional(_DIR_PROMPTS / "system_prompt.md") or SYSTEM_PROMPT


def construir_prompt(payload: dict[str, Any]) -> str:
    """Monta o prompt completo a partir do JSON de métricas.

    Args:
        payload: JSON estruturado (ver :mod:`agent.analytical_force_agent`).

    Returns:
        Prompt textual pronto para envio ao modelo.
    """
    instrucao = _ler_arquivo_opcional(_DIR_PROMPTS / "report_prompt.md") or INSTRUCAO_PADRAO
    json_metricas = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return f"{instrucao}\n\n```json\n{json_metricas}\n```"
