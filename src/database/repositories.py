"""Repositórios de acesso ao banco Turso.

Esta camada isola o SQL da regra de negócio. Cada repositório cuida de uma
tabela e expõe operações de leitura/escrita com tipos claros.

Regra do projeto: aqui NÃO há cálculo de indicadores nem geração de texto.
Apenas persistência e consulta.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .turso_client import TursoClient
from ..utils.date_utils import agora_tz, datas_dos_ultimos_n_dias, para_soql_date
from ..utils.logger import get_logger

logger = get_logger("database.repositories")


def _agora_iso() -> str:
    """Timestamp atual (timezone do projeto) em ISO 8601."""
    return agora_tz().isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# agent_runs
# ----------------------------------------------------------------------
class AgentRunRepository:
    """Operações sobre a tabela ``agent_runs``."""

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def iniciar_execucao(self, run_date: date) -> int:
        """Registra o início de uma execução e retorna o ID gerado.

        Args:
            run_date: Data de referência da execução.

        Returns:
            ID da linha criada em ``agent_runs``.
        """
        agora = _agora_iso()
        cursor = self._client.execute_query(
            """
            INSERT INTO agent_runs (run_date, started_at, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (para_soql_date(run_date), agora, "running", agora),
        )
        # lastrowid é a forma padrão de obter o autoincrement.
        run_id = getattr(cursor, "lastrowid", None)
        if run_id is None:
            linha = self._client.fetch_one(
                "SELECT id FROM agent_runs ORDER BY id DESC LIMIT 1"
            )
            run_id = int(linha["id"]) if linha else -1
        logger.info("Execução iniciada (run_id=%s, data=%s).", run_id, run_date)
        return int(run_id)

    def finalizar_execucao(
        self, run_id: int, status: str, error_message: str | None = None
    ) -> None:
        """Atualiza o status final de uma execução.

        Args:
            run_id: ID da execução.
            status: ``"success"`` ou ``"error"``.
            error_message: Mensagem de erro (quando status = error).
        """
        self._client.execute_query(
            """
            UPDATE agent_runs
               SET finished_at = ?, status = ?, error_message = ?
             WHERE id = ?
            """,
            (_agora_iso(), status, error_message, run_id),
        )
        logger.info("Execução finalizada (run_id=%s, status=%s).", run_id, status)


