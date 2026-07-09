"""Camada de Consulta (busca somente leitura) do Analytical-Force.

Diferente de ``analytics`` (que calcula métricas do pipeline diário), este
pacote orquestra a busca/detalhe sob demanda de Contas, Oportunidades,
Contratos e Itens de Contrato para o painel — usada pela tela de "Busca".
"""

from .search_service import TIPOS_VALIDOS, buscar, detalhar, status_tipos

__all__ = ["TIPOS_VALIDOS", "buscar", "detalhar", "status_tipos"]
