"""Camada de entrega do relatório do Analytical-Force.

- ``file_writer``: salva o relatório Markdown localmente (sempre disponível).
- ``email_sender``: envia por e-mail via SMTP (opcional).
- ``clickup_sender``: cria tarefas para alertas críticos (opcional, gated).
"""

from .clickup_sender import criar_tarefas_de_alertas
from .email_sender import enviar_relatorio_email
from .file_writer import salvar_relatorio_md

__all__ = [
    "salvar_relatorio_md",
    "enviar_relatorio_email",
    "criar_tarefas_de_alertas",
]
