"""Cliente de autenticação no Salesforce (simple-salesforce).

Responsabilidades:
- autenticar no Salesforce usando OAuth 2.0 Refresh Token (método PADRÃO);
- oferecer o login SOAP legado (usuário/senha/token) apenas como fallback;
- retornar um cliente autenticado pronto para executar SOQL;
- operar exclusivamente em modo SOMENTE LEITURA (apenas consultas SOQL);
- tratar erros de autenticação de forma controlada;
- registrar logs SEM expor client_secret, refresh_token, access_token,
  senha ou security token.

Não há regra de negócio aqui — apenas conexão e leitura.

Importante: este módulo NÃO implementa nenhuma operação de escrita
(create/update/delete/upsert/bulk). O único POST permitido é para o
endpoint OAuth de token. Toda leitura passa por ``query_all`` (SOQL).
"""

from __future__ import annotations

from typing import Any

import requests

from ..config import Settings, get_settings
from ..utils.logger import get_logger

logger = get_logger("salesforce.client")


class SalesforceAuthError(RuntimeError):
    """Erro de autenticação/conexão/consulta com o Salesforce."""


# ----------------------------------------------------------------------
# OAuth 2.0 — Refresh Token
# ----------------------------------------------------------------------
def get_oauth_access_token(settings: Settings) -> dict[str, Any]:
    """Obtém um ``access_token`` no Salesforce via OAuth Refresh Token.

    Faz um POST para ``{SALESFORCE_INSTANCE_URL}/services/oauth2/token`` com
    ``grant_type=refresh_token``. Este é o único POST permitido pelo projeto.

    Args:
        settings: Configurações do agente (lê ``settings.salesforce``).

    Returns:
        Dicionário retornado pelo Salesforce, contendo ao menos
        ``access_token`` e ``instance_url``.

    Raises:
        SalesforceAuthError: Se faltar variável obrigatória, houver erro de
            rede ou o Salesforce retornar status diferente de 200.

    Nota de segurança: nem o payload (que contém segredos) nem a resposta
    (que contém o token) são registrados em log.
    """
    sf = settings.salesforce

    # Valida variáveis obrigatórias sem expor seus valores.
    ausentes: list[str] = []
    if not sf.instance_url:
        ausentes.append("SALESFORCE_INSTANCE_URL")
    if not sf.client_id:
        ausentes.append("SALESFORCE_CLIENT_ID")
    if not sf.client_secret:
        ausentes.append("SALESFORCE_CLIENT_SECRET")
    if not sf.refresh_token:
        ausentes.append("SALESFORCE_REFRESH_TOKEN")
    if ausentes:
        raise SalesforceAuthError(
            "Variáveis obrigatórias ausentes para OAuth: " + ", ".join(ausentes)
        )

    token_url = f"{sf.instance_url.rstrip('/')}/services/oauth2/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": sf.client_id,
        "client_secret": sf.client_secret,
        "refresh_token": sf.refresh_token,
    }

    try:
        resposta = requests.post(token_url, data=payload, timeout=30)
    except requests.RequestException as exc:
        # Apenas o tipo do erro — nunca o payload (contém segredos).
        logger.error("Falha de rede ao obter token OAuth: %s", type(exc).__name__)
        raise SalesforceAuthError(
            "Falha de rede ao contatar o endpoint OAuth do Salesforce."
        ) from exc

    if resposta.status_code != 200:
        detalhe = _mensagem_erro_oauth(resposta)
        # Loga apenas o status; o detalhe é sanitizado (sem tokens).
        logger.error("Erro OAuth do Salesforce (status=%s).", resposta.status_code)
        raise SalesforceAuthError(
            f"Erro ao obter access token (status {resposta.status_code}): {detalhe}"
        )

    dados: dict[str, Any] = resposta.json()
    # NÃO logar o conteúdo: contém o access_token.
    if "access_token" not in dados:
        raise SalesforceAuthError("Resposta OAuth inválida: 'access_token' ausente.")
    return dados


def _mensagem_erro_oauth(resposta: requests.Response) -> str:
    """Extrai uma mensagem de erro sanitizada da resposta OAuth.

    Retorna apenas os campos ``error`` e ``error_description`` do Salesforce,
    que não contêm tokens. Nunca retorna o corpo bruto da resposta.
    """
    try:
        dados = resposta.json()
    except ValueError:
        return "resposta inválida do servidor OAuth."
    erro = dados.get("error", "erro_desconhecido")
    descricao = dados.get("error_description", "")
    return f"{erro} — {descricao}".strip(" —")