# ----------------------------------------------------------------------
# daily_metrics
# ----------------------------------------------------------------------
class MetricsRepository:
    """Operações sobre a tabela ``daily_metrics``.

    As métricas são armazenadas em formato "longo": uma linha por
    (categoria, nome_da_métrica) por dia. Valores numéricos vão em
    ``metric_value``; valores textuais em ``metric_text``.
    """

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def salvar_metricas(self, metric_date: date, metrics: dict[str, Any]) -> None:
        """Persiste o dicionário de métricas calculado em Python.

        Args:
            metric_date: Data de referência.
            metrics: Dicionário ``{categoria: {nome: valor}}``.
        """
        data_str = para_soql_date(metric_date)
        agora = _agora_iso()
        linhas: list[tuple[Any, ...]] = []

        for categoria, indicadores in metrics.items():
            if not isinstance(indicadores, dict):
                continue
            for nome, valor in indicadores.items():
                metric_value, metric_text = self._classificar_valor(valor)
                linhas.append(
                    (
                        data_str,
                        categoria,
                        nome,
                        metric_value,
                        metric_text,
                        None,  # comparison_value (preenchido por comparação posterior)
                        None,  # variation_value
                        None,  # variation_percent
                        agora,
                    )
                )

        if not linhas:
            logger.warning("Nenhuma métrica numérica/textual para salvar em %s.", data_str)
            return

        # Evita duplicidade ao reexecutar o mesmo dia.
        self._client.execute_query(
            "DELETE FROM daily_metrics WHERE metric_date = ?", (data_str,)
        )
        self._client.execute_many(
            """
            INSERT INTO daily_metrics
                (metric_date, category, metric_name, metric_value, metric_text,
                 comparison_value, variation_value, variation_percent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            linhas,
        )
        logger.info("Salvas %d métricas para %s.", len(linhas), data_str)

    @staticmethod
    def _classificar_valor(valor: Any) -> tuple[float | None, str | None]:
        """Separa um valor entre numérico (metric_value) e textual (metric_text)."""
        if isinstance(valor, bool):
            # Booleano vira texto para não se confundir com 0/1 numérico.
            return None, str(valor)
        if isinstance(valor, (int, float)):
            return float(valor), None
        if valor is None:
            return None, None
        # Listas/dicts e strings são serializados como texto.
        if isinstance(valor, (list, dict)):
            return None, json.dumps(valor, ensure_ascii=False)
        return None, str(valor)

    def buscar_metricas_do_dia(self, metric_date: date) -> dict[str, dict[str, Any]]:
        """Retorna as métricas de um dia em formato aninhado.

        Returns:
            Dicionário ``{categoria: {nome: valor}}``.
        """
        linhas = self._client.fetch_all(
            """
            SELECT category, metric_name, metric_value, metric_text
              FROM daily_metrics
             WHERE metric_date = ?
            """,
            (para_soql_date(metric_date),),
        )
        resultado: dict[str, dict[str, Any]] = {}
        for linha in linhas:
            categoria = linha["category"]
            nome = linha["metric_name"]
            valor = (
                linha["metric_value"]
                if linha["metric_value"] is not None
                else linha["metric_text"]
            )
            resultado.setdefault(categoria, {})[nome] = valor
        return resultado

    def buscar_media_ultimos_7_dias(
        self, referencia: date
    ) -> dict[str, dict[str, float]]:
        """Calcula a média numérica dos últimos 7 dias anteriores à referência.

        Apenas métricas numéricas entram na média.

        Args:
            referencia: Data atual (não incluída no cálculo).

        Returns:
            Dicionário ``{categoria: {nome: media}}``.
        """
        dias = datas_dos_ultimos_n_dias(referencia, 7)
        datas_str = [para_soql_date(d) for d in dias]
        placeholders = ",".join("?" for _ in datas_str)

        linhas = self._client.fetch_all(
            f"""
            SELECT category, metric_name, AVG(metric_value) AS media
              FROM daily_metrics
             WHERE metric_date IN ({placeholders})
               AND metric_value IS NOT NULL
             GROUP BY category, metric_name
            """,
            datas_str,
        )
        resultado: dict[str, dict[str, float]] = {}
        for linha in linhas:
            categoria = linha["category"]
            nome = linha["metric_name"]
            media = linha["media"]
            if media is not None:
                resultado.setdefault(categoria, {})[nome] = round(float(media), 4)
        return resultado


# ----------------------------------------------------------------------
# daily_alerts
# ----------------------------------------------------------------------
class AlertsRepository:
    """Operações sobre a tabela ``daily_alerts``."""

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def salvar_alertas(self, alert_date: date, alerts: list[dict[str, Any]]) -> None:
        """Persiste a lista de alertas gerada pelo motor de risco.

        Args:
            alert_date: Data de referência.
            alerts: Lista de dicionários de alerta.
        """
        data_str = para_soql_date(alert_date)
        agora = _agora_iso()

        # Limpa alertas anteriores do mesmo dia para idempotência.
        self._client.execute_query(
            "DELETE FROM daily_alerts WHERE alert_date = ?", (data_str,)
        )
        if not alerts:
            logger.info("Nenhum alerta gerado para %s.", data_str)
            return

        linhas = [
            (
                data_str,
                a.get("severity", "low"),
                a.get("category", "Geral"),
                a.get("title", ""),
                a.get("description", ""),
                a.get("recommended_action"),
                a.get("source_object"),
                a.get("source_record_id"),
                agora,
            )
            for a in alerts
        ]
        self._client.execute_many(
            """
            INSERT INTO daily_alerts
                (alert_date, severity, category, title, description,
                 recommended_action, source_object, source_record_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            linhas,
        )
        logger.info("Salvos %d alertas para %s.", len(linhas), data_str)


# ----------------------------------------------------------------------
# daily_reports
# ----------------------------------------------------------------------
class ReportRepository:
    """Operações sobre a tabela ``daily_reports``."""

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def salvar_relatorio(
        self,
        report_date: date,
        markdown: str,
        payload_json: dict[str, Any],
        llm_provider: str,
    ) -> None:
        """Persiste o relatório (Markdown + JSON de entrada da IA)."""
        data_str = para_soql_date(report_date)
        self._client.execute_query(
            "DELETE FROM daily_reports WHERE report_date = ?", (data_str,)
        )
        self._client.execute_query(
            """
            INSERT INTO daily_reports
                (report_date, report_markdown, report_json, llm_provider, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data_str,
                markdown,
                json.dumps(payload_json, ensure_ascii=False),
                llm_provider,
                _agora_iso(),
            ),
        )
        logger.info("Relatório salvo no Turso para %s (provider=%s).", data_str, llm_provider)

    def buscar_relatorio(self, report_date: date) -> dict[str, Any] | None:
        """Busca o relatório salvo de um dia (Markdown + payload JSON completo).

        O ``payload`` inclui métricas, alertas, destaques e qualidade de dados —
        ou seja, tudo que o front precisa para montar as telas a partir do banco.
        """
        linha = self._client.fetch_one(
            """
            SELECT report_markdown, report_json, llm_provider, created_at
              FROM daily_reports WHERE report_date = ?
            """,
            (para_soql_date(report_date),),
        )
        if not linha:
            return None
        try:
            payload = json.loads(linha.get("report_json") or "{}")
        except (ValueError, TypeError):
            payload = {}
        return {
            "markdown": linha.get("report_markdown") or "",
            "payload": payload,
            "provider": linha.get("llm_provider"),
            "created_at": linha.get("created_at"),
        }

    def listar_datas(self, limite: int = 90) -> list[str]:
        """Lista as datas (mais recentes primeiro) que possuem relatório salvo."""
        linhas = self._client.fetch_all(
            "SELECT report_date FROM daily_reports ORDER BY report_date DESC LIMIT ?",
            (int(limite),),
        )
        return [linha["report_date"] for linha in linhas if linha.get("report_date")]


# ----------------------------------------------------------------------
# salesforce_snapshots
# ----------------------------------------------------------------------
class SnapshotRepository:
    """Operações sobre a tabela ``salesforce_snapshots``."""

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def salvar_snapshots(
        self,
        snapshot_date: date,
        object_name: str,
        registros: list[dict[str, Any]],
        id_field: str = "Id",
    ) -> None:
        """Persiste payloads brutos de um objeto do Salesforce.

        Args:
            snapshot_date: Data do snapshot.
            object_name: Nome do objeto (ex.: ``Lead``).
            registros: Lista de registros (dicionários).
            id_field: Campo identificador do registro.
        """
        if not registros:
            return
        data_str = para_soql_date(snapshot_date)
        agora = _agora_iso()
        # Idempotência: remove snapshots anteriores do mesmo dia+objeto para não
        # acumular a cada reexecução (evita inchar a tabela salesforce_snapshots).
        self._client.execute_query(
            "DELETE FROM salesforce_snapshots WHERE snapshot_date = ? AND object_name = ?",
            (data_str, object_name),
        )
        linhas = [
            (
                data_str,
                object_name,
                str(reg.get(id_field, "")),
                json.dumps(reg, ensure_ascii=False, default=str),
                agora,
            )
            for reg in registros
        ]
        self._client.execute_many(
            """
            INSERT INTO salesforce_snapshots
                (snapshot_date, object_name, record_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            linhas,
        )
        logger.info(
            "Salvos %d snapshots de %s para %s.", len(linhas), object_name, data_str
        )


# ----------------------------------------------------------------------
# agent_config
# ----------------------------------------------------------------------
# Chave usada em ``agent_config`` para persistir os e-mails em cópia (Cc)
# do relatório diário. Cadastrados pelo painel (React), sem precisar de
# redeploy — ao contrário do destinatário principal, que vem do .env.
_CHAVE_EMAILS_CC = "email_cc_recipients"


class ConfigRepository:
    """Operações sobre a tabela ``agent_config``."""

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def listar_emails_cc(self) -> list[str]:
        """Retorna a lista de e-mails em cópia cadastrados (pode ser vazia)."""
        valor = self.buscar_config(_CHAVE_EMAILS_CC)
        if not valor:
            return []
        return sorted({e.strip() for e in valor.split(",") if e.strip()})

    def definir_emails_cc(self, emails: list[str]) -> list[str]:
        """Substitui a lista completa de e-mails em cópia (upsert)."""
        limpo = sorted({e.strip().lower() for e in emails if e.strip()})
        self.salvar_config(
            _CHAVE_EMAILS_CC,
            ",".join(limpo),
            descricao="E-mails que recebem cópia (Cc) do relatório diário.",
        )
        return limpo

    def buscar_config(self, chave: str) -> str | None:
        """Retorna o valor de uma configuração persistida (ou None)."""
        linha = self._client.fetch_one(
            "SELECT config_value FROM agent_config WHERE config_key = ?",
            (chave,),
        )
        return linha["config_value"] if linha else None

    def buscar_todas(self) -> dict[str, str]:
        """Retorna todas as configurações persistidas como dicionário."""
        linhas = self._client.fetch_all(
            "SELECT config_key, config_value FROM agent_config"
        )
        return {l["config_key"]: l["config_value"] for l in linhas}

    def salvar_config(
        self, chave: str, valor: str, descricao: str | None = None
    ) -> None:
        """Insere ou atualiza uma configuração (upsert por config_key)."""
        self._client.execute_query(
            """
            INSERT INTO agent_config (config_key, config_value, description, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(config_key) DO UPDATE SET
                config_value = excluded.config_value,
                description = excluded.description,
                updated_at = excluded.updated_at
            """,
            (chave, valor, descricao, _agora_iso()),
        )


# ----------------------------------------------------------------------
# object_mapping
# ----------------------------------------------------------------------
class ObjectMappingRepository:
    """Operações sobre a tabela ``object_mapping``.

    Usada para configurar de forma flexível as fontes de satisfação e
    cancelamento (que podem estar em objetos diferentes do Salesforce).
    """

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def buscar_mapeamento(self, domain: str) -> dict[str, Any] | None:
        """Retorna o mapeamento ativo de um domínio (ex.: ``satisfaction``).

        Returns:
            Dicionário com ``salesforce_object`` e ``field_mapping`` (dict),
            ou None se não houver mapeamento ativo.
        """
        linha = self._client.fetch_one(
            """
            SELECT salesforce_object, field_mapping_json
              FROM object_mapping
             WHERE domain = ? AND is_active = 1
             ORDER BY id DESC
             LIMIT 1
            """,
            (domain,),
        )
        if not linha:
            return None
        try:
            mapeamento_campos = json.loads(linha["field_mapping_json"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("field_mapping_json inválido para domínio %s.", domain)
            mapeamento_campos = {}
        return {
            "salesforce_object": linha["salesforce_object"],
            "field_mapping": mapeamento_campos,
        }

    def salvar_mapeamento(
        self,
        domain: str,
        salesforce_object: str,
        field_mapping: dict[str, Any],
        is_active: bool = True,
    ) -> None:
        """Salva (ou atualiza) o mapeamento de um objeto customizado.

        Estratégia simples: desativa mapeamentos antigos do domínio e insere
        o novo como ativo, preservando histórico.
        """
        agora = _agora_iso()
        # Desativa mapeamentos anteriores do mesmo domínio.
        self._client.execute_query(
            "UPDATE object_mapping SET is_active = 0, updated_at = ? WHERE domain = ?",
            (agora, domain),
        )
        self._client.execute_query(
            """
            INSERT INTO object_mapping
                (domain, salesforce_object, field_mapping_json, is_active,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                domain,
                salesforce_object,
                json.dumps(field_mapping, ensure_ascii=False),
                1 if is_active else 0,
                agora,
                agora,
            ),
        )
        logger.info("Mapeamento salvo para domínio %s (objeto=%s).", domain, salesforce_object)


# ----------------------------------------------------------------------
# search_cache
# ----------------------------------------------------------------------
class SearchCacheRepository:
    """Operações sobre a tabela ``search_cache``.

    É a camada RÁPIDA do módulo de Consulta (busca híbrida): um espelho
    somente leitura de Account/Opportunity/Contrato/Item de Contrato,
    sincronizado incrementalmente (ver ``src/salesforce/search_sync.py``).
    Quando a busca não encontra nada aqui (ou o dado precisa estar fresco),
    o serviço de consulta cai para o Salesforce ao vivo.
    """

    def __init__(self, client: TursoClient) -> None:
        self._client = client

    def upsert_registros(
        self,
        object_name: str,
        registros: list[dict[str, Any]],
        campo_nome: str = "Name",
        campo_subtitulo: str | None = None,
    ) -> int:
        """Insere ou atualiza um lote de registros no cache de busca.

        Args:
            object_name: Nome da API do objeto (ex.: ``"Account"``).
            registros: Lista de registros (dicionários vindos do Salesforce,
                já sem o atributo ``attributes``).
            campo_nome: Campo usado como nome de exibição (padrão ``Name``).
            campo_subtitulo: Campo opcional usado como subtítulo (ex.: um
                valor monetário ou o nome da conta relacionada).

        Returns:
            Quantidade de registros gravados.
        """
        if not registros:
            return 0
        agora = _agora_iso()
        linhas = [
            (
                object_name,
                str(reg.get("Id", "")),
                str(reg.get(campo_nome) or reg.get("Id") or ""),
                str(reg.get(campo_subtitulo)) if campo_subtitulo and reg.get(campo_subtitulo) is not None else None,
                json.dumps(reg, ensure_ascii=False, default=str),
                agora,
            )
            for reg in registros
            if reg.get("Id")
        ]
        if not linhas:
            return 0
        self._client.execute_many(
            """
            INSERT INTO search_cache
                (object_name, record_id, display_name, subtitle, payload_json, synced_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_name, record_id) DO UPDATE SET
                display_name = excluded.display_name,
                subtitle = excluded.subtitle,
                payload_json = excluded.payload_json,
                synced_at = excluded.synced_at
            """,
            linhas,
        )
        logger.info("Cache de busca atualizado: %d registro(s) de %s.", len(linhas), object_name)
        return len(linhas)

    def buscar(self, object_name: str, termo: str, limite: int = 20) -> list[dict[str, Any]]:
        """Busca no cache por trecho do nome de exibição (case-insensitive).

        Returns:
            Lista de dicionários ``{id, name, subtitle}`` (sem o payload
            completo — use :meth:`buscar_por_id` para o detalhe).
        """
        termo_like = f"%{termo.strip()}%"
        linhas = self._client.fetch_all(
            """
            SELECT record_id, display_name, subtitle
              FROM search_cache
             WHERE object_name = ? AND display_name LIKE ? COLLATE NOCASE
             ORDER BY display_name
             LIMIT ?
            """,
            (object_name, termo_like, int(limite)),
        )
        return [
            {"id": l["record_id"], "name": l["display_name"], "subtitle": l.get("subtitle")}
            for l in linhas
        ]

    def buscar_por_id(self, object_name: str, record_id: str) -> dict[str, Any] | None:
        """Retorna o payload completo cacheado de um registro (ou None)."""
        linha = self._client.fetch_one(
            "SELECT payload_json, synced_at FROM search_cache WHERE object_name = ? AND record_id = ?",
            (object_name, record_id),
        )
        if not linha:
            return None
        try:
            payload = json.loads(linha["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None
        return {"payload": payload, "synced_at": linha.get("synced_at")}

    def contar(self, object_name: str) -> int:
        """Quantidade de registros cacheados de um objeto."""
        linha = self._client.fetch_one(
            "SELECT COUNT(*) AS total FROM search_cache WHERE object_name = ?",
            (object_name,),
        )
        return int(linha["total"]) if linha else 0
