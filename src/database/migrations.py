"""Migrations do banco Turso/libSQL.

Cria as tabelas necessárias para o agente. Todas usam ``IF NOT EXISTS``,
portanto a execução é idempotente e segura para rodar em todo boot.

Tabelas:
- agent_runs: histórico de execuções do agente.
- daily_metrics: métricas diárias calculadas em Python.
- daily_alerts: alertas gerados pelo motor de risco.
- daily_reports: relatórios (Markdown + JSON) gerados.
- salesforce_snapshots: payloads brutos extraídos do Salesforce.
- object_mapping: mapeamento configurável de objetos/campos customizados.
- agent_config: parâmetros de configuração persistidos.
"""

from __future__ import annotations

from .turso_client import TursoClient
from ..utils.logger import get_logger

logger = get_logger("database.migrations")

# Lista ordenada de comandos DDL. Mantida explícita para rastreabilidade.
_DDL: list[str] = [
    # 9.1 — Execuções do agente
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TEXT NOT NULL
    );
    """,
    # 9.2 — Métricas diárias
    """
    CREATE TABLE IF NOT EXISTS daily_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_date TEXT NOT NULL,
        category TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        metric_text TEXT,
        comparison_value REAL,
        variation_value REAL,
        variation_percent REAL,
        created_at TEXT NOT NULL
    );
    """,
    # 9.3 — Alertas diários
    """
    CREATE TABLE IF NOT EXISTS daily_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_date TEXT NOT NULL,
        severity TEXT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        recommended_action TEXT,
        source_object TEXT,
        source_record_id TEXT,
        created_at TEXT NOT NULL
    );
    """,
    # 9.4 — Relatórios diários
    """
    CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT NOT NULL,
        report_markdown TEXT NOT NULL,
        report_json TEXT NOT NULL,
        llm_provider TEXT,
        created_at TEXT NOT NULL
    );
    """,
    # 9.5 — Snapshots brutos do Salesforce
    """
    CREATE TABLE IF NOT EXISTS salesforce_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date TEXT NOT NULL,
        object_name TEXT NOT NULL,
        record_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    # 9.6 — Mapeamento de objetos customizados
    """
    CREATE TABLE IF NOT EXISTS object_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL,
        salesforce_object TEXT NOT NULL,
        field_mapping_json TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT
    );
    """,
    # 9.7 — Configuração do agente
    """
    CREATE TABLE IF NOT EXISTS agent_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_key TEXT NOT NULL UNIQUE,
        config_value TEXT NOT NULL,
        description TEXT,
        updated_at TEXT
    );
    """,
    # 9.8 — Cache de busca (mirror somente leitura para o módulo de Consulta).
    # Guarda um "espelho" de Account/Opportunity/Contrato/Item de Contrato,
    # sincronizado incrementalmente pelo pipeline diário. É a camada RÁPIDA
    # da busca híbrida; quando não encontra ou o dado precisa estar fresco,
    # a consulta cai para o Salesforce ao vivo (ver src/query/search_service.py).
    """
    CREATE TABLE IF NOT EXISTS search_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_name TEXT NOT NULL,
        record_id TEXT NOT NULL,
        display_name TEXT,
        subtitle TEXT,
        payload_json TEXT NOT NULL,
        synced_at TEXT NOT NULL,
        UNIQUE(object_name, record_id)
    );
    """,
]

# Índices para acelerar buscas históricas (comparação dia anterior / 7 dias).
_INDICES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_daily_metrics_date "
    "ON daily_metrics (metric_date, category, metric_name);",
    "CREATE INDEX IF NOT EXISTS idx_daily_alerts_date "
    "ON daily_alerts (alert_date, severity);",
    "CREATE INDEX IF NOT EXISTS idx_daily_reports_date "
    "ON daily_reports (report_date);",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_date_obj "
    "ON salesforce_snapshots (snapshot_date, object_name);",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_date "
    "ON agent_runs (run_date, status);",
    "CREATE INDEX IF NOT EXISTS idx_search_cache_lookup "
    "ON search_cache (object_name, display_name);",
]


def run_migrations(client: TursoClient) -> None:
    """Cria todas as tabelas e índices no banco Turso.

    Args:
        client: Cliente Turso já configurado.
    """
    logger.info("Executando migrations do Turso...")
    for ddl in _DDL:
        client.execute_query(ddl)
    for indice in _INDICES:
        client.execute_query(indice)
    logger.info("Migrations concluídas (%d tabelas, %d índices).", len(_DDL), len(_INDICES))
