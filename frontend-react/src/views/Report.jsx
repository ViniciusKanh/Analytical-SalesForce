import { useMemo, useState } from "react";
import { marked } from "marked";
import SecaoHeader from "../components/SecaoHeader.jsx";

// Divide o Markdown do relatório em seções por "## " para exibir em abas
// (igual ao painel anterior) — não interpreta nem recalcula nada, só
// reformata o texto que o backend já gerou.
function dividirSecoes(md) {
  const linhas = (md || "").split("\n");
  const secoes = [];
  let atual = null;
  for (const ln of linhas) {
    const m = ln.match(/^##\s+(.*)/);
    if (m) {
      if (atual) secoes.push(atual);
      atual = { titulo: m[1].trim(), corpo: "" };
    } else if (atual) {
      atual.corpo += ln + "\n";
    }
  }
  if (atual) secoes.push(atual);
  return [{ titulo: "Tudo", corpo: md || "" }].concat(
    secoes.map((s) => ({ titulo: s.titulo.replace(/^\d+\.\s*/, ""), corpo: "## " + s.titulo + "\n" + s.corpo }))
  );
}

export default function Report({ dia }) {
  const md = dia.report_markdown || "_Sem relatório._";
  const abas = useMemo(() => dividirSecoes(md), [md]);
  const [ativa, setAtiva] = useState(0);

  function copiar() {
    navigator.clipboard.writeText(md);
  }
  function baixar() {
    const blob = new Blob([md], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "relatorio_" + (dia.date || "af") + ".md";
    a.click();
  }

  return (
    <div className="card">
      <SecaoHeader
        icone="📄"
        titulo={"Relatório — " + dia.date}
        cor="#6366f1"
        extra={
          <span style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={copiar}>
              Copiar
            </button>
            <button className="btn btn-ghost btn-sm" onClick={baixar}>
              Baixar .md
            </button>
          </span>
        }
      />
      <div className="tabs">
        {abas.map((a, i) => (
          <div key={i} className={"tab" + (i === ativa ? " active" : "")} onClick={() => setAtiva(i)}>
            {a.titulo}
          </div>
        ))}
      </div>
      <div id="panels">
        {abas.map((a, i) => (
          <div
            key={i}
            className={"panel" + (i === ativa ? " active" : "")}
            dangerouslySetInnerHTML={{ __html: marked.parse(a.corpo) }}
          />
        ))}
      </div>
    </div>
  );
}
