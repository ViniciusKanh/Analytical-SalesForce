import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import HighlightsCards from "../components/HighlightsCards.jsx";
import { num } from "../format.js";

export default function Satisfaction({ dia }) {
  const s = dia.metrics?.satisfaction || {};
  if (!s.configured) {
    return (
      <div className="card">
        <div className="empty">⚙️ {s.message || "Satisfação não configurada."}</div>
      </div>
    );
  }
  if (!s.responses) {
    return (
      <div className="card">
        <div className="empty">{s.message || "Sem respostas de satisfação nesse dia."}</div>
      </div>
    );
  }
  const motivos = s.top_negative_reasons || {};
  const chaves = Object.keys(motivos);

  return (
    <>
      <div className="card">
        <SecaoHeader icone="😊" titulo={"Satisfação — " + dia.date} cor="#0d9488" />
        <StatGrid
          itens={[
            ["⭐", "Nota média", num(s.avg_score), "teal"],
            ["🗳️", "Respostas", num(s.responses), "blue"],
            ["😟", "Negativas", num(s.negative_count), "red"],
          ]}
        />
        {chaves.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {chaves.map((k) => (
              <span className="chip" key={k} style={{ marginRight: 6 }}>
                {k} ({motivos[k]})
              </span>
            ))}
          </div>
        )}
      </div>
      <HighlightsCards highlights={dia.highlights} chaves={["satisfacoes_piores"]} />
    </>
  );
}
