"""Serviço de Consulta (busca híbrida) — camada de orquestração.

Não calcula métricas nem gera relatório: apenas orquestra a busca de
Account, Opportunity, Contrato e Item de Contrato para o painel, seguindo a
estratégia HÍBRIDA definida para o projeto:

1. Busca primeiro no cache do Turso (``search_cache``) — rápido.
2. Se não encontrar nada, cai para consulta ao vivo no Salesforce (somente
   leitura) e, quando encontra algo, grava o resultado no cache para
   acelerar a próxima busca pelo mesmo termo.

Esta é a ÚNICA camada que conhece o mapeamento "tipo lógico -> objeto do
Salesforce". A API HTTP (``api.py``) nunca deve aceitar um nome de objeto
arbitrário vindo do cliente — apenas um dos tipos em :data:`TIPOS_VALIDOS`,
o que evita qualquer risco de injeção de SOQL pela camada web.
"""

from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from ..database.repositories import SearchCacheRepository
from ..database.turso_client import TursoClient
from ..salesforce import search as sf_search
from ..salesforce.client import SalesforceAuthError, SalesforceClient
from ..utils.logger import get_logger

logger = get_logger("query.search_service")

# Tipos lógicos aceitos pela API — único ponto que traduz para o objeto real
# do Salesforce. Nunca exponha nomes de objeto direto na API HTTP.
TIPOS_VALIDOS: tuple[str, ...] = ("conta", "oportunidade", "contrato", "item")

_ROTULOS = {
    "conta": "Clientes (Account)",
    "oportunidade": "Oportunidades",
    "contrato": "Contratos",
    "item": "Itens de contrato",
}

_TAMANHO_MINIMO_TERMO = 2


def _mapa_objetos(settings: Settings) -> dict[str, str]:
    """Mapa tipo lógico -> nome de API do objeto Salesforce."""
    contrato = settings.contract_source or {}
    return {
        "conta": "Account",
        "oportunidade": "Opportunity",
        "contrato": contrato.get("object") or "Contrato_oPT__c",
        "item": contrato.get("item_object") or "Item_do_Contrato__c",
    }


def status_tipos(settings: Settings) -> dict[str, Any]:
    """Retorna os tipos de busca disponíveis e o estado da configuração.

    Usado pela tela de Busca para exibir avisos (ex.: "vínculo com conta
    não configurado") sem travar a funcionalidade principal.
    """
    contrato = settings.contract_source or {}
    mapa = _mapa_objetos(settings)
    return {
        "tipos": [
            {"tipo": tipo, "objeto": objeto, "rotulo": _ROTULOS.get(tipo, tipo)}
            for tipo, objeto in mapa.items()
        ],
        "conta_do_contrato_configurada": bool(contrato.get("account_field")),
        "itens_do_contrato_configurados": bool(contrato.get("item_parent_field")),
    }


