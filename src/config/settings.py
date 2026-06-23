"""Módulo de configuração central do Analytical-Force.

Responsabilidades:
- Carregar variáveis de ambiente a partir do arquivo ``.env``.
- Validar configurações de Salesforce, Turso e provider de modelo.
- Permitir o modo ``template`` quando não houver modelo de IA configurado.
- Expor a classe :class:`Settings` com type hints.
- Nunca imprimir segredos no console/log.

Regra crítica do projeto: o agente NÃO depende de APIs comerciais pagas
(OpenAI, Anthropic, Groq, Gemini etc.). Apenas modelos locais/públicos são
suportados: ``template`` (sem IA), ``ollama`` (local) e ``transformers``
(Hugging Face público).

Princípio: este módulo apenas lê e valida configuração. Ele NÃO acessa
Salesforce, Turso ou qualquer serviço externo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

# Carrega o arquivo .env (se existir) para dentro de os.environ.
# `override=False` garante que variáveis já presentes no ambiente
# (ex.: GitHub Actions Secrets) tenham prioridade sobre o .env local.
load_dotenv(override=False)


# Provedores de modelo suportados pelo agente.
# Apenas modelos locais/públicos gratuitos — sem APIs comerciais pagas.
PROVEDORES_MODELO_VALIDOS: tuple[str, ...] = (
    "template",       # Relatório por regras/template, sem IA. Sempre funciona.
    "ollama",         # Modelo local via API HTTP do Ollama.
    "transformers",   # Modelo público via Hugging Face Transformers (CPU local).
    "hf_inference",   # Modelo hospedado via Hugging Face Inference Providers.
)

# Modos de autenticação do Salesforce suportados.
#   oauth_refresh_token -> OAuth 2.0 Refresh Token (padrão, recomendado).
#   soap_legacy         -> login() SOAP com usuário/senha/token (fallback).
SALESFORCE_AUTH_MODES_VALIDOS: tuple[str, ...] = (
    "oauth_refresh_token",
    "soap_legacy",
)


def _get_str(nome: str, padrao: str = "") -> str:
    """Lê uma variável de ambiente como string, com valor padrão.

    Args:
        nome: Nome da variável de ambiente.
        padrao: Valor padrão caso a variável não exista.

    Returns:
        Valor da variável (com espaços nas pontas removidos).
    """
    valor = os.environ.get(nome, padrao)
    return valor.strip() if isinstance(valor, str) else padrao


def _get_int(nome: str, padrao: int) -> int:
    """Lê uma variável de ambiente como inteiro, tolerando valores inválidos."""
    bruto = _get_str(nome)
    if not bruto:
        return padrao
    try:
        return int(bruto)
    except ValueError:
        return padrao


def _get_float(nome: str, padrao: float) -> float:
    """Lê uma variável de ambiente como float, tolerando valores inválidos."""
    bruto = _get_str(nome)
    if not bruto:
        return padrao
    try:
        return float(bruto)
    except ValueError:
        return padrao


def _get_bool(nome: str, padrao: bool) -> bool:
    """Lê uma variável de ambiente como booleano.

    Considera verdadeiros: ``1, true, yes, sim, on`` (case-insensitive).
    """
    bruto = _get_str(nome)
    if not bruto:
        return padrao
    return bruto.strip().lower() in {"1", "true", "yes", "sim", "on"}


def _normalizar_turso_url(url: str) -> str:
    """Normaliza a URL do Turso, tolerando erros comuns de digitação.

    Corrige casos como aspas acidentais, esquema escrito errado
    (ex.: ``ibsql://`` em vez de ``libsql://``) ou ausência de esquema em um
    host ``*.turso.io``. Não altera URLs já válidas (libsql/https/file/...).

    Args:
        url: Valor bruto de ``TURSO_DATABASE_URL``.

    Returns:
        URL normalizada (ou a original quando não há correção segura).
    """
    u = (url or "").strip().strip('"').strip("'")
    if not u:
        return u
    esquemas_ok = ("libsql://", "https://", "http://", "wss://", "ws://", "file:")
    if u.startswith(esquemas_ok):
        return u
    # Sem esquema reconhecido: extrai o "resto" após um eventual "://".
    resto = u.partition("://")[2] if "://" in u else u
    # Se aparenta ser um banco Turso remoto, força o esquema libsql.
    if "turso.io" in resto.lower():
        return "libsql://" + resto
    return u


@dataclass(frozen=True)
class SalesforceSettings:
    """Configurações de conexão com o Salesforce.

    Suporta dois modos de autenticação:
    - ``oauth_refresh_token`` (padrão): usa OAuth 2.0 com Refresh Token.
    - ``soap_legacy`` (fallback): usa usuário/senha/security token (SOAP login).

    Em qualquer modo, o agente opera apenas em leitura (SOQL).
    """

    # Modo de autenticação e parâmetros gerais.
    auth_mode: str = "oauth_refresh_token"
    api_version: str = "64.0"
    read_only_mode: bool = True

    # OAuth 2.0 Refresh Token (método principal).
    instance_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""

    # Credenciais legadas (somente usadas em soap_legacy).
    username: str = ""
    password: str = ""
    security_token: str = ""
    domain: str = "login"

    @property
    def is_oauth(self) -> bool:
        """True quando o modo de autenticação é OAuth Refresh Token."""
        return self.auth_mode == "oauth_refresh_token"

    @property
    def is_configured(self) -> bool:
        """Indica se há credenciais mínimas para autenticar no Salesforce.

        A verificação depende do modo de autenticação ativo.
        """
        if self.auth_mode == "oauth_refresh_token":
            return bool(
                self.instance_url
                and self.client_id
                and self.client_secret
                and self.refresh_token
            )
        if self.auth_mode == "soap_legacy":
            return bool(self.username and self.password and self.security_token)
        return False


@dataclass(frozen=True)
class TursoSettings:
    """Configurações de conexão com o banco Turso/libSQL."""

    database_url: str
    auth_token: str

    @property
    def is_configured(self) -> bool:
        """Indica se há dados mínimos para conectar ao Turso.

        Observação: bancos locais embarcados (arquivo) podem dispensar token,
        mas o banco principal de produção (Turso remoto) exige ambos.
        """
        return bool(self.database_url)


@dataclass(frozen=True)
class ModelSettings:
    """Configurações do provider de modelo (interpretação do relatório).

    Apenas modelos locais/públicos são suportados. Nenhuma chave de API
    comercial é lida ou exigida.
    """

    provider: str = "template"
    enable_ai_interpretation: bool = True
    # Ollama local (provider padrão).
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    # Hugging Face Transformers (opcional). Sem modelo fixo no código.
    hf_model_repo_id: str = ""
    hf_device: str = "cpu"
    # Limite de tokens gerados. Menor = mais rápido (sobretudo em CPU).
    hf_max_new_tokens: int = 320
    # Hugging Face Inference Providers (modelo hospedado, rápido e online).
    hf_inference_model: str = ""
    hf_inference_provider: str = ""  # vazio = roteamento automático da HF
    hf_token: str = ""

    @property
    def is_template_mode(self) -> bool:
        """True quando o relatório é gerado sem chamar modelo de IA."""
        return self.provider == "template"

    @property
    def usa_ia(self) -> bool:
        """True quando há intenção de usar um modelo de IA (não-template)."""
        return self.enable_ai_interpretation and self.provider != "template"


@dataclass(frozen=True)
class RiskSettings:
    """Limiares configuráveis usados pelo motor de risco."""

    lead_max_hours_without_task: int = 24
    opportunity_max_days_without_activity: int = 7
    conversion_drop_threshold_percent: float = 20.0
    pipeline_drop_threshold_percent: float = 15.0
    lead_first_task_target_hours: float = 8.0
    overdue_tasks_owner_threshold: int = 5
    high_value_opportunity_amount: float = 50000.0
    # Valor mínimo de oportunidade a considerar na análise de pipeline/risco.
    # 0 = analisa todas. Use para ignorar oportunidades de baixo valor.
    opportunity_min_amount: float = 0.0
    satisfaction_min_score: float = 7.0


@dataclass(frozen=True)
class EmailSettings:
    """Configurações de envio de e-mail (SMTP). Opcional."""

    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_password: str = ""
    recipient_email: str = ""
    # Gmail API (HTTP/OAuth) — envia por HTTPS, funcionando onde o SMTP é
    # bloqueado (ex.: Hugging Face Spaces). Preferido quando configurado.
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""
    gmail_sender: str = ""

    @property
    def gmail_api_configured(self) -> bool:
        """Indica se há credenciais para enviar via Gmail API (HTTP)."""
        return bool(
            self.gmail_client_id
            and self.gmail_client_secret
            and self.gmail_refresh_token
            and self.recipient_email
        )

    @property
    def smtp_configured(self) -> bool:
        """Indica se há dados mínimos para enviar via SMTP."""
        return bool(self.smtp_host and self.smtp_port and self.recipient_email)

    @property
    def is_configured(self) -> bool:
        """Indica se há ALGUM método de envio configurado (Gmail API ou SMTP)."""
        return self.gmail_api_configured or self.smtp_configured


@dataclass(frozen=True)
class ClickUpSettings:
    """Configurações da integração opcional com ClickUp."""

    api_token: str = ""
    list_id: str = ""
    auto_create: bool = False
    # Responsável (assignee) das tarefas criadas. Pode-se informar o ID numérico
    # do usuário (preferencial) ou o e-mail (resolvido via API da lista).
    assignee_id: str = ""
    assignee_email: str = ""
    # Gera um plano de ação por IA (Ollama) na descrição da tarefa, quando
    # houver provider de IA ativo. Com fallback para descrição só com dados.
    ai_tasks: bool = True

    @property
    def is_configured(self) -> bool:
        """Indica se há dados mínimos para usar a API do ClickUp."""
        return bool(self.api_token and self.list_id)


@dataclass(frozen=True)
class Settings:
    """Agregador de todas as configurações do agente.

    Esta classe é imutável (``frozen=True``) e deve ser obtida via
    :func:`get_settings`, que aplica cache.
    """

    salesforce: SalesforceSettings
    turso: TursoSettings
    model: ModelSettings
    risk: RiskSettings
    email: EmailSettings
    clickup: ClickUpSettings
    report_timezone: str = "America/Sao_Paulo"
    custom_fields: dict[str, str] = field(default_factory=dict)
    # Fontes configuráveis de Satisfação e Cancelamento (objeto + campos).
    # Permitem ativar esses módulos sem fixar nomes no código (regra 16/17).
    satisfaction_source: dict[str, Any] = field(default_factory=dict)
    cancellation_source: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validações
    # ------------------------------------------------------------------
    def validar_salesforce(self) -> list[str]:
        """Valida configuração do Salesforce conforme o modo de autenticação.

        Returns:
            Lista de mensagens de erro (vazia quando válido).
        """
        erros: list[str] = []
        sf = self.salesforce

        if sf.auth_mode not in SALESFORCE_AUTH_MODES_VALIDOS:
            erros.append(
                f"SALESFORCE_AUTH_MODE inválido: '{sf.auth_mode}'. "
                f"Use um de: {', '.join(SALESFORCE_AUTH_MODES_VALIDOS)}."
            )
            return erros

        if sf.auth_mode == "oauth_refresh_token":
            # Modo principal: exige instance_url + credenciais OAuth.
            if not sf.instance_url:
                erros.append("SALESFORCE_INSTANCE_URL não configurado.")
            if not sf.client_id:
                erros.append("SALESFORCE_CLIENT_ID não configurado.")
            if not sf.client_secret:
                erros.append("SALESFORCE_CLIENT_SECRET não configurado.")
            if not sf.refresh_token:
                erros.append("SALESFORCE_REFRESH_TOKEN não configurado.")
        else:  # soap_legacy
            if not sf.username:
                erros.append("SALESFORCE_USERNAME não configurado.")
            if not sf.password:
                erros.append("SALESFORCE_PASSWORD não configurado.")
            if not sf.security_token:
                erros.append("SALESFORCE_SECURITY_TOKEN não configurado.")
        return erros

    def validar_turso(self) -> list[str]:
        """Valida configuração do Turso (banco principal)."""
        erros: list[str] = []
        if not self.turso.database_url:
            erros.append("TURSO_DATABASE_URL não configurado.")
        # Token é obrigatório para Turso remoto; bancos locais (file:) o dispensam.
        url = self.turso.database_url
        eh_remoto = url.startswith("libsql://") or url.startswith("https://")
        if eh_remoto and not self.turso.auth_token:
            erros.append("TURSO_AUTH_TOKEN não configurado para banco remoto.")
        return erros

    def validar_modelo(self) -> list[str]:
        """Valida configuração do provider de modelo.

        Aceita somente ``template``, ``ollama`` ou ``transformers``.
        Nenhuma chave de API comercial é exigida.
        """
        erros: list[str] = []
        provider = self.model.provider
        if provider not in PROVEDORES_MODELO_VALIDOS:
            erros.append(
                f"MODEL_PROVIDER inválido: '{provider}'. "
                f"Use um de: {', '.join(PROVEDORES_MODELO_VALIDOS)}."
            )
            return erros

        # Modo template não exige nada além do código (sempre funciona).
        if provider == "ollama" and not self.model.ollama_base_url:
            erros.append("OLLAMA_BASE_URL não configurado para provider ollama.")
        elif provider == "transformers" and not self.model.hf_model_repo_id:
            erros.append(
                "HF_MODEL_REPO_ID não configurado para provider transformers."
            )
        elif provider == "hf_inference":
            if not self.model.hf_token:
                erros.append("HF_TOKEN não configurado para provider hf_inference.")
            if not self.model.hf_inference_model:
                erros.append(
                    "HF_INFERENCE_MODEL não configurado para provider hf_inference."
                )
        return erros

    def validar_tudo(self) -> dict[str, list[str]]:
        """Executa todas as validações e retorna um relatório consolidado.

        Returns:
            Dicionário com listas de erros por área. Áreas sem erro têm lista vazia.
        """
        return {
            "salesforce": self.validar_salesforce(),
            "turso": self.validar_turso(),
            "modelo": self.validar_modelo(),
        }

    def resumo_seguro(self) -> dict[str, object]:
        """Resumo de configuração SEM expor segredos.

        Útil para registrar em log no início da execução.
        """
        return {
            "salesforce_configurado": self.salesforce.is_configured,
            "salesforce_auth_mode": self.salesforce.auth_mode,
            # instance_url e domínio não são segredos; tokens NUNCA são expostos.
            "salesforce_instance_url": self.salesforce.instance_url,
            "salesforce_domain": self.salesforce.domain,
            "salesforce_read_only": self.salesforce.read_only_mode,
            "turso_configurado": self.turso.is_configured,
            "model_provider": self.model.provider,
            "ai_interpretation": self.model.enable_ai_interpretation,
            "email_configurado": self.email.is_configured,
            "clickup_configurado": self.clickup.is_configured,
            "report_timezone": self.report_timezone,
        }


def _carregar_campos_customizados() -> dict[str, str]:
    """Carrega mapeamento de campos customizados padrão do Salesforce.

    Permite sobrescrever via variável de ambiente (ex.: SF_FIELD_FIRST_TASK).
    Os valores padrão usam os nomes reais da org Penso; campos inexistentes em
    outra org são ignorados automaticamente (validação por ``describe``).
    """
    return {
        # Campo do Lead que indica a primeira tarefa registrada.
        "lead_first_task": _get_str("SF_FIELD_FIRST_TASK", "FirstTask__c"),
        # Campos customizados de Opportunity (nomes reais da org).
        "opp_motivo_perda": _get_str("SF_FIELD_OPP_MOTIVO_PERDA", "Motivo_Perda_ganho__c"),
        # Origem da oportunidade: usa o campo padrão LeadSource (vazio = não custom).
        "opp_origem": _get_str("SF_FIELD_OPP_ORIGEM", ""),
        "opp_tipo_venda": _get_str("SF_FIELD_OPP_TIPO_VENDA", "Tipo_venda__c"),
        "opp_produto": _get_str("SF_FIELD_OPP_PRODUTO", "ProdutoPrincipal__c"),
        # Campos adicionais úteis (próxima ação, dias sem atividade, GC, valor).
        "opp_proxima_acao": _get_str("SF_FIELD_OPP_PROXIMA_ACAO", "Proxima_acao__c"),
        "opp_dias_sem_atividade": _get_str(
            "SF_FIELD_OPP_DIAS_SEM_ATIVIDADE", "OppDiasSemAtividade__c"
        ),
        "opp_gc_nome": _get_str("SF_FIELD_OPP_GC_NOME", "GC_Nome__c"),
        "opp_valor_mensal": _get_str("SF_FIELD_OPP_VALOR_MENSAL", "Valor_Liquido_Mensal__c"),
    }


def _carregar_fonte_satisfacao() -> dict[str, Any]:
    """Monta a configuração da fonte de Satisfação (objeto + campos).

    Padrões alinhados ao objeto ``Satisfacao__c`` da org Penso. Como o campo
    de sentimento é categórico, o extrator deriva uma nota numérica na coluna
    ``SentimentScore`` (Verde=10, Amarelo=5, Vermelho=0), usada como ``score``.
    """
    sentimento = _get_str("SF_SAT_SENTIMENT_FIELD", "Sentimento__c")
    return {
        "object": _get_str("SF_SAT_OBJECT", "Satisfacao__c"),
        "date_field": _get_str("SF_SAT_DATE_FIELD", "Reply_Date__c"),
        "sentiment_field": sentimento,
        "fields": [
            "Id",
            "Name",
            "Conta_Nome__c",
            sentimento,
            "Sentimento_Nivel__c",
            "CreatedDate",
            "LastModifiedDate",
            "Area_insatisfacao__c",
            "area_de_insatisfacao_motivador__c",
            "Motivador__c",
            "Motivador_Outros__c",
            "Resumo__c",
            "Ticket_Atual__c",
            "Owner_Nome__c",
            "Gerente_Comercial__c",
            "Tipo_de_Pesquisa__c",
            "Status__c",
            "Tier__c",
        ],
        "field_mapping": {
            # Coluna numérica derivada do sentimento (criada no extrator).
            "score": "SentimentScore",
            "reason": _get_str("SF_SAT_REASON_FIELD", "area_de_insatisfacao_motivador__c"),
            "comment": _get_str("SF_SAT_COMMENT_FIELD", "Resumo__c"),
            "negative_threshold": _get_float("SF_SAT_NEGATIVE_THRESHOLD", 5.0),
        },
        # Escala de conversão do sentimento (chave = trecho em minúsculas).
        "sentiment_scale": {"verde": 10.0, "amarelo": 5.0, "vermelho": 0.0},
    }


def _carregar_fonte_cancelamento() -> dict[str, Any]:
    """Monta a configuração da fonte de Cancelamento (objeto + campos).

    Padrão: oportunidades com data de cancelamento no dia (``DATA_CANCELAMENTO__c``).
    O impacto em MRR usa o valor líquido mensal; ARR é derivado (×12) na métrica.
    """
    return {
        "object": _get_str("SF_CANC_OBJECT", "Opportunity"),
        "date_field": _get_str("SF_CANC_DATE_FIELD", "DATA_CANCELAMENTO__c"),
        "fields": [
            "Id",
            "Name",
            "Conta_Raz_o_Social__c",
            "Conta_CNPJ__c",
            "DATA_CANCELAMENTO__c",
            "VALOR_CANCELADO__c",
            "Valor_Liquido_Mensal__c",
            "Valor_Cancelado_12_Meses__c",
            "Motivo_Cancelamento__c",
            "Tipo_Cancelamento__c",
            "ProdutoPrincipal__c",
            "GC_Nome__c",
            "OwnerId",
            "StageName",
        ],
        "field_mapping": {
            "mrr": _get_str("SF_CANC_MRR_FIELD", "Valor_Liquido_Mensal__c"),
            "reason": _get_str("SF_CANC_REASON_FIELD", "Motivo_Cancelamento__c"),
            "product": _get_str("SF_CANC_PRODUCT_FIELD", "ProdutoPrincipal__c"),
            "owner": _get_str("SF_CANC_OWNER_FIELD", "GC_Nome__c"),
        },
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Constrói (uma única vez) e retorna as configurações do agente.

    O resultado é cacheado para evitar releitura do ambiente a cada chamada.

    Returns:
        Instância imutável de :class:`Settings`.
    """
    salesforce = SalesforceSettings(
        # Modo padrão = OAuth Refresh Token (recomendado).
        auth_mode=(
            _get_str("SALESFORCE_AUTH_MODE", "oauth_refresh_token")
            or "oauth_refresh_token"
        ).lower(),
        api_version=_get_str("SALESFORCE_API_VERSION", "64.0") or "64.0",
        read_only_mode=_get_bool("SALESFORCE_READ_ONLY_MODE", True),
        # OAuth Refresh Token.
        instance_url=_get_str("SALESFORCE_INSTANCE_URL").rstrip("/"),
        client_id=_get_str("SALESFORCE_CLIENT_ID"),
        client_secret=_get_str("SALESFORCE_CLIENT_SECRET"),
        refresh_token=_get_str("SALESFORCE_REFRESH_TOKEN"),
        # Credenciais legadas (fallback soap_legacy).
        username=_get_str("SALESFORCE_USERNAME"),
        password=_get_str("SALESFORCE_PASSWORD"),
        security_token=_get_str("SALESFORCE_SECURITY_TOKEN"),
        domain=_get_str("SALESFORCE_DOMAIN", "login") or "login",
    )

    turso = TursoSettings(
        database_url=_normalizar_turso_url(_get_str("TURSO_DATABASE_URL")),
        auth_token=_get_str("TURSO_AUTH_TOKEN"),
    )

    model = ModelSettings(
        # Padrão "template" garante MVP funcional sem nenhum modelo instalado.
        provider=(_get_str("MODEL_PROVIDER", "template") or "template").lower(),
        enable_ai_interpretation=_get_bool("ENABLE_AI_INTERPRETATION", True),
        ollama_base_url=_get_str("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=_get_str("OLLAMA_MODEL", "llama3.1:8b"),
        hf_model_repo_id=_get_str("HF_MODEL_REPO_ID"),
        hf_device=_get_str("HF_DEVICE", "cpu") or "cpu",
        hf_max_new_tokens=_get_int("HF_MAX_NEW_TOKENS", 320),
        hf_inference_model=_get_str("HF_INFERENCE_MODEL"),
        hf_inference_provider=_get_str("HF_INFERENCE_PROVIDER"),
        hf_token=_get_str("HF_TOKEN"),
    )

    risk = RiskSettings(
        lead_max_hours_without_task=_get_int("LEAD_MAX_HOURS_WITHOUT_TASK", 24),
        opportunity_max_days_without_activity=_get_int(
            "OPPORTUNITY_MAX_DAYS_WITHOUT_ACTIVITY", 7
        ),
        conversion_drop_threshold_percent=_get_float(
            "CONVERSION_DROP_THRESHOLD_PERCENT", 20.0
        ),
        pipeline_drop_threshold_percent=_get_float(
            "PIPELINE_DROP_THRESHOLD_PERCENT", 15.0
        ),
        lead_first_task_target_hours=_get_float("LEAD_FIRST_TASK_TARGET_HOURS", 8.0),
        overdue_tasks_owner_threshold=_get_int("OVERDUE_TASKS_OWNER_THRESHOLD", 5),
        high_value_opportunity_amount=_get_float(
            "HIGH_VALUE_OPPORTUNITY_AMOUNT", 50000.0
        ),
        opportunity_min_amount=_get_float("OPPORTUNITY_MIN_AMOUNT", 0.0),
        satisfaction_min_score=_get_float("SATISFACTION_MIN_SCORE", 7.0),
    )

    email = EmailSettings(
        smtp_host=_get_str("SMTP_HOST"),
        smtp_port=_get_int("SMTP_PORT", 0),
        smtp_user=_get_str("SMTP_USER"),
        smtp_password=_get_str("SMTP_PASSWORD"),
        recipient_email=_get_str("REPORT_RECIPIENT_EMAIL"),
        gmail_client_id=_get_str("GMAIL_CLIENT_ID"),
        gmail_client_secret=_get_str("GMAIL_CLIENT_SECRET"),
        gmail_refresh_token=_get_str("GMAIL_REFRESH_TOKEN"),
        gmail_sender=_get_str("GMAIL_SENDER"),
    )

    clickup = ClickUpSettings(
        # Remove aspas acidentais coladas no valor (causa comum de 401 no ClickUp).
        api_token=_get_str("CLICKUP_API_TOKEN").strip('"').strip("'"),
        list_id=_get_str("CLICKUP_LIST_ID").strip('"').strip("'"),
        auto_create=_get_bool("ENABLE_CLICKUP_AUTO_CREATE", False),
        assignee_id=_get_str("CLICKUP_ASSIGNEE_ID"),
        assignee_email=_get_str("CLICKUP_ASSIGNEE_EMAIL"),
        ai_tasks=_get_bool("CLICKUP_AI_TASKS", True),
    )

    return Settings(
        salesforce=salesforce,
        turso=turso,
        model=model,
        risk=risk,
        email=email,
        clickup=clickup,
        report_timezone=_get_str("REPORT_TIMEZONE", "America/Sao_Paulo")
        or "America/Sao_Paulo",
        custom_fields=_carregar_campos_customizados(),
        satisfaction_source=_carregar_fonte_satisfacao(),
        cancellation_source=_carregar_fonte_cancelamento(),
    )
