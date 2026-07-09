// Helpers de formatação pt-BR. Só formatam valores já calculados pelo
// backend Python — nenhuma métrica é derivada aqui.

export function moeda(v) {
  return "R$ " + Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function pct(v) {
  return v == null ? "—" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";
}

export function num(v) {
  if (v == null) return "—";
  return typeof v === "number" ? v.toLocaleString("pt-BR") : v;
}

export function pipelineVal(o) {
  return o.open_pipeline_product_value != null && o.open_pipeline_product_value
    ? o.open_pipeline_product_value
    : o.open_pipeline_amount;
}

export function extrairResumo(md) {
  const m = (md || "").split(/##\s+/).find((s) => /resumo executivo/i.test(s.split("\n")[0]));
  return m ? m.split("\n").slice(1).join("\n").trim() : "";
}

/** Escapa HTML básico antes de reinjetar como innerHTML. */
export function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Converte negrito Markdown (**texto**) e parágrafos em HTML simples.
 * Usado só para exibição do resumo já gerado pelo backend — não interpreta
 * nem recalcula nada, apenas formata o texto que já veio pronto.
 */
export function renderResumoHtml(texto) {
  if (!texto) return "";
  const paragrafos = texto
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  return paragrafos
    .map((p) => {
      const comNegrito = escapeHtml(p)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br/>");
      return `<p>${comNegrito}</p>`;
    })
    .join("");
}