def _detalhe_erro_salesforce(exc: Exception) -> str:
    """Extrai uma mensagem legível de um erro do simple-salesforce.

    Erros como ``SalesforceMalformedRequest`` expõem ``.content`` (lista de
    dicionários com ``errorCode``/``message``) que descrevem o problema de
    SOQL ou de campo — não contêm credenciais. Útil para diagnóstico.
    """
    conteudo = getattr(exc, "content", None)
    if isinstance(conteudo, list):
        partes: list[str] = []
        for item in conteudo:
            if isinstance(item, dict):
                code = (item.get("errorCode") or "").strip()
                msg = (item.get("message") or "").strip()
                parte = f"{code}: {msg}".strip(": ")
                if parte:
                    partes.append(parte)
        if partes:
            return " | ".join(partes)
    # Fallback: texto do erro, limitado para não poluir o log.
    return str(exc)[:500]


# ----------------------------------------------------------------------
# Proteção somente leitura
# ----------------------------------------------------------------------
def _garantir_consulta_somente_leitura(soql: str) -> None:
    """Garante que a string recebida é uma consulta SOQL de leitura.

    O projeto é read-only: apenas comandos ``SELECT`` são aceitos. Como SOQL
    não possui DML (INSERT/UPDATE/DELETE), esta checagem é uma barreira extra
    e explícita contra qualquer uso indevido.

    Raises:
        SalesforceAuthError: Se a consulta estiver vazia ou não for um SELECT.
    """
    consulta = (soql or "").strip()
    if not consulta:
        raise SalesforceAuthError("Consulta SOQL vazia.")
    primeira_palavra = consulta.lstrip("(").split(None, 1)[0].upper()
    if primeira_palavra != "SELECT":
        raise SalesforceAuthError(
            "Modo somente leitura: apenas consultas SELECT (SOQL) são permitidas."
        )


def execute_soql_query(sf: Any, query: str) -> dict[str, Any]:
    """Executa uma consulta SOQL somente leitura, com paginação automática.

    Esta é a ÚNICA função sancionada para ler dados do Salesforce no projeto.
    Use sempre esta função (ou :meth:`SalesforceClient.query`) para consultar.
    Não existem funções de escrita (create/update/delete/upsert/bulk).

    Args:
        sf: Cliente ``simple_salesforce.Salesforce`` autenticado.
        query: Consulta SOQL (deve começar com ``SELECT``).

    Returns:
        Dicionário de resultado do Salesforce (com a chave ``records``).
    """
    _garantir_consulta_somente_leitura(query)
    return sf.query_all(query)


