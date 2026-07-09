"""Consulta ao vivo (SOQL) para o módulo de Busca — somente leitura.

Não participa do pipeline diário de métricas: é usado sob demanda pelo
serviço de consulta (``src/query/search_service.py``) quando o cache do
Turso não tem o registro procurado, ou quando o dado precisa estar fresco.

Regra 3 do projeto (nunca inventar campos): a busca usa apenas ``Id``/``Name``
(sempre presentes em qualquer objeto do Salesforce, padrão ou customizado) e
o detalhe usa ``FIELDS(ALL)`` — os campos exibidos vêm do schema real da
organização (descoberto em tempo de execução), nunca fixados no código.
"""

from __future__ import annotations

import re
from typing import Any

from .client import SalesforceAuthError, SalesforceClient
from ..utils.logger import get_logger

logger = get_logger("salesforce.search")

# Formato de Id do Salesforce (15 ou 18 caracteres alfanuméricos).
_ID_VALIDO = re.compile(r"^[a-zA-Z0-9]{15,18}$")

# Nome de objeto/campo de API do Salesforce: letras, números, "_" e "__c"/"__r".
_NOME_API_VALIDO = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")

_LIMITE_MAXIMO_BUSCA = 50
_LIMITE_MAXIMO_DETALHE = 200  # teto exigido pelo SOQL ao usar FIELDS(ALL)/FIELDS(CUSTOM)


def _escapar_termo(termo: str) -> str:
    """Escapa aspas simples/barras para uso seguro em cláusula LIKE do SOQL."""
    return (termo or "").replace("\\", "\\\\").replace("'", "\\'")


def _validar_nome_api(nome: str, rotulo: str) -> str:
    """Garante que ``nome`` é um identificador de API válido (objeto/campo).

    Barreira contra injeção de SOQL nos poucos lugares em que o nome do
    objeto/campo é interpolado diretamente na consulta (esses nomes vêm de
    configuração interna — nunca de entrada livre do usuário).
    """
    if not nome or not _NOME_API_VALIDO.match(nome):
        raise SalesforceAuthError(f"{rotulo} inválido para consulta: {nome!r}")
    return nome


def _validar_id(record_id: str) -> str:
    """Garante que ``record_id`` tem o formato de um Id do Salesforce."""
    valor = (record_id or "").strip()
    if not _ID_VALIDO.match(valor):
        raise SalesforceAuthError("Id inválido para consulta.")
    return valor


def buscar_por_nome(
    client: SalesforceClient, objeto: str, termo: str, limite: int = 20
) -> list[dict[str, Any]]:
    """Busca registros de um objeto por trecho do campo ``Name`` (ao vivo).

    Args:
        client: Cliente Salesforce autenticado (somente leitura).
        objeto: Nome de API do objeto (ex.: ``"Account"``, ``"Opportunity"``).
        termo: Trecho buscado (aplica-se ``LIKE '%termo%'``).
        limite: Máximo de registros retornados (até 50).

    Returns:
        Lista de registros (``Id`` e ``Name``). Vazia em caso de falha —
        busca é uma funcionalidade auxiliar e não deve derrubar a tela.
    """
    _validar_nome_api(objeto, "Objeto")
    termo_esc = _escapar_termo(termo)
    limite = max(1, min(int(limite), _LIMITE_MAXIMO_BUSCA))
    soql = f"SELECT Id, Name FROM {objeto} WHERE Name LIKE '%{termo_esc}%' LIMIT {limite}"
    try:
        return client.query(soql)
    except SalesforceAuthError as exc:
        logger.warning("Busca ao vivo falhou em %s: %s", objeto, exc)
        return []


def detalhar_registro(
    client: SalesforceClient, objeto: str, record_id: str
) -> dict[str, Any] | None:
    """Retorna TODOS os campos populados de um registro (ao vivo).

    Usa ``FIELDS(ALL)`` (SOQL, disponível a partir da API v58.0) — os campos
    exibidos vêm do schema real da organização, nunca fixados no código.

    Args:
        client: Cliente Salesforce autenticado (somente leitura).
        objeto: Nome de API do objeto.
        record_id: Id do registro (validado antes de entrar na consulta).

    Returns:
        Dicionário de campos do registro, ou ``None`` se não encontrado.
    """
    _validar_nome_api(objeto, "Objeto")
    rid = _validar_id(record_id)
    soql = f"SELECT FIELDS(ALL) FROM {objeto} WHERE Id = '{rid}' LIMIT 1"
    registros = client.query(soql)
    return registros[0] if registros else None


def listar_relacionados(
    client: SalesforceClient,
    objeto_filho: str,
    campo_pai: str,
    id_pai: str,
    limite: int = 200,
) -> list[dict[str, Any]]:
    """Lista registros filhos vinculados a um pai por um campo de lookup.

    Usado, por exemplo, para listar os Itens de um Contrato quando o campo
    de vínculo (``SF_CONTRACT_ITEM_PARENT_FIELD``) estiver configurado.

    Args:
        objeto_filho: Nome de API do objeto filho (ex.: ``"Item_do_Contrato__c"``).
        campo_pai: Nome de API do campo de lookup que aponta para o pai.
        id_pai: Id do registro pai.
        limite: Máximo de registros retornados (até 200, teto do FIELDS(ALL)).
    """
    _validar_nome_api(objeto_filho, "Objeto filho")
    _validar_nome_api(campo_pai, "Campo de vínculo")
    rid = _validar_id(id_pai)
    limite = max(1, min(int(limite), _LIMITE_MAXIMO_DETALHE))
    soql = f"SELECT FIELDS(ALL) FROM {objeto_filho} WHERE {campo_pai} = '{rid}' LIMIT {limite}"
    return client.query(soql)
