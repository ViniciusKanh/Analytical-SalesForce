"""Orquestrador principal do agente Analytical-Force.

Coordena o pipeline completo de uma execução diária:

    Salesforce → extração → cálculo (Python) → motor de risco → Turso
              → prompt → modelo local/template → relatório Markdown → arquivo

Princípio: este módulo apenas ORQUESTRA. Toda a regra de cálculo está em
``analytics`` e todo o acesso ao banco em ``database``. A IA nunca calcula.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

from ..analytics import (
    calculate_cancellation_metrics,
    calculate_lead_metrics,
    calculate_opportunity_metrics,
    calculate_satisfaction_metrics,
    calculate_task_metrics,
    generate_alerts,
)
from ..config import get_settings
from ..config.settings import Settings
from ..database.migrations import run_migrations
from ..database.repositories import (
    AgentRunRepository,
    AlertsRepository,
    MetricsRepository,
    ObjectMappingRepository,
    ReportRepository,
    SnapshotRepository,
)
from ..database.turso_client import get_turso_client
from ..delivery.file_writer import salvar_relatorio_md
from ..models.model_router import ModelRouter
from ..salesforce.client import SalesforceAuthError, get_salesforce_client
from ..salesforce.extractors import SalesforceExtractor
from ..salesforce.field_mapping import get_field_mapping
from ..utils.date_utils import agora_tz, para_soql_date
from ..utils.logger import get_logger
from .report_generator import gerar_relatorio

logger = get_logger("agent")

# Tipos escalares aceitos diretamente em daily_metrics (demais viram texto/ignorados).
_TIPOS_ESCALARES = (int, float, str, bool)


@dataclass
class ResultadoExecucao:
    """Resultado consolidado de uma execução do agente."""

    dia: date
    status: str = "running"
    provider: str = "template"
    run_id: int | None = None
    markdown: str = ""
    caminho_relatorio: str | None = None
    metricas: dict[str, Any] = field(default_factory=dict)
    alertas: list[dict[str, Any]] = field(default_factory=list)
    destaques: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    erro: str | None = None


def _limpar_metricas_para_persistencia(
    metricas: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Mantém apenas valores escalares por categoria (para daily_metrics).

    Remove sub-dicionários auxiliares (comparisons, variações, listas) que não
    devem virar linhas numéricas no histórico.
    """
    limpo: dict[str, dict[str, Any]] = {}
    for categoria, indicadores in metricas.items():
        if not isinstance(indicadores, dict):
            continue
        limpo[categoria] = {
            nome: valor
            for nome, valor in indicadores.items()
            if isinstance(valor, _TIPOS_ESCALARES) or valor is None
        }
    return limpo


