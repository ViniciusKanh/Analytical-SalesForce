"""Cliente de conexão com o banco Turso/libSQL.

Este módulo é a ÚNICA porta de entrada para o banco. Ele:
- conecta no Turso usando ``libsql`` e as variáveis TURSO_DATABASE_URL /
  TURSO_AUTH_TOKEN;
- nunca imprime credenciais no log;
- expõe ``get_connection``, ``execute_query``, ``execute_many`` e ``fetch_all``.

Importante (separação de responsabilidades): aqui não há regra de negócio.
Apenas execução de SQL parametrizado.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..config import get_settings
from ..utils.logger import get_logger

logger = get_logger("database.turso")

# Tipagem auxiliar para parâmetros de SQL.
Parametros = Sequence[Any]


class TursoClient:
    """Encapsula a conexão e a execução de comandos no Turso/libSQL."""

    def __init__(self, database_url: str, auth_token: str) -> None:
        """Inicializa o cliente.

        Args:
            database_url: URL do banco (TURSO_DATABASE_URL).
            auth_token: Token de autenticação (TURSO_AUTH_TOKEN).

        Observação: a conexão é preguiçosa (lazy) — só é aberta no primeiro uso.
        """
        self._database_url = database_url
        self._auth_token = auth_token
        self._conn: Any | None = None

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------
    def get_connection(self) -> Any:
        """Retorna a conexão ativa, criando-a se necessário.

        Returns:
            Objeto de conexão do ``libsql``.

        Raises:
            RuntimeError: Se a biblioteca ``libsql`` não estiver instalada
                ou se a conexão falhar.
        """
        if self._conn is not None:
            return self._conn

        try:
            import libsql  # import tardio para não exigir a lib em testes unitários
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise RuntimeError(
                "Biblioteca 'libsql' não instalada. Rode: pip install libsql"
            ) from exc

        if not self._database_url:
            raise RuntimeError("TURSO_DATABASE_URL não configurado.")

        try:
            # Bancos remotos exigem auth_token; arquivos locais (file:) não.
            if self._auth_token:
                self._conn = libsql.connect(
                    database=self._database_url, auth_token=self._auth_token
                )
            else:
                self._conn = libsql.connect(database=self._database_url)
            # Log seguro: NÃO registra URL completa nem token.
            logger.info("Conexão com Turso estabelecida.")
        except Exception as exc:
            # Mensagem genérica para não vazar credenciais embutidas na URL.
            logger.error("Falha ao conectar no Turso: %s", type(exc).__name__)
            raise RuntimeError("Não foi possível conectar ao banco Turso.") from exc

        return self._conn

    # ------------------------------------------------------------------
    # Execução de comandos
    # ------------------------------------------------------------------
    def execute_query(self, sql: str, params: Parametros | None = None) -> Any:
        """Executa um comando SQL único (INSERT/UPDATE/DELETE/DDL).

        Args:
            sql: Comando SQL com placeholders ``?``.
            params: Parâmetros do comando.

        Returns:
            O cursor resultante da execução.
        """
        conn = self.get_connection()
        cursor = conn.execute(sql, tuple(params) if params else ())
        conn.commit()
        return cursor

    def execute_many(self, sql: str, seq_params: list[Parametros]) -> None:
        """Executa o mesmo comando para múltiplos conjuntos de parâmetros.

        Args:
            sql: Comando SQL com placeholders ``?``.
            seq_params: Lista de tuplas de parâmetros.
        """
        if not seq_params:
            return
        conn = self.get_connection()
        # executemany quando disponível; senão, itera (compatibilidade).
        if hasattr(conn, "executemany"):
            conn.executemany(sql, [tuple(p) for p in seq_params])
        else:  # pragma: no cover - fallback de compatibilidade
            for p in seq_params:
                conn.execute(sql, tuple(p))
        conn.commit()

    def fetch_all(
        self, sql: str, params: Parametros | None = None
    ) -> list[dict[str, Any]]:
        """Executa um SELECT e retorna todas as linhas como dicionários.

        Args:
            sql: Comando SELECT com placeholders ``?``.
            params: Parâmetros da query.

        Returns:
            Lista de dicionários (coluna -> valor).
        """
        conn = self.get_connection()
        cursor = conn.execute(sql, tuple(params) if params else ())
        linhas = cursor.fetchall()
        # Extrai nomes de coluna de cursor.description (padrão DB-API).
        if cursor.description:
            colunas = [desc[0] for desc in cursor.description]
        else:
            colunas = []
        return [dict(zip(colunas, linha)) for linha in linhas]

    def fetch_one(
        self, sql: str, params: Parametros | None = None
    ) -> dict[str, Any] | None:
        """Executa um SELECT e retorna apenas a primeira linha (ou None)."""
        resultado = self.fetch_all(sql, params)
        return resultado[0] if resultado else None

    def close(self) -> None:
        """Fecha a conexão, se aberta."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # pragma: no cover - best effort
                pass
            finally:
                self._conn = None


# ----------------------------------------------------------------------
# Fábrica com cache simples (singleton por processo)
# ----------------------------------------------------------------------
_cliente_singleton: TursoClient | None = None


def get_turso_client() -> TursoClient:
    """Retorna uma instância única de :class:`TursoClient` para o processo.

    Lê as credenciais a partir das configurações (variáveis de ambiente).
    """
    global _cliente_singleton
    if _cliente_singleton is None:
        settings = get_settings()
        _cliente_singleton = TursoClient(
            database_url=settings.turso.database_url,
            auth_token=settings.turso.auth_token,
        )
    return _cliente_singleton
