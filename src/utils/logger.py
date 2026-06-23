"""Configuração centralizada de logging do Analytical-Force.

Fornece um logger com saída para console e arquivo (``logs/analytical_force.log``).
Inclui um filtro simples que evita o vazamento acidental de segredos no log.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Diretório de logs na raiz do projeto.
_RAIZ_PROJETO = Path(__file__).resolve().parents[2]
_DIR_LOGS = _RAIZ_PROJETO / "logs"
_ARQUIVO_LOG = _DIR_LOGS / "analytical_force.log"

# Nome do logger raiz do projeto.
_NOME_LOGGER = "analytical_force"

# Padrões que NÃO devem aparecer no log (mascarados como ***).
# Cobre chaves comuns e valores tipo token/secret.
_PADROES_SENSIVEIS = [
    re.compile(r"(?i)(password\s*[=:]\s*)(\S+)"),
    re.compile(r"(?i)(token\s*[=:]\s*)(\S+)"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)(\S+)"),
    re.compile(r"(?i)(secret\s*[=:]\s*)(\S+)"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)"),
]


class _FiltroSegredos(logging.Filter):
    """Filtro que mascara valores sensíveis nas mensagens de log."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            mensagem = record.getMessage()
        except Exception:
            return True
        original = mensagem
        for padrao in _PADROES_SENSIVEIS:
            mensagem = padrao.sub(r"\1***", mensagem)
        if mensagem != original:
            # Substitui args já formatados pela versão mascarada.
            record.msg = mensagem
            record.args = None
        return True


def configurar_logger(nivel: int = logging.INFO) -> logging.Logger:
    """Configura e retorna o logger raiz do projeto.

    É idempotente: chamadas repetidas não duplicam handlers.

    Args:
        nivel: Nível de log (ex.: ``logging.INFO``, ``logging.DEBUG``).

    Returns:
        Logger configurado.
    """
    logger = logging.getLogger(_NOME_LOGGER)
    logger.setLevel(nivel)

    # Evita adicionar handlers duplicados em re-execuções/imports.
    if logger.handlers:
        return logger

    formato = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    filtro = _FiltroSegredos()

    # Handler de console.
    console = logging.StreamHandler()
    console.setFormatter(formato)
    console.addFilter(filtro)
    logger.addHandler(console)

    # Handler de arquivo com rotação (best-effort: não quebra se faltar permissão).
    try:
        _DIR_LOGS.mkdir(parents=True, exist_ok=True)
        arquivo = RotatingFileHandler(
            _ARQUIVO_LOG, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        arquivo.setFormatter(formato)
        arquivo.addFilter(filtro)
        logger.addHandler(arquivo)
    except OSError:
        logger.warning("Não foi possível criar o arquivo de log em %s", _ARQUIVO_LOG)

    # Não propaga para o root logger para evitar logs duplicados.
    logger.propagate = False
    return logger


def get_logger(nome: str | None = None) -> logging.Logger:
    """Retorna um logger filho do logger do projeto.

    Args:
        nome: Sufixo do logger (ex.: ``"salesforce"``). Se None, retorna o raiz.

    Returns:
        Logger pronto para uso.
    """
    # Garante que o logger raiz esteja configurado ao menos uma vez.
    configurar_logger()
    if nome:
        return logging.getLogger(f"{_NOME_LOGGER}.{nome}")
    return logging.getLogger(_NOME_LOGGER)
