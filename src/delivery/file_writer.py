"""Entrega do relatório em arquivo local (Markdown).

Salva o relatório diário em ``reports/daily/`` com nome baseado na data.
É a entrega mais simples e sempre disponível do agente.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger("delivery.file_writer")

# Diretório padrão de relatórios (…/analytical-force/reports/daily).
_RAIZ_PROJETO = Path(__file__).resolve().parents[2]
_DIR_RELATORIOS = _RAIZ_PROJETO / "reports" / "daily"


def salvar_relatorio_md(
    markdown: str, dia: date, dir_reports: Path | None = None
) -> Path:
    """Salva o relatório em Markdown no diretório de relatórios.

    Args:
        markdown: Conteúdo do relatório.
        dia: Dia de referência (compõe o nome do arquivo).
        dir_reports: Diretório de saída (padrão: ``reports/daily``).

    Returns:
        Caminho completo do arquivo salvo.

    Raises:
        OSError: Se não for possível escrever o arquivo.
    """
    destino = dir_reports or _DIR_RELATORIOS
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"relatorio_{dia.isoformat()}.md"
    caminho = destino / nome
    caminho.write_text(markdown, encoding="utf-8")
    logger.info("Relatório salvo em %s.", caminho)
    return caminho
