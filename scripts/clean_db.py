"""Limpeza/manutenção do banco Turso do Analytical-Force.

Útil para remover dados acumulados de testes (sobretudo snapshots, que são os
que mais crescem). Reaproveita a conexão do projeto (lê o .env).

Uso (rodar localmente, na raiz do projeto):
    python scripts/clean_db.py --snapshots          # apaga TODOS os snapshots
    python scripts/clean_db.py --date 2026-06-23     # apaga os dados desse dia
    python scripts/clean_db.py --all                 # apaga TODOS os dados
    python scripts/clean_db.py --date 2026-06-23 --yes   # sem confirmação

Tabelas afetadas: agent_runs, daily_metrics, daily_alerts, daily_reports,
salesforce_snapshots. O schema (tabelas/índices) é preservado.
"""

from __future__ import annotations

import argparse
import os
import sys

# Permite "from src..." ao rodar o script diretamente.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.turso_client import get_turso_client  # noqa: E402

# Tabela -> coluna de data (para limpeza por dia).
_COLUNA_DATA: dict[str, str] = {
    "agent_runs": "run_date",
    "daily_metrics": "metric_date",
    "daily_alerts": "alert_date",
    "daily_reports": "report_date",
    "salesforce_snapshots": "snapshot_date",
}


def _contar(client, tabela: str) -> int:
    """Conta as linhas de uma tabela (0 em caso de erro)."""
    try:
        linha = client.fetch_one(f"SELECT COUNT(*) AS n FROM {tabela}")
        return int(linha["n"]) if linha else 0
    except Exception:
        return 0


def main() -> None:
    """Ponto de entrada do utilitário de limpeza."""
    parser = argparse.ArgumentParser(
        description="Limpeza do banco Turso do Analytical-Force."
    )
    parser.add_argument("--date", help="Apaga os dados de uma data (YYYY-MM-DD).")
    parser.add_argument(
        "--snapshots", action="store_true", help="Apaga TODOS os snapshots."
    )
    parser.add_argument(
        "--all", action="store_true", help="Apaga TODOS os dados transacionais."
    )
    parser.add_argument(
        "--yes", action="store_true", help="Não pedir confirmação."
    )
    args = parser.parse_args()

    if not (args.date or args.snapshots or args.all):
        parser.error("Informe ao menos uma ação: --date, --snapshots ou --all.")

    client = get_turso_client()

    # Monta a lista de comandos conforme as opções.
    acoes: list[tuple[str, tuple]] = []
    if args.all:
        for tabela in _COLUNA_DATA:
            acoes.append((f"DELETE FROM {tabela}", ()))
    else:
        if args.snapshots:
            acoes.append(("DELETE FROM salesforce_snapshots", ()))
        if args.date:
            for tabela, coluna in _COLUNA_DATA.items():
                acoes.append((f"DELETE FROM {tabela} WHERE {coluna} = ?", (args.date,)))

    print("== Estado atual ==")
    for tabela in _COLUNA_DATA:
        print(f"  {tabela}: {_contar(client, tabela)} linhas")

    print("\n== Ações a executar ==")
    for sql, params in acoes:
        print("  -", sql, params if params else "")

    if not args.yes:
        resposta = input("\nConfirmar limpeza? (digite 'sim'): ").strip().lower()
        if resposta != "sim":
            print("Cancelado.")
            return

    for sql, params in acoes:
        client.execute_query(sql, params)

    print("\n== Estado após limpeza ==")
    for tabela in _COLUNA_DATA:
        print(f"  {tabela}: {_contar(client, tabela)} linhas")
    print("Limpeza concluída.")


if __name__ == "__main__":
    main()
