"""Extratores de dados do Salesforce.

Responsabilidades:
- executar as queries SOQL (via :class:`SalesforceClient`);
- converter a resposta em DataFrames pandas;
- tratar resultado vazio (retornando DataFrame com colunas esperadas);
- padronizar campos de data para o timezone do projeto;
- opcionalmente salvar o snapshot bruto no Turso.

Esta camada NÃO calcula indicadores e NÃO gera relatório.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any

import pandas as pd

from . import queries
from .client import SalesforceClient
from .field_mapping import FieldMapping
from ..database.repositories import SnapshotRepository
from ..utils.date_utils import (
    intervalo_do_dia,
    para_soql_date,
    para_soql_datetime,
)
from ..utils.logger import get_logger

logger = get_logger("salesforce.extractors")

# Colunas de data por objeto, para normalização de timezone.
_COLUNAS_DATA = [
    "CreatedDate",
    "LastModifiedDate",
    "ConvertedDate",
    "CloseDate",
    "ActivityDate",
]


class SalesforceExtractor:
    """Orquestra a extração dos objetos do Salesforce em DataFrames."""

    def __init__(
        self,
        client: SalesforceClient,
        field_mapping: FieldMapping,
        timezone: str = "America/Sao_Paulo",
        snapshot_repo: SnapshotRepository | None = None,
        ignore_lead_names: list[str] | None = None,
    ) -> None:
        """Inicializa o extrator.

        Args:
            client: Cliente Salesforce autenticado.
            field_mapping: Mapeamento de campos customizados.
            timezone: Fuso para normalização das datas.
            snapshot_repo: Repositório opcional para salvar payload bruto.
        """
        self._client = client
        # Cache de campos por objeto (describe), para validar nomes uma vez só.
        self._cache_campos: dict[str, set[str]] = {}
        # Valida os campos customizados contra o schema real da org, evitando
        # SOQL malformado por campo inexistente (ex.: nomes padrão genéricos).
        self._fm = self._validar_campos_customizados(field_mapping)
        self._tz = timezone
        self._snapshot_repo = snapshot_repo
        self._ignore_lead_names = [n for n in (ignore_lead_names or []) if n]

    def _filtrar_leads_ignorados(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove leads de teste (nome contém algum trecho configurado p/ ignorar)."""
        if df.empty or not self._ignore_lead_names or "Name" not in df.columns:
            return df
        nomes = df["Name"].astype(str).str.lower()
        manter = ~nomes.apply(lambda n: any(t in n for t in self._ignore_lead_names))
        removidos = int((~manter).sum())
        if removidos:
            logger.info("Leads de teste ignorados: %d.", removidos)
        return df[manter]

    # ------------------------------------------------------------------
    # Validação de campos contra o schema (describe, somente leitura)
    # ------------------------------------------------------------------
    def _campos_objeto(self, objeto: str) -> set[str]:
        """Retorna (com cache) os nomes de campo existentes em um objeto."""
        if objeto not in self._cache_campos:
            self._cache_campos[objeto] = self._client.listar_campos(objeto)
        return self._cache_campos[objeto]

    def _campos_validos(self, objeto: str, campos: list[str]) -> list[str]:
        """Filtra uma lista de campos, mantendo só os que existem no objeto.

        Remove duplicatas preservando a ordem. Campos de relacionamento
        (com ``.``) são mantidos sem validação. Se o ``describe`` falhar
        (conjunto vazio), mantém todos os campos (fallback seguro).
        """
        disponiveis = self._campos_objeto(objeto)
        resultado: list[str] = []
        for campo in campos:
            if not campo or campo in resultado:
                continue
            if "." in campo:  # campo de relacionamento (ex.: Account.Name)
                resultado.append(campo)
                continue
            if disponiveis and campo not in disponiveis:
                logger.warning(
                    "Campo ignorado em %s (não existe na org): %s.", objeto, campo
                )
                continue
            resultado.append(campo)
        return resultado

    def _validar_campos_customizados(self, fm: FieldMapping) -> FieldMapping:
        """Desativa campos customizados que não existem na organização.

        Usa ``describe()`` (somente leitura) para listar os campos reais de
        Lead e Opportunity. Campos configurados que não existem são desativados
        (substituídos por ``""``) e registrados em log — assim a consulta não
        falha com ``INVALID_FIELD`` por causa de nomes que a org não possui.

        Fallback seguro: se o ``describe`` falhar (conjunto vazio), mantém os
        campos como estão e deixa eventual erro de consulta ser reportado.
        """
        campos_lead = self._campos_objeto("Lead")
        campos_opp = self._campos_objeto("Opportunity")

        def _validar(nome: str, disponiveis: set[str]) -> str:
            if not nome:
                return ""
            # Sem describe (conjunto vazio) não há como validar: mantém o nome.
            if disponiveis and nome not in disponiveis:
                logger.warning(
                    "Campo customizado ignorado (não existe na org): %s.", nome
                )
                return ""
            return nome

        return replace(
            fm,
            lead_first_task=_validar(fm.lead_first_task, campos_lead),
            opp_motivo_perda=_validar(fm.opp_motivo_perda, campos_opp),
            opp_origem=_validar(fm.opp_origem, campos_opp),
            opp_tipo_venda=_validar(fm.opp_tipo_venda, campos_opp),
            opp_produto=_validar(fm.opp_produto, campos_opp),
            opp_proxima_acao=_validar(fm.opp_proxima_acao, campos_opp),
            opp_dias_sem_atividade=_validar(fm.opp_dias_sem_atividade, campos_opp),
            opp_gc_nome=_validar(fm.opp_gc_nome, campos_opp),
            opp_valor_mensal=_validar(fm.opp_valor_mensal, campos_opp),
            opp_valor_mensal_produtos=_validar(fm.opp_valor_mensal_produtos, campos_opp),
            opp_valor_pontual_produtos=_validar(fm.opp_valor_pontual_produtos, campos_opp),
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------
    def _para_dataframe(
        self,
        registros: list[dict[str, Any]],
        colunas_esperadas: list[str],
    ) -> pd.DataFrame:
        """Converte registros em DataFrame, tratando lista vazia.

        Args:
            registros: Lista de dicionários vinda do Salesforce.
            colunas_esperadas: Colunas garantidas mesmo se vazio.

        Returns:
            DataFrame com datas normalizadas ao timezone do projeto.
        """
        if not registros:
            # DataFrame vazio mas com colunas, para os motores de métrica não quebrarem.
            return pd.DataFrame(columns=colunas_esperadas)

        df = pd.DataFrame(registros)
        # Normaliza colunas de data presentes.
        for coluna in _COLUNAS_DATA:
            if coluna in df.columns:
                df[coluna] = self._normalizar_datas(df[coluna])
        return df

    def _normalizar_datas(self, serie: pd.Series) -> pd.Series:
        """Converte uma série de datas para o timezone do projeto.

        Datas-only (ActivityDate/CloseDate) ficam sem timezone (apenas data).
        Datetimes com offset são convertidos para o fuso configurado.
        """
        convertido = pd.to_datetime(serie, errors="coerce", utc=True)
        try:
            return convertido.dt.tz_convert(self._tz)
        except (TypeError, AttributeError):
            # Série sem timezone (datas puras) — retorna como datetime simples.
            return convertido

    def _salvar_snapshot(
        self, dia: date, objeto: str, registros: list[dict[str, Any]]
    ) -> None:
        """Salva snapshot bruto no Turso, se o repositório estiver disponível."""
        if self._snapshot_repo is not None and registros:
            try:
                self._snapshot_repo.salvar_snapshots(dia, objeto, registros)
            except Exception as exc:  # snapshot não deve quebrar a extração
                logger.warning("Falha ao salvar snapshot de %s: %s", objeto, type(exc).__name__)

    # ------------------------------------------------------------------
    # Extração — Leads
    # ------------------------------------------------------------------
    def extrair_leads_criados(self, dia: date) -> pd.DataFrame:
        """Extrai leads criados no dia informado."""
        inicio, fim = intervalo_do_dia(dia, self._tz)
        soql = queries.leads_criados(
            para_soql_datetime(inicio), para_soql_datetime(fim), self._fm
        )
        registros = self._client.query(soql)
        self._salvar_snapshot(dia, "Lead", registros)
        logger.info("Leads criados extraídos: %d.", len(registros))
        colunas = _colunas_lead(self._fm)
        return self._filtrar_leads_ignorados(self._para_dataframe(registros, colunas))

    def extrair_leads_modificados(self, dia: date) -> pd.DataFrame:
        """Extrai leads modificados no dia informado."""
        inicio, fim = intervalo_do_dia(dia, self._tz)
        soql = queries.leads_modificados(
            para_soql_datetime(inicio), para_soql_datetime(fim), self._fm
        )
        registros = self._client.query(soql)
        logger.info("Leads modificados extraídos: %d.", len(registros))
        colunas = _colunas_lead(self._fm)
        return self._filtrar_leads_ignorados(self._para_dataframe(registros, colunas))

    # ------------------------------------------------------------------
    # Extração — Oportunidades
    # ------------------------------------------------------------------
    def extrair_oportunidades_abertas(self, dia: date) -> pd.DataFrame:
        """Extrai todas as oportunidades abertas (com coluna ValorProdutos)."""
        soql = queries.oportunidades_abertas(self._fm)
        registros = self._client.query(soql)
        self._salvar_snapshot(dia, "Opportunity", registros)
        logger.info("Oportunidades abertas extraídas: %d.", len(registros))
        colunas = _colunas_opp(self._fm)
        return self._adicionar_valor_produtos(self._para_dataframe(registros, colunas))

    def _adicionar_valor_produtos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cria a coluna ``ValorProdutos`` = recorrente + pontual dos produtos.

        Usa os campos configurados (``Valor_Mensal_Produtos__c`` +
        ``Valor_Pontual_Produtos__c``). Se nenhum existir na org, não cria a
        coluna (o cálculo cai para ``Amount``).
        """
        if df.empty:
            return df
        cols = [
            c
            for c in [self._fm.opp_valor_mensal_produtos, self._fm.opp_valor_pontual_produtos]
            if c and c in df.columns
        ]
        if not cols:
            return df
        df = df.copy()
        soma = None
        for c in cols:
            v = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
            soma = v if soma is None else soma + v
        df["ValorProdutos"] = soma
        return df

    def extrair_oportunidades_criadas(self, dia: date) -> pd.DataFrame:
        """Extrai oportunidades criadas no dia."""
        inicio, fim = intervalo_do_dia(dia, self._tz)
        soql = queries.oportunidades_criadas(
            para_soql_datetime(inicio), para_soql_datetime(fim), self._fm
        )
        registros = self._client.query(soql)
        logger.info("Oportunidades criadas extraídas: %d.", len(registros))
        colunas = _colunas_opp(self._fm)
        return self._para_dataframe(registros, colunas)

    def extrair_oportunidades_fechadas(self, dia: date) -> pd.DataFrame:
        """Extrai oportunidades fechadas no dia (por CloseDate)."""
        inicio, fim = intervalo_do_dia(dia, self._tz)
        soql = queries.oportunidades_fechadas(
            para_soql_date(inicio.date()), para_soql_date(fim.date()), self._fm
        )
        registros = self._client.query(soql)
        logger.info("Oportunidades fechadas extraídas: %d.", len(registros))
        colunas = _colunas_opp(self._fm)
        return self._para_dataframe(registros, colunas)

    # ------------------------------------------------------------------
    # Extração — Tarefas
    # ------------------------------------------------------------------
    def extrair_tarefas_periodo(self, dia: date) -> pd.DataFrame:
        """Extrai tarefas criadas no dia."""
        inicio, fim = intervalo_do_dia(dia, self._tz)
        soql = queries.tarefas_do_periodo(
            para_soql_datetime(inicio), para_soql_datetime(fim)
        )
        registros = self._client.query(soql)
        self._salvar_snapshot(dia, "Task", registros)
        logger.info("Tarefas do período extraídas: %d.", len(registros))
        return self._para_dataframe(registros, _COLUNAS_TASK)

    def extrair_tarefas_vencidas(self) -> pd.DataFrame:
        """Extrai tarefas vencidas e abertas."""
        soql = queries.tarefas_vencidas()
        registros = self._client.query(soql)
        logger.info("Tarefas vencidas extraídas: %d.", len(registros))
        return self._para_dataframe(registros, _COLUNAS_TASK)

    def extrair_tarefas_futuras(self) -> pd.DataFrame:
        """Extrai tarefas abertas com data futura (próximas atividades)."""
        soql = queries.tarefas_abertas_futuras()
        registros = self._client.query(soql)
        logger.info("Tarefas futuras extraídas: %d.", len(registros))
        return self._para_dataframe(registros, _COLUNAS_TASK)

    # ------------------------------------------------------------------
    # Extração — Fontes configuráveis (Satisfação / Cancelamento)
    # ------------------------------------------------------------------
    def _extrair_fonte_por_data(
        self, dia: date, source: dict[str, Any]
    ) -> pd.DataFrame:
        """Extrai registros de uma fonte configurável filtrando por uma data.

        Valida objeto/campos contra o schema (describe) e degrada com segurança
        (retorna DataFrame vazio) se a fonte não estiver disponível ou a
        consulta falhar — sem derrubar o pipeline.

        Args:
            dia: Dia de referência.
            source: Configuração da fonte (``object``, ``date_field``,
                ``fields``).

        Returns:
            DataFrame com os registros do dia (vazio se indisponível).
        """
        objeto = source.get("object")
        date_field = source.get("date_field")
        campos = list(source.get("fields", []))
        if not objeto or not date_field or not campos:
            return pd.DataFrame(columns=campos)

        # Garante que o campo de data está na seleção e valida tudo no schema.
        campos_ok = self._campos_validos(objeto, campos + [date_field])
        if date_field not in campos_ok:
            logger.warning(
                "Campo de data %s ausente em %s; fonte ignorada.", date_field, objeto
            )
            return pd.DataFrame(columns=campos_ok)

        soql = queries.registros_por_data(
            objeto, campos_ok, date_field, para_soql_date(dia)
        )
        try:
            registros = self._client.query(soql)
        except Exception as exc:  # fonte opcional não deve quebrar o agente
            logger.warning(
                "Falha ao extrair fonte %s: %s", objeto, type(exc).__name__
            )
            return pd.DataFrame(columns=campos_ok)

        return self._para_dataframe(registros, campos_ok)

    def extrair_satisfacao(self, dia: date, source: dict[str, Any]) -> pd.DataFrame:
        """Extrai respostas de satisfação do dia e deriva a nota numérica.

        Converte o campo de sentimento (categórico) em uma nota 0–10 na coluna
        ``SentimentScore``, conforme a escala em ``source['sentiment_scale']``.

        Args:
            dia: Dia de referência.
            source: Configuração da fonte de satisfação.

        Returns:
            DataFrame com as respostas e a coluna ``SentimentScore``.
        """
        df = self._extrair_fonte_por_data(dia, source)
        campo_sentimento = source.get("sentiment_field")
        escala = source.get("sentiment_scale", {})
        if not df.empty and campo_sentimento and campo_sentimento in df.columns:
            df = df.copy()
            df["SentimentScore"] = df[campo_sentimento].map(
                lambda valor: _sentimento_para_nota(valor, escala)
            )
        logger.info("Respostas de satisfação extraídas: %d.", len(df))
        return df

    def extrair_cancelamentos(
        self, dia: date, source: dict[str, Any]
    ) -> pd.DataFrame:
        """Extrai cancelamentos do dia a partir da fonte configurável.

        Args:
            dia: Dia de referência.
            source: Configuração da fonte de cancelamento.

        Returns:
            DataFrame com os cancelamentos do dia.
        """
        df = self._extrair_fonte_por_data(dia, source)
        logger.info("Cancelamentos extraídos: %d.", len(df))
        return df


# ----------------------------------------------------------------------
# Conversão de sentimento (categórico) em nota numérica
# ----------------------------------------------------------------------
def _sentimento_para_nota(valor: Any, escala: dict[str, float]) -> float | None:
    """Converte o texto de sentimento em uma nota numérica conforme a escala.

    A correspondência é por trecho em minúsculas (ex.: "Verde / Promotor"
    contém "verde" → 10). Retorna ``None`` quando não há correspondência,
    para que a média ignore o registro (a IA nunca calcula; Python sim).

    Args:
        valor: Conteúdo do campo de sentimento.
        escala: Mapa trecho→nota (ex.: ``{"verde": 10, "amarelo": 5, "vermelho": 0}``).

    Returns:
        Nota numérica correspondente ou ``None``.
    """
    if valor is None:
        return None
    texto = str(valor).strip().lower()
    if not texto:
        return None
    for chave, nota in escala.items():
        if chave in texto:
            return float(nota)
    return None


# ----------------------------------------------------------------------
# Colunas esperadas (para DataFrames vazios consistentes)
# ----------------------------------------------------------------------
_COLUNAS_TASK = [
    "Id",
    "Subject",
    "Status",
    "Priority",
    "ActivityDate",
    "CreatedDate",
    "LastModifiedDate",
    "OwnerId",
    "WhoId",
    "WhatId",
    "IsClosed",
]


def _colunas_lead(fm: FieldMapping) -> list[str]:
    """Colunas esperadas de Lead, incluindo customizados."""
    base = [
        "Id",
        "Name",
        "Company",
        "Status",
        "LeadSource",
        "CreatedDate",
        "LastModifiedDate",
        "ConvertedDate",
        "IsConverted",
        "OwnerId",
    ]
    return base + fm.campos_lead_customizados()


def _colunas_opp(fm: FieldMapping) -> list[str]:
    """Colunas esperadas de Opportunity, incluindo customizados."""
    base = [
        "Id",
        "Name",
        "StageName",
        "Amount",
        "CreatedDate",
        "CloseDate",
        "LastModifiedDate",
        "IsClosed",
        "IsWon",
        "OwnerId",
        "Probability",
        "ForecastCategory",
        "Type",
        "LeadSource",
    ]
    return base + fm.campos_opportunity_customizados()
