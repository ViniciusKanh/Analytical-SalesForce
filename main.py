"""Ponto de entrada (CLI) do Analytical-Force.

Uso:
    python main.py                 # executa o agente para ontem
    python main.py --date 2026-06-22
    python main.py --check         # valida configuração (sem executar)
    python main.py --demo          # gera um relatório de demonstração (sem Salesforce)

Comandos:
    --check : valida Salesforce, Turso e provider de modelo.
    --demo  : renderiza o relatório a partir de examples/sample_payload.json
              (dados de DEMONSTRAÇÃO, não reais), útil para validar o template
              localmente antes de conectar Salesforce/Turso.
    --no-email : não tenta enviar e-mail mesmo se o SMTP estiver configurado.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.agent.analytical_force_agent import AnalyticalForceAgent
from src.agent.report_generator import gerar_relatorio
from src.config import get_settings
from src.delivery.clickup_sender import criar_tarefas_de_alertas
from src.delivery.email_sender import enviar_relatorio_email
from src.delivery.file_writer import salvar_relatorio_md
from src.utils.date_utils import parse_data
from src.utils.logger import get_logger

logger = get_logger("main")

_RAIZ = Path(__file__).resolve().parent
_EXEMPLO_PAYLOAD = _RAIZ / "examples" / "sample_payload.json"


def _comando_check() -> int:
    """Valida a configuração e imprime um resumo seguro (sem segredos)."""
    settings = get_settings()
    print("== Configuração (resumo seguro) ==")
    for chave, valor in settings.resumo_seguro().items():
        print(f"  {chave}: {valor}")

    print("\n== Validação ==")
    validacoes = settings.validar_tudo()
    houve_erro = False
    for area, erros in validacoes.items():
        if erros:
            houve_erro = True
            for msg in erros:
                print(f"  [ERRO] {area}: {msg}")
        else:
            print(f"  [OK] {area}")
    return 1 if houve_erro else 0


def _comando_demo() -> int:
    """Gera um relatório de demonstração a partir do payload de exemplo."""
    if not _EXEMPLO_PAYLOAD.is_file():
        print(f"[ERRO] Arquivo de exemplo não encontrado: {_EXEMPLO_PAYLOAD}")
        return 1

    payload = json.loads(_EXEMPLO_PAYLOAD.read_text(encoding="utf-8"))
    settings = get_settings()
    markdown, provider = gerar_relatorio(payload, settings.model)

    dia = parse_data(payload.get("report_date", date.today().isoformat()))
    caminho = salvar_relatorio_md(markdown, dia)
    print("== DEMONSTRAÇÃO (dados de exemplo, NÃO reais) ==")
    print(f"Provider efetivo: {provider}")
    print(f"Relatório salvo em: {caminho}")
    print("\n" + markdown)
    return 0


def _comando_executar(dia: date | None, enviar_email: bool) -> int:
    """Executa o pipeline diário real (requer Salesforce e Turso)."""
    settings = get_settings()
    agente = AnalyticalForceAgent(settings)

    erros = agente.validar_prerequisitos()
    if erros:
        print("[ERRO] Pré-requisitos não atendidos:")
        for e in erros:
            print(f"  - {e}")
        print("\nDica: rode 'python main.py --demo' para validar o template sem credenciais.")
        return 1

    resultado = agente.executar(dia)

    if resultado.status != "success":
        print(f"[ERRO] Execução falhou: {resultado.erro}")
        return 1

    print("== Execução concluída ==")
    print(f"  Dia de referência: {resultado.dia}")
    print(f"  Provider efetivo:  {resultado.provider}")
    print(f"  Alertas gerados:   {len(resultado.alertas)}")
    print(f"  Relatório:         {resultado.caminho_relatorio}")

    # Entregas opcionais.
    if enviar_email and settings.email.is_configured:
        enviado = enviar_relatorio_email(
            config=settings.email,
            assunto=f"Analytical-Force — Relatório {resultado.dia}",
            report_date=str(resultado.dia),
            metrics=resultado.metricas,
            alerts=resultado.alertas,
            report_markdown=resultado.markdown,
            highlights=resultado.destaques,
        )
        print(f"  E-mail enviado:    {enviado}")

    criadas = criar_tarefas_de_alertas(
        resultado.alertas,
        settings.clickup,
        settings.clickup.auto_create,
        instance_url=settings.salesforce.instance_url,
        report_date=str(resultado.dia),
    )
    if criadas:
        print(f"  Tarefas ClickUp:   {criadas}")

    return 0


def cli(argv: list[str] | None = None) -> int:
    """Interface de linha de comando do agente.

    Args:
        argv: Lista de argumentos (None usa ``sys.argv``).

    Returns:
        Código de saída (0 = sucesso).
    """
    parser = argparse.ArgumentParser(
        description="Analytical-Force — agente analítico diário (Salesforce + Turso)."
    )
    parser.add_argument("--date", help="Dia de referência (YYYY-MM-DD). Padrão: ontem.")
    parser.add_argument("--check", action="store_true", help="Valida a configuração.")
    parser.add_argument("--demo", action="store_true", help="Relatório de demonstração.")
    parser.add_argument(
        "--no-email", action="store_true", help="Não envia e-mail mesmo se configurado."
    )
    args = parser.parse_args(argv)

    if args.check:
        return _comando_check()
    if args.demo:
        return _comando_demo()

    dia = parse_data(args.date) if args.date else None
    return _comando_executar(dia, enviar_email=not args.no_email)


if __name__ == "__main__":
    sys.exit(cli())