class AnalyticalForceAgent:
    """Agente analítico que produz o relatório diário a partir do Salesforce."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Inicializa o agente.

        Args:
            settings: Configurações (se None, usa :func:`get_settings`).
        """
        self._settings = settings or get_settings()
        self._tz = self._settings.report_timezone

    # ------------------------------------------------------------------
    # Pré-requisitos
    # ------------------------------------------------------------------
    def validar_prerequisitos(self) -> list[str]:
        """Valida Salesforce, Turso e provider de modelo. Retorna lista de erros."""
        validacoes = self._settings.validar_tudo()
        erros: list[str] = []
        for area, msgs in validacoes.items():
            for msg in msgs:
                erros.append(f"[{area}] {msg}")
        return erros

    # ------------------------------------------------------------------
    # Execução principal
    # ------------------------------------------------------------------
    def executar(self, dia: date | None = None) -> ResultadoExecucao:
        """Executa o pipeline diário completo.

        Args:
            dia: Dia de referência. Se None, usa o dia anterior (ontem).

        Returns:
            :class:`ResultadoExecucao` com relatório, métricas e alertas.
        """
        dia_ref = dia or (agora_tz(self._tz).date() - timedelta(days=1))
        resultado = ResultadoExecucao(dia=dia_ref)
        logger.info("Iniciando execução do Analytical-Force para %s.", dia_ref)

        run_repo: AgentRunRepository | None = None
        run_id: int | None = None

        try:
            # Banco Turso + migrations + repositórios (dentro do try para que
            # falha de conexão vire erro tratado, sem derrubar a aplicação).
            turso = get_turso_client()
            run_migrations(turso)
            run_repo = AgentRunRepository(turso)
            metrics_repo = MetricsRepository(turso)
            alerts_repo = AlertsRepository(turso)
            report_repo = ReportRepository(turso)
            snapshot_repo = SnapshotRepository(turso)
            mapping_repo = ObjectMappingRepository(turso)

            run_id = run_repo.iniciar_execucao(dia_ref)
            resultado.run_id = run_id

            # --- Extração do Salesforce ---
            extrator = self._montar_extrator(snapshot_repo)
            dados = self._extrair(extrator, dia_ref)

            # --- Histórico para comparação ---
            anterior = metrics_repo.buscar_metricas_do_dia(dia_ref - timedelta(days=1))
            media7 = metrics_repo.buscar_media_ultimos_7_dias(dia_ref)

            # --- Mapeamentos configuráveis (satisfação/cancelamento) ---
            # Prioriza mapeamento salvo no Turso; se não houver, usa a config
            # de ambiente (defaults reais da org), ativando os módulos.
            mapa_sat = mapping_repo.buscar_mapeamento(
                "satisfaction"
            ) or self._mapeamento_padrao(self._settings.satisfaction_source)
            mapa_can = mapping_repo.buscar_mapeamento(
                "cancellation"
            ) or self._mapeamento_padrao(self._settings.cancellation_source)

            # --- Cálculo das métricas (Python) ---
            metricas = self._calcular_metricas(dados, anterior, media7, mapa_sat, mapa_can)
            resultado.metricas = metricas

            # --- Persistência das métricas ---
            metrics_repo.salvar_metricas(dia_ref, _limpar_metricas_para_persistencia(metricas))

            # --- Qualidade de dados ---
            data_quality = {
                "salesforce_connection": "ok",
                "satisfaction_configured": bool(mapa_sat),
                "cancellation_configured": bool(mapa_can),
                "missing_fields": [],
            }

            # --- Motor de risco ---
            alertas = generate_alerts(metricas, self._settings.risk, data_quality)
            alerts_repo.salvar_alertas(dia_ref, alertas)
            resultado.alertas = alertas

            # Destaques do dia: registros concretos (com link) para e-mail/ClickUp.
            destaques = self._montar_destaques(dados, metricas)
            resultado.destaques = destaques
            self._anexar_destaques_aos_alertas(alertas, destaques)

            # Enriquecimento opcional por IA: plano de ação por alerta crítico
            # (apenas quando ClickUp e a IA de tarefas estão ativos).
            if self._settings.clickup.auto_create and self._settings.clickup.ai_tasks:
                self._enriquecer_alertas_com_ia(alertas, dia_ref)

            # --- Relatório (template ou modelo local) ---
            payload = self._montar_payload(
                dia_ref, metricas, alertas, data_quality, destaques
            )
            markdown, provider = gerar_relatorio(payload, self._settings.model)
            resultado.markdown = markdown
            resultado.provider = provider

            # --- Persistência e entrega ---
            report_repo.salvar_relatorio(dia_ref, markdown, payload, provider)
            caminho = salvar_relatorio_md(markdown, dia_ref)
            resultado.caminho_relatorio = str(caminho)

            run_repo.finalizar_execucao(run_id, "success")
            resultado.status = "success"
            logger.info("Execução concluída com sucesso (provider=%s).", provider)

        except Exception as exc:
            mensagem = f"{type(exc).__name__}: {exc}"
            logger.error("Falha na execução: %s", mensagem)
            # Registra a falha no Turso apenas se a execução chegou a ser criada.
            if run_repo is not None and run_id is not None:
                try:
                    run_repo.finalizar_execucao(run_id, "error", mensagem)
                except Exception:  # banco pode estar indisponível
                    pass
            resultado.status = "error"
            resultado.erro = mensagem

        return resultado

    # ------------------------------------------------------------------
    # Etapas internas
    # ------------------------------------------------------------------
    def _montar_extrator(self, snapshot_repo: SnapshotRepository) -> SalesforceExtractor:
        """Autentica no Salesforce e devolve o extrator configurado.

        Usa o cliente com as configurações do agente. Por padrão, a
        autenticação ocorre via OAuth Refresh Token (somente leitura).
        """
        sf_client = get_salesforce_client(self._settings)
        sf_client.connect()  # valida credenciais cedo (levanta erro controlado)
        return SalesforceExtractor(
            client=sf_client,
            field_mapping=get_field_mapping(),
            timezone=self._tz,
            snapshot_repo=snapshot_repo,
        )

    def _extrair(self, extrator: SalesforceExtractor, dia: date) -> dict[str, pd.DataFrame]:
        """Extrai todos os DataFrames necessários do Salesforce."""
        return {
            "leads_criados": extrator.extrair_leads_criados(dia),
            "leads_modificados": extrator.extrair_leads_modificados(dia),
            "opp_abertas": extrator.extrair_oportunidades_abertas(dia),
            "opp_criadas": extrator.extrair_oportunidades_criadas(dia),
            "opp_fechadas": extrator.extrair_oportunidades_fechadas(dia),
            "tarefas_periodo": extrator.extrair_tarefas_periodo(dia),
            "tarefas_vencidas": extrator.extrair_tarefas_vencidas(),
            "tarefas_futuras": extrator.extrair_tarefas_futuras(),
            "satisfacao": extrator.extrair_satisfacao(
                dia, self._settings.satisfaction_source
            ),
            "cancelamentos": extrator.extrair_cancelamentos(
                dia, self._settings.cancellation_source
            ),
        }

    @staticmethod
    def _mapeamento_padrao(source: dict[str, Any]) -> dict[str, Any] | None:
        """Constrói o mapeamento (objeto + field_mapping) a partir da config.

        Retorna ``None`` quando a fonte não define um objeto — nesse caso o
        módulo permanece "não configurado" (sem inventar dados).
        """
        if not source or not source.get("object"):
            return None
        return {
            "salesforce_object": source["object"],
            "field_mapping": source.get("field_mapping", {}),
        }

    def _calcular_metricas(
        self,
        dados: dict[str, pd.DataFrame],
        anterior: dict[str, dict[str, Any]],
        media7: dict[str, dict[str, float]],
        mapa_sat: dict[str, Any] | None,
        mapa_can: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]]:
        """Calcula todas as métricas em Python (a IA nunca calcula)."""
        fm = get_field_mapping()
        risk = self._settings.risk

        # Conjunto de WhatId com tarefa futura (para "oportunidade sem próxima tarefa").
        futuras = dados["tarefas_futuras"]
        what_ids: set[str] = set()
        if not futuras.empty and "WhatId" in futuras.columns:
            what_ids = {str(x) for x in futuras["WhatId"].dropna().tolist()}

        leads = calculate_lead_metrics(
            dados["leads_criados"],
            dados["leads_modificados"],
            previous_metrics=anterior.get("leads"),
            seven_day_average=media7.get("leads"),
            first_task_field=fm.lead_first_task,
        )
        opportunidades = calculate_opportunity_metrics(
            dados["opp_abertas"],
            dados["opp_criadas"],
            dados["opp_fechadas"],
            open_task_what_ids=what_ids,
            previous_metrics=anterior.get("opportunities"),
            seven_day_average=media7.get("opportunities"),
            high_value_amount=risk.high_value_opportunity_amount,
            max_days_without_activity=risk.opportunity_max_days_without_activity,
            min_amount=risk.opportunity_min_amount,
            timezone=self._tz,
        )
        tarefas = calculate_task_metrics(
            dados["tarefas_periodo"],
            dados["tarefas_vencidas"],
            dados["tarefas_futuras"],
            previous_metrics=anterior.get("tasks"),
            seven_day_average=media7.get("tasks"),
            timezone=self._tz,
        )
        satisfacao = calculate_satisfaction_metrics(
            mapping=mapa_sat,
            df=dados.get("satisfacao"),
            previous_metrics=anterior.get("satisfaction"),
            seven_day_average=media7.get("satisfaction"),
            min_score=risk.satisfaction_min_score,
        )
        cancelamentos = calculate_cancellation_metrics(
            mapping=mapa_can,
            df=dados.get("cancelamentos"),
            previous_metrics=anterior.get("cancellations"),
            seven_day_average=media7.get("cancellations"),
        )

        return {
            "leads": leads,
            "opportunities": opportunidades,
            "tasks": tarefas,
            "satisfaction": satisfacao,
            "cancellations": cancelamentos,
        }

    def _montar_payload(
        self,
        dia: date,
        metricas: dict[str, Any],
        alertas: list[dict[str, Any]],
        data_quality: dict[str, Any],
        destaques: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """Monta o JSON estruturado entregue ao modelo de IA."""
        return {
            "agent_name": "Analytical-Force",
            "report_date": para_soql_date(dia),
            "timezone": self._tz,
            "period": {
                "current": "reference_day",
                "comparison": "previous_day",
                "seven_day_average": True,
            },
            "metrics": metricas,
            "alerts": alertas,
            "highlights": destaques or {},
            "data_quality": data_quality,
        }

    # ------------------------------------------------------------------
    # Destaques do dia (registros concretos com link p/ e-mail e ClickUp)
    # ------------------------------------------------------------------
    @staticmethod
    def _info_moeda(valor: Any) -> str | None:
        """Formata um valor como moeda BRL curta (ou None se não numérico)."""
        num = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
        if pd.isna(num):
            return None
        return "R$ " + f"{float(num):,.0f}".replace(",", ".")

    def _montar_destaques(
        self, dados: dict[str, pd.DataFrame], metricas: dict[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        """Extrai os registros-chave do dia (com link) para e-mail/ClickUp.

        Inclui leads criados, leads sem primeira tarefa, oportunidades travadas
        e ganhas, cancelamentos e piores satisfações. NÃO inclui tarefas
        vencidas (volume alto demais — sobrecarregaria).
        """
        inst = (self._settings.salesforce.instance_url or "").rstrip("/")
        fm = get_field_mapping()
        limite = 15

        def _reg(rid: Any, nome: Any, info: str | None = None) -> dict[str, Any]:
            sid = str(rid) if rid is not None else ""
            nome_txt = str(nome).strip() if nome is not None and str(nome).strip() else sid
            return {
                "id": sid,
                "name": nome_txt,
                "info": info,
                "url": f"{inst}/{sid}" if inst and sid else None,
            }

        destaques: dict[str, list[dict[str, Any]]] = {}

        leads = dados.get("leads_criados")
        if leads is not None and not leads.empty and "Id" in leads.columns:
            destaques["leads_criados"] = [
                _reg(r.get("Id"), r.get("Name")) for _, r in leads.head(limite).iterrows()
            ]
            campo_ft = fm.lead_first_task
            if campo_ft and campo_ft in leads.columns:
                serie = leads[campo_ft]
                vazio = serie.isna() | serie.astype(str).str.strip().isin(
                    ["", "nan", "NaT", "None"]
                )
                sem = leads[vazio]
                destaques["leads_sem_tarefa"] = [
                    _reg(r.get("Id"), r.get("Name")) for _, r in sem.head(limite).iterrows()
                ]

        opp_fech = dados.get("opp_fechadas")
        if opp_fech is not None and not opp_fech.empty and "IsWon" in opp_fech.columns:
            ganhas = opp_fech[opp_fech["IsWon"].fillna(False).astype(bool)]
            destaques["oportunidades_ganhas"] = [
                _reg(r.get("Id"), r.get("Name"), self._info_moeda(r.get("Amount")))
                for _, r in ganhas.head(limite).iterrows()
            ]

        travadas = (metricas.get("opportunities", {}) or {}).get(
            "stalled_opportunity_details"
        ) or []
        if travadas:
            destaques["oportunidades_travadas"] = [
                _reg(d.get("id"), d.get("name"), self._info_moeda(d.get("amount")))
                for d in travadas[:limite]
            ]

        canc = dados.get("cancelamentos")
        if canc is not None and not canc.empty and "Id" in canc.columns:
            destaques["cancelamentos"] = [
                _reg(
                    r.get("Id"),
                    r.get("Name") or r.get("Conta_Raz_o_Social__c"),
                    self._info_moeda(r.get("VALOR_CANCELADO__c")),
                )
                for _, r in canc.head(limite).iterrows()
            ]

        sat = dados.get("satisfacao")
        if (
            sat is not None
            and not sat.empty
            and "Id" in sat.columns
            and "SentimentScore" in sat.columns
        ):
            score = pd.to_numeric(sat["SentimentScore"], errors="coerce")
            piores = sat[score <= 5].copy()
            if not piores.empty:
                piores["_score"] = pd.to_numeric(piores["SentimentScore"], errors="coerce")
                piores = piores.sort_values("_score")
                destaques["satisfacoes_piores"] = [
                    _reg(
                        r.get("Id"),
                        r.get("Conta_Nome__c") or r.get("Name"),
                        (str(r.get("Sentimento__c")).strip() or None)
                        if r.get("Sentimento__c") is not None
                        else None,
                    )
                    for _, r in piores.head(limite).iterrows()
                ]

        return destaques

    @staticmethod
    def _anexar_destaques_aos_alertas(
        alertas: list[dict[str, Any]],
        destaques: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Anexa registros do dia aos alertas correspondentes (links no ClickUp).

        Só preenche quando o alerta ainda não tem ``affected_records`` (as
        oportunidades já trazem os seus). Não toca em tarefas vencidas.
        """
        for a in alertas:
            if a.get("affected_records"):
                continue
            categoria = a.get("category")
            titulo = (a.get("title") or "").lower()
            if categoria == "Leads" and "primeira tarefa" in titulo:
                a["affected_records"] = destaques.get("leads_sem_tarefa", [])
            elif categoria == "Cancelamentos":
                a["affected_records"] = destaques.get("cancelamentos", [])
            elif categoria == "Satisfação":
                a["affected_records"] = destaques.get("satisfacoes_piores", [])

    # ------------------------------------------------------------------
    # Enriquecimento de alertas por IA (plano de ação para tarefas)
    # ------------------------------------------------------------------
    def _enriquecer_alertas_com_ia(
        self, alertas: list[dict[str, Any]], dia: date
    ) -> None:
        """Gera, via modelo local, um plano de ação por alerta de alta severidade.

        O plano usa apenas os dados concretos do alerta (registros afetados),
        respeitando o princípio "a IA interpreta, o Python calcula". Qualquer
        falha no modelo apenas pula o enriquecimento — a tarefa permanece com
        os dados estruturados do alerta.
        """
        if not self._settings.model.usa_ia:
            return
        router = ModelRouter(self._settings.model)
        system = (
            "Você é um analista comercial sênior do agente Analytical-Force. "
            "Escreva planos de ação curtos, objetivos e específicos, em português "
            "do Brasil. Use SOMENTE os dados fornecidos; nunca invente números, "
            "nomes ou clientes."
        )
        # Limita a quantidade de planos por IA: cada geração em CPU é custosa.
        # Os demais alertas mantêm os dados estruturados (já acionáveis).
        criticos = [a for a in alertas if a.get("severity") == "high"][:3]
        enriquecidos = 0
        for alerta in criticos:
            prompt = self._prompt_plano_acao(alerta, dia)
            try:
                texto, _ = router.interpretar(prompt, system=system)
            except Exception as exc:  # IA nunca derruba o pipeline
                logger.warning(
                    "Falha ao gerar plano de ação por IA: %s", type(exc).__name__
                )
                texto = None
            if texto and texto.strip():
                alerta["action_plan"] = texto.strip()
                enriquecidos += 1
        if enriquecidos:
            logger.info("Planos de ação por IA gerados: %d.", enriquecidos)

    @staticmethod
    def _prompt_plano_acao(alerta: dict[str, Any], dia: date) -> str:
        """Monta o prompt do plano de ação a partir dos dados do alerta."""
        linhas = [
            f"Data de referência: {para_soql_date(dia)}",
            f"Alerta: {alerta.get('title', '')}",
            f"Categoria: {alerta.get('category', '')}",
            f"Diagnóstico: {alerta.get('description', '')}",
            f"Ação recomendada (base): {alerta.get('recommended_action', '')}",
        ]
        registros = alerta.get("affected_records") or []
        if registros:
            linhas.append("")
            linhas.append("Registros afetados (use estes dados reais):")
            for r in registros[:10]:
                partes: list[str] = [str(r.get("name") or r.get("id") or "registro")]
                if r.get("amount") is not None:
                    partes.append(f"R$ {float(r['amount']):,.0f}")
                if r.get("stage"):
                    partes.append(f"estágio {r['stage']}")
                if r.get("owner"):
                    partes.append(f"GC {r['owner']}")
                if r.get("days_inactive") is not None:
                    partes.append(f"{r['days_inactive']} dias sem atividade")
                if r.get("next_action"):
                    partes.append(f"próxima ação {r['next_action']}")
                linhas.append("- " + " | ".join(partes))
        linhas.append("")
        linhas.append(
            "Escreva um plano de ação prático com 3 a 5 passos numerados para "
            "resolver este alerta hoje, citando os registros mais críticos pelo "
            "nome. Seja específico, direto e priorize por valor/risco. Não use "
            "introdução nem conclusão — apenas os passos."
        )
        return "\n".join(linhas)


def run_daily(dia: date | None = None) -> ResultadoExecucao:
    """Função de conveniência para executar o agente uma vez.

    Args:
        dia: Dia de referência (None = ontem).

    Returns:
        Resultado da execução.
    """
    return AnalyticalForceAgent().executar(dia)
