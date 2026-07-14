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
    "do Brasil, um RESUMO EXECUTIVO em formato de STORYTELLING — uma narrativa "
    "que CONVENÇA a liderança com os dados, e não uma lista seca de números.\n"
    "Regras inegociáveis:\n"
    "1. NUNCA recalcule, invente ou altere números. Use apenas os valores do JSON.\n"
    "2. Toda conclusão deve estar ligada a uma métrica ou alerta presente no JSON — "
    "nada de generalidades sem dado por trás.\n"
    "3. Construa uma narrativa com começo (cenário do dia), meio (o que os "
    "números revelam — leads, oportunidades, contratos/reajustes, satisfação) "
    "e fim (para onde a liderança deve olhar agora). Use uma progressão lógica, "
    "não uma lista de tópicos soltos.\n"
    "4. Use um tom direto e confiante, com dados concretos como prova (ex.: "
    "'as oportunidades de alto valor paradas somam R$ X e concentram o risco "
    "de hoje') — o objetivo é persuadir com evidência, não com adjetivos vazios.\n"
    "5. Não use saudações, títulos de seção nem linguagem genérica de IA.\n"
    "6. Produza de 3 a 5 parágrafos curtos e coesos. Não repita a tabela de métricas.\n"
    "7. Se o JSON trouxer um aviso de qualidade de dados (ex.: reajuste de "
    "contrato estimado), mencione a ressalva de forma transparente, sem "
    "esconder a incerteza."
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
