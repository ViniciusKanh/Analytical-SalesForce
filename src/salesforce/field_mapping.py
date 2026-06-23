"""Centralização dos nomes de campos customizados do Salesforce.

Objetivo: evitar nomes "mágicos" espalhados no código. Quando houver
incerteza sobre um campo customizado, ele é configurável aqui (via
variáveis de ambiente em ``settings.custom_fields``) e/ou via
``object_mapping`` no banco para satisfação e cancelamento.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import get_settings


@dataclass(frozen=True)
class FieldMapping:
    """Mapeamento de campos customizados usados pelo agente.

    Campos padrão do Salesforce não entram aqui; apenas customizados (``__c``)
    ou pontos de incerteza que precisam ser ajustáveis por organização.
    """

    lead_first_task: str = "FirstTask__c"
    opp_motivo_perda: str = "Motivo_Perda_ganho__c"
    opp_origem: str = ""  # usa o campo padrão LeadSource (não customizado)
    opp_tipo_venda: str = "Tipo_venda__c"
    opp_produto: str = "ProdutoPrincipal__c"
    # Campos adicionais úteis para diagnóstico e tarefas.
    opp_proxima_acao: str = "Proxima_acao__c"
    opp_dias_sem_atividade: str = "OppDiasSemAtividade__c"
    opp_gc_nome: str = "GC_Nome__c"
    opp_valor_mensal: str = "Valor_Liquido_Mensal__c"

    def campos_lead_customizados(self) -> list[str]:
        """Lista de campos customizados de Lead a incluir nas queries.

        Campos vazios (desativados) são omitidos.
        """
        return [campo for campo in [self.lead_first_task] if campo]

    def campos_opportunity_customizados(self) -> list[str]:
        """Lista de campos customizados de Opportunity a incluir nas queries.

        Campos vazios (desativados) são omitidos e duplicatas são removidas.
        """
        candidatos = [
            self.opp_motivo_perda,
            self.opp_origem,
            self.opp_tipo_venda,
            self.opp_produto,
            self.opp_proxima_acao,
            self.opp_dias_sem_atividade,
            self.opp_gc_nome,
            self.opp_valor_mensal,
        ]
        # Remove vazios e duplicatas preservando a ordem.
        vistos: list[str] = []
        for campo in candidatos:
            if campo and campo not in vistos:
                vistos.append(campo)
        return vistos


def get_field_mapping() -> FieldMapping:
    """Constrói o mapeamento a partir das configurações de ambiente.

    Permite, por exemplo, alterar ``FirstTask__c`` sem mexer no código.
    """
    cf = get_settings().custom_fields
    return FieldMapping(
        lead_first_task=cf.get("lead_first_task", "FirstTask__c"),
        opp_motivo_perda=cf.get("opp_motivo_perda", "Motivo_Perda_ganho__c"),
        opp_origem=cf.get("opp_origem", ""),
        opp_tipo_venda=cf.get("opp_tipo_venda", "Tipo_venda__c"),
        opp_produto=cf.get("opp_produto", "ProdutoPrincipal__c"),
        opp_proxima_acao=cf.get("opp_proxima_acao", "Proxima_acao__c"),
        opp_dias_sem_atividade=cf.get("opp_dias_sem_atividade", "OppDiasSemAtividade__c"),
        opp_gc_nome=cf.get("opp_gc_nome", "GC_Nome__c"),
        opp_valor_mensal=cf.get("opp_valor_mensal", "Valor_Liquido_Mensal__c"),
    )