def buscar(
    settings: Settings,
    turso: TursoClient,
    sf_client: SalesforceClient,
    termo: str,
    tipos: list[str] | None = None,
    limite: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Busca híbrida: cache do Turso primeiro, Salesforce ao vivo como fallback.

    Args:
        termo: Texto buscado (mínimo 2 caracteres — evita varreduras amplas).
        tipos: Subconjunto de :data:`TIPOS_VALIDOS` (``None`` = todos).
        limite: Máximo de resultados por tipo.

    Returns:
        Dicionário ``{tipo: [{id, name, subtitle}, ...]}`` — tipos sem
        resultado não aparecem na resposta.
    """
    termo = (termo or "").strip()
    if len(termo) < _TAMANHO_MINIMO_TERMO:
        return {}

    mapa = _mapa_objetos(settings)
    tipos_busca = [t for t in (tipos or TIPOS_VALIDOS) if t in mapa]
    cache = SearchCacheRepository(turso)
    resultado: dict[str, list[dict[str, Any]]] = {}

    for tipo in tipos_busca:
        objeto = mapa[tipo]
        achados: list[dict[str, Any]] = []
        try:
            achados = cache.buscar(objeto, termo, limite)
        except Exception as exc:  # cache não deve derrubar a busca
            logger.warning("Falha ao consultar cache de %s: %s", objeto, type(exc).__name__)

        if not achados:
            # Fallback: Salesforce ao vivo (somente leitura).
            try:
                registros = sf_search.buscar_por_nome(sf_client, objeto, termo, limite)
                achados = [
                    {"id": r.get("Id"), "name": r.get("Name") or r.get("Id"), "subtitle": None}
                    for r in registros
                ]
                if registros:
                    # Alimenta o cache com o achado ao vivo (acelera a próxima busca).
                    try:
                        cache.upsert_registros(objeto, registros)
                    except Exception as exc:
                        logger.warning(
                            "Falha ao alimentar cache de %s: %s", objeto, type(exc).__name__
                        )
            except SalesforceAuthError as exc:
                logger.warning("Busca ao vivo falhou em %s: %s", objeto, exc)

        if achados:
            resultado[tipo] = achados

    return resultado


def detalhar(
    settings: Settings,
    turso: TursoClient,
    sf_client: SalesforceClient,
    tipo: str,
    record_id: str,
) -> dict[str, Any]:
    """Detalhe completo de um registro (ao vivo; cache como último recurso).

    Prioriza a consulta ao vivo para o DETALHE (mais sensível a estar
    desatualizado do que a lista de busca); só usa o cache se o Salesforce
    falhar (ex.: instabilidade momentânea da API).

    Args:
        tipo: Um dos :data:`TIPOS_VALIDOS`.
        record_id: Id do registro no Salesforce.

    Returns:
        Dicionário com ``tipo``, ``objeto``, ``origem`` (salesforce/cache),
        ``campos`` (lista ``{campo, valor}``) e, para contratos,
        ``itens_do_contrato`` quando o vínculo estiver configurado.

    Raises:
        ValueError: Tipo inválido ou registro não encontrado em nenhuma fonte.
    """
    mapa = _mapa_objetos(settings)
    if tipo not in mapa:
        raise ValueError(f"Tipo de consulta inválido: {tipo!r}")
    objeto = mapa[tipo]
    cache = SearchCacheRepository(turso)

    payload: dict[str, Any] | None = None
    origem = "salesforce"
    try:
        payload = sf_search.detalhar_registro(sf_client, objeto, record_id)
        if payload:
            try:
                cache.upsert_registros(objeto, [payload])
            except Exception as exc:
                logger.warning("Falha ao atualizar cache de %s: %s", objeto, type(exc).__name__)
    except SalesforceAuthError as exc:
        logger.warning("Detalhe ao vivo falhou em %s/%s: %s", objeto, record_id, exc)

    if not payload:
        cacheado = cache.buscar_por_id(objeto, record_id)
        if cacheado:
            payload = cacheado["payload"]
            origem = f"cache (sincronizado em {cacheado.get('synced_at')})"

    if not payload:
        raise ValueError(f"Registro não encontrado: {objeto}/{record_id}")

    resultado: dict[str, Any] = {
        "tipo": tipo,
        "objeto": objeto,
        "origem": origem,
        "campos": [
            {"campo": campo, "valor": valor}
            for campo, valor in payload.items()
            if campo != "attributes" and valor is not None
        ],
    }

    # Contrato -> lista os itens vinculados, se o campo de vínculo estiver configurado.
    if tipo == "contrato":
        contrato_cfg = settings.contract_source or {}
        campo_pai = contrato_cfg.get("item_parent_field")
        if campo_pai:
            try:
                itens = sf_search.listar_relacionados(sf_client, mapa["item"], campo_pai, record_id)
                resultado["itens_do_contrato"] = itens
            except SalesforceAuthError as exc:
                logger.warning("Falha ao listar itens do contrato: %s", exc)
                resultado["itens_do_contrato"] = []
        else:
            resultado["itens_do_contrato"] = None  # vínculo não configurado

    return resultado
