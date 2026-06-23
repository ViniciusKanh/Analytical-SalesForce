"""Interface web local opcional (Gradio) do Analytical-Force.

Permite gerar e visualizar o relatório diário pelo navegador, sem expor
credenciais. Requer a dependência opcional ``gradio``:

    pip install gradio
    python app.py

A interface não usa nenhuma API comercial paga. O provider de modelo segue
o ``MODEL_PROVIDER`` configurado no ``.env`` (template/ollama/transformers).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.agent.analytical_force_agent import AnalyticalForceAgent
from src.agent.report_generator import gerar_relatorio
from src.config import get_settings
from src.utils.date_utils import parse_data

_RAIZ = Path(__file__).resolve().parent
_EXEMPLO_PAYLOAD = _RAIZ / "examples" / "sample_payload.json"


def _gerar_demo() -> str:
    """Renderiza o relatório de demonstração (dados de exemplo, não reais)."""
    if not _EXEMPLO_PAYLOAD.is_file():
        return "Arquivo de exemplo não encontrado em examples/sample_payload.json."
    payload = json.loads(_EXEMPLO_PAYLOAD.read_text(encoding="utf-8"))
    markdown, provider = gerar_relatorio(payload, get_settings().model)
    return f"> **Demonstração** (dados de exemplo) • provider: `{provider}`\n\n{markdown}"


def _gerar_real(data_texto: str) -> str:
    """Executa o pipeline real para a data informada (requer Salesforce/Turso)."""
    settings = get_settings()
    agente = AnalyticalForceAgent(settings)
    erros = agente.validar_prerequisitos()
    if erros:
        return "Pré-requisitos não atendidos:\n\n- " + "\n- ".join(erros)

    dia: date | None = parse_data(data_texto) if data_texto.strip() else None
    resultado = agente.executar(dia)
    if resultado.status != "success":
        return f"Execução falhou: {resultado.erro}"
    cabecalho = (
        f"> Execução real • dia: `{resultado.dia}` • provider: "
        f"`{resultado.provider}` • alertas: {len(resultado.alertas)}\n\n"
    )
    return cabecalho + resultado.markdown


def construir_interface():
    """Constrói e retorna a interface Gradio."""
    try:
        import gradio as gr
    except ImportError as exc:  # pragma: no cover - dependência opcional
        raise SystemExit(
            "Gradio não instalado. Rode: pip install gradio"
        ) from exc

    with gr.Blocks(title="Analytical-Force") as demo:
        gr.Markdown("# Analytical-Force\nAgente analítico diário (Salesforce + Turso).")
        with gr.Row():
            data_input = gr.Textbox(
                label="Data (YYYY-MM-DD) — vazio = ontem", placeholder="2026-06-22"
            )
        with gr.Row():
            botao_real = gr.Button("Gerar relatório (real)", variant="primary")
            botao_demo = gr.Button("Demonstração (sem credenciais)")
        saida = gr.Markdown(label="Relatório")

        botao_real.click(_gerar_real, inputs=data_input, outputs=saida)
        botao_demo.click(_gerar_demo, inputs=None, outputs=saida)
    return demo


if __name__ == "__main__":
    construir_interface().launch()
