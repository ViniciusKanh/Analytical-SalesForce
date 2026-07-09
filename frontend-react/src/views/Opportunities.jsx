import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import HighlightsCards from "../components/HighlightsCards.jsx";
import { moeda, num, pct, pipelineVal } from "../format.js";

export default function Opportunities({ dia }) {
  const O = dia.metrics?.opportunities || {};
  const porVendedor = O.pipeline_by_owner || {};
  const vendedores = Object.keys(porVendedor);
  const total = O.open_pipeline_product_value || O.open_pipeline_amount || 0;

  return (
    <>
      <div className="card">
        <SecaoHeader icone="💼" titulo={"Oportunidades — " + dia.date} cor="#2563eb" />
        <StatGrid
          itens={[
            ["🆕", "Novas", num(O.new_opportunities), "blue"],
            ["📂", "Abertas", num(O.open_opportunities), "blue"],
            ["🏆", "Ganhas", num(O.won_opportunities), "green"],
            ["📉", "Perdidas", num(O.lost_opportunities), "red"],
            ["💰", "Pipeline aberto", moeda(pipelineVal(O)), "violet"],
            ["💵", "Valor ganho", moeda(O.won_amount), "green"],
            ["🎯", "Win rate", pct(O.win_rate), "blue"],
            ["📊", "Loss rate", pct(O.loss_rate), "amber"],
            ["🚧", "Paradas", num(O.stalled_opportunities), "amber"],
            ["🔴", "Alto valor paradas", num(O.high_value_stalled_opportunities), "red"],
            ["🔕", "Sem próxima tarefa", num(O.opportunities_without_next_task), "amber"],
            ["📅", "Fecham no mês", num(O.opportunities_closing_this_month), "violet"],
          ]}
        />
      </div>
      {vendedores.length > 0 && (
        <div className="card">
          <SecaoHeader
            icone="💰"
            titulo="Pipeline por vendedor"
            cor="#2563eb"
            extra={<span className="chip">Total: {moeda(total)}</span>}
          />
          <table className="owners">
            <thead>
              <tr>
                <th>Vendedor</th>
                <th style={{ textAlign: "right" }}>Pipeline</th>
              </tr>
            </thead>
            <tbody>
              {vendedores.map((k) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td style={{ textAlign: "right" }}>{moeda(porVendedor[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <HighlightsCards highlights={dia.highlights} chaves={["oportunidades_travadas", "oportunidades_ganhas"]} />
    </>
  );
}