# ----------------------------------------------------------------------
# Cliente
# ----------------------------------------------------------------------
class SalesforceClient:
    """Encapsula a sessão autenticada do Salesforce (somente leitura).

    Suporta dois modos definidos em ``settings.salesforce.auth_mode``:
    - ``oauth_refresh_token`` (padrão): autentica via OAuth Refresh Token;
    - ``soap_legacy`` (fallback): login SOAP com usuário/senha/token.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicializa o cliente a partir das configurações do agente.

        Args:
            settings: Configurações completas (usa ``settings.salesforce``).
        """
        self._settings = settings
        self._cfg = settings.salesforce
        self._sf: Any | None = None

    @property
    def read_only(self) -> bool:
        """Indica se o cliente opera em modo somente leitura."""
        return self._cfg.read_only_mode

    def connect(self) -> Any:
        """Autentica e retorna o objeto ``Salesforce`` do simple-salesforce.

        Returns:
            Cliente Salesforce autenticado.

        Raises:
            SalesforceAuthError: Em caso de falha de autenticação/import.
        """
        if self._sf is not None:
            return self._sf

        try:
            from simple_salesforce import Salesforce
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise SalesforceAuthError(
                "Biblioteca 'simple-salesforce' não instalada. "
                "Rode: pip install simple-salesforce"
            ) from exc

        if self._cfg.auth_mode == "oauth_refresh_token":
            self._sf = self._conectar_oauth(Salesforce)
        elif self._cfg.auth_mode == "soap_legacy":
            self._sf = self._conectar_soap_legacy(Salesforce)
        else:
            raise SalesforceAuthError(
                f"SALESFORCE_AUTH_MODE inválido: '{self._cfg.auth_mode}'. "
                "Use 'oauth_refresh_token' ou 'soap_legacy'."
            )
        return self._sf

    def _conectar_oauth(self, salesforce_cls: Any) -> Any:
        """Autentica via OAuth Refresh Token (método principal)."""
        token_data = get_oauth_access_token(self._settings)
        access_token = token_data["access_token"]
        # O Salesforce pode devolver a instance_url definitiva no token.
        instance_url = token_data.get("instance_url", self._cfg.instance_url)

        sf = salesforce_cls(
            instance_url=instance_url,
            session_id=access_token,
            version=self._cfg.api_version,
        )
        # Log seguro: instance_url (não é segredo) e versão. Nunca o token.
        logger.info(
            "Autenticado no Salesforce via OAuth (instance_url=%s, version=%s, "
            "read_only=%s).",
            instance_url,
            self._cfg.api_version,
            self._cfg.read_only_mode,
        )
        return sf

    def _conectar_soap_legacy(self, salesforce_cls: Any) -> Any:
        """Autentica via login SOAP legado (fallback).

        Algumas organizações bloqueiam o SOAP ``login()`` em versões recentes
        da API, resultando em ``INVALID_OPERATION``. Nesse caso, orientamos o
        uso do modo OAuth.
        """
        if not (
            self._cfg.username and self._cfg.password and self._cfg.security_token
        ):
            raise SalesforceAuthError(
                "Credenciais legadas incompletas. Verifique o .env "
                "(SALESFORCE_AUTH_MODE=soap_legacy)."
            )

        try:
            sf = salesforce_cls(
                username=self._cfg.username,
                password=self._cfg.password,
                security_token=self._cfg.security_token,
                domain=self._cfg.domain,
                version=self._cfg.api_version,
            )
        except Exception as exc:
            texto = str(exc)
            # Loga apenas o tipo do erro — nunca senha/token.
            logger.error("Falha no login SOAP legado: %s", type(exc).__name__)
            if "INVALID_OPERATION" in texto:
                raise SalesforceAuthError(
                    "SOAP API login() está indisponível nesta organização. "
                    "Use SALESFORCE_AUTH_MODE=oauth_refresh_token."
                ) from exc
            raise SalesforceAuthError(
                "Não foi possível autenticar no Salesforce (soap_legacy)."
            ) from exc

        # Log seguro: apenas usuário (e-mail) e domínio.
        logger.info(
            "Autenticado no Salesforce via SOAP legado (usuário=%s, domínio=%s).",
            self._cfg.username,
            self._cfg.domain,
        )
        return sf

    def query(self, soql: str) -> list[dict[str, Any]]:
        """Executa uma consulta SOQL (somente leitura) com paginação.

        Args:
            soql: Comando SOQL (deve ser um ``SELECT``).

        Returns:
            Lista de registros (sem o atributo de metadados ``attributes``).

        Raises:
            SalesforceAuthError: Em caso de falha de consulta ou comando
                não permitido (não-SELECT).
        """
        sf = self.connect()
        try:
            resultado = execute_soql_query(sf, soql)
        except SalesforceAuthError:
            # Erros já tratados (ex.: consulta não permitida) sobem direto.
            raise
        except Exception as exc:
            # Surface da causa real (ex.: campo inexistente) sem expor segredos.
            detalhe = _detalhe_erro_salesforce(exc)
            logger.error(
                "Erro ao executar SOQL (%s): %s", type(exc).__name__, detalhe
            )
            raise SalesforceAuthError(
                f"Falha ao executar consulta SOQL: {detalhe}"
            ) from exc

        registros = resultado.get("records", [])
        # Remove o campo de metadados que o Salesforce inclui em cada registro.
        for reg in registros:
            reg.pop("attributes", None)
        return registros

    def listar_campos(self, objeto: str) -> set[str]:
        """Retorna o conjunto de nomes de campos existentes em um objeto.

        Usa ``describe()`` (metadados, somente leitura) para descobrir os
        campos reais do objeto na organização. Serve para validar nomes de
        campos customizados antes de montar consultas, evitando SOQL
        malformado por campo inexistente.

        Args:
            objeto: Nome da API do objeto (ex.: ``"Lead"``, ``"Opportunity"``).

        Returns:
            Conjunto com os nomes de campo. Vazio em caso de falha (o chamador
            deve tratar conjunto vazio como "não foi possível validar").
        """
        sf = self.connect()
        try:
            descricao = getattr(sf, objeto).describe()
        except Exception as exc:  # describe não deve quebrar o pipeline
            logger.warning(
                "Não foi possível descrever o objeto %s: %s",
                objeto,
                type(exc).__name__,
            )
            return set()
        campos = descricao.get("fields", []) if isinstance(descricao, dict) else []
        return {campo.get("name", "") for campo in campos if campo.get("name")}


# ----------------------------------------------------------------------
# Fábrica
# ----------------------------------------------------------------------
_cliente_sf: SalesforceClient | None = None


def get_salesforce_client(settings: Settings | None = None) -> SalesforceClient:
    """Retorna um :class:`SalesforceClient` configurado.

    Comportamento:
    - Sem argumento: usa as configurações globais (:func:`get_settings`) e
      mantém um singleton — compatível com o uso atual do agente.
    - Com ``settings``: constrói um cliente novo com essas configurações
      (útil para testes ou execução isolada).

    O cliente resultante autentica via OAuth Refresh Token por padrão
    (``SALESFORCE_AUTH_MODE=oauth_refresh_token``) ao chamar ``.connect()``.

    Args:
        settings: Configurações opcionais do agente.

    Returns:
        Instância de :class:`SalesforceClient`.
    """
    global _cliente_sf
    if settings is not None:
        return SalesforceClient(settings)
    if _cliente_sf is None:
        _cliente_sf = SalesforceClient(get_settings())
    return _cliente_sf
