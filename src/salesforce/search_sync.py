"""Sincronização incremental do cache de busca (módulo de Consulta).

Roda como etapa BEST-EFFORT do pipeline diário (chamada por
``AnalyticalForceAgent.executar``): uma falha aqui nunca deve derrubar a
execução principal. Usa ``LastModifiedDate`` para buscar apenas o que mudou
desde a última sincronização (guardada em ``agent_config`` via
``ConfigRepository``), paginando por ``OFFSET`` respeitando o limite de 200
registros por página exigido pelo ``FIELDS(ALL)``.

É a camada de escrita da busca HÍBRIDA escolhida para o projeto: o cache
(Turso) responde rápido; quando não encontra, ``src/query/search_service.py``
cai para consulta ao vivo no Salesforce.
"""

from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from ..database.repositories import ConfigRepository, SearchCacheRepository
from ..salesforce.client import SalesforceAuthError, SalesforceClient
from ..utils.date_utils import agora_tz
from ..utils.logger import get_logger

logger = get_logger("salesforce.search_sync")

_LOTE = 200  # teto de registros por página exigido pelo FIELDS(ALL)
_MAX_REGISTROS_POR_OBJETO = 2000  # teto de segurança por execução/objeto
_CHAVE_ULTIMA_SYNC = "search_sync_last_{objeto}"
_DESDE_PADRAO = "2000-01-01T00:00:00Z"  # primeira sincronização: busca tudo (até o teto)


def _consultar_alterados(
    client: SalesforceClient, objeto: str, desde_iso: str
) -> list[dict[str, Any]]:
    """Busca (com paginação) os registros de ``objeto`` alterados desde ``desde_iso``."""
    registros: list[dict[str, Any]] = []
    offset = 0
    while offset < _MAX_REGISTROS_POR_OBJETO:
        soql = (
            f"SELECT FIELDS(ALL) FROM {objeto} "
            f"WHERE LastModifiedDate >= {desde_iso} "
            f"ORDER BY LastModifiedDate ASC LIMIT {_LOTE} OFFSET {offset}"
        )
        try:
            pagina = client.query(soql)
        except SalesforceAuthError as exc:
            # Objeto pode não existir na org (ex.: contrato customizado não
            # aplicável) — registra e segue sem quebrar os demais objetos.
            logger.warning("Sincronização de %s interrompida: %s", objeto, exc)
            break
        if not pagina:
            break
        registros.extend(pagina)
        if len(pagina) < _LOTE:
            break
        offset += _LOTE
    else:
        logger.warning(
            "Sincronização de %s atingiu o teto de segurança (%d); pode haver "
            "registros pendentes para o próximo ciclo.",
            objeto,
            _MAX_REGISTROS_POR_OBJETO,
        )
    return registros


def sincronizar_cache_busca(
    client: SalesforceClient,
    settings: Settings,
    config_repo: ConfigRepository,
    cache_repo: SearchCacheRepository,
) -> dict[str, int]:
    """Sincroniza incrementalmente Account/Opportunity/Contrato/Item no Turso.

    Cada objeto é isolado: uma falha em um (ex.: objeto de contrato não
    existe nesta org) não afeta a sincronização dos demais.

    Args:
        client: Cliente Salesforce já autenticado (reaproveitado da extração
            principal — evita autenticar duas vezes na mesma execução).
        settings: Configurações do agente (usa ``settings.contract_source``).
        config_repo: Repositório de configuração (guarda o "desde quando"
            de cada objeto).
        cache_repo: Repositório do cache de busca (destino da gravação).

    Returns:
        Dicionário ``{objeto: quantidade_sincronizada}``.
    """
    contrato_cfg = settings.contract_source or {}
    objetos: list[tuple[str, str, str | None]] = [
        ("Account", "Name", None),
        ("Opportunity", "Name", "StageName"),
        (contrato_cfg.get("object") or "Contrato_oPT__c", "Name", None),
        (contrato_cfg.get("item_object") or "Item_do_Contrato__c", "Name", None),
    ]
    agora_iso = agora_tz(settings.report_timezone).strftime("%Y-%m-%dT%H:%M:%SZ")
    resultado: dict[str, int] = {}

    for objeto, campo_nome, campo_subtitulo in objetos:
        chave = _CHAVE_ULTIMA_SYNC.format(objeto=objeto)
        try:
            desde = config_repo.buscar_config(chave) or _DESDE_PADRAO
            registros = _consultar_alterados(client, objeto, desde)
            gravados = cache_repo.upsert_registros(objeto, registros, campo_nome, campo_subtitulo)
            config_repo.salvar_config(
                chave,
                agora_iso,
                descricao=f"Última sincronização do cache de busca de {objeto}.",
            )
            resultado[objeto] = gravados
            logger.info("Cache de busca sincronizado: %s (%d registro(s)).", objeto, gravados)
        except Exception as exc:  # objeto isolado — não derruba os demais
            logger.warning("Falha ao sincronizar cache de %s: %s", objeto, type(exc).__name__)
            resultado[objeto] = 0

    return resultado
