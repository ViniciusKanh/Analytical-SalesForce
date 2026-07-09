import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import HighlightsCards from "../components/HighlightsCards.jsx";
import { moeda, num } from "../format.js";

export default function Cancellations({ dia }) {
  const c = dia.metrics?.cancellations || {};
  if (!c.configured) {
    return (
      <div className="card">
        <div className="empty">⚙️ {c.message || "Cancelamento não configurado."}</div>
      </div>
    );
  }
  const produtos = c.cancellations_by_product || {};
  const chaves = Object.keys(produtos);

  return (
    <>
      <div className="card">
        <SecaoHeader icone="❌" titulo={"Cancelamentos — " + dia.date} cor="#e11d48" />
        <StatGrid
          itens={[
            ["📉", "Cancelamentos", num(c.cancellations_count), "red"],
            ["💸", "Impacto MRR", moeda(c.mrr_impact), "red"],
            ["📅", "Impacto ARR", moeda(c.arr_impact), "amber"],
            ["📝", "Motivo principal", num(c.top_reason), "violet"],
          ]}
        />
        {chaves.length > 0 && (
          <div style={{ marginTop: 12 }}>
            {chaves.map((k) => (
              <span className="chip" key={k} style={{ marginRight: 6 }}>
                {k} ({produtos[k]})
              </span>
            ))}
          </div>
        )}
      </div>
      <HighlightsCards highlights={dia.highlights} chaves={["cancelamentos"]} />
    </>
  );
}
