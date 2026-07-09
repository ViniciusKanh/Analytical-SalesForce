import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import HighlightsCards from "../components/HighlightsCards.jsx";
import { num, pct } from "../format.js";

export default function Leads({ dia }) {
  const L = dia.metrics?.leads || {};
  const porVendedor = L.leads_by_owner || {};
  const vendedores = Object.keys(porVendedor);

  return (
    <>
      <div className="card">
        <SecaoHeader icone="🌱" titulo={"Leads — " + dia.date} cor="#16a34a" />
        <StatGrid
          itens={[
            ["🆕", "Novos", num(L.new_leads), "green"],
            ["✅", "Convertidos", num(L.converted_leads), "blue"],
            ["🎯", "Conversão", pct(L.conversion_rate), "violet"],
            ["⏳", "Sem 1ª tarefa", num(L.leads_without_first_task), "amber"],
            ["⏱️", "Tempo médio 1ª tarefa (h)", num(L.avg_time_to_first_task_hours), "teal"],
            ["📈", "Origem top", num(L.top_lead_source_by_volume), "blue"],
          ]}
        />
      </div>
      {vendedores.length > 0 && (
        <div className="card">
          <SecaoHeader icone="👥" titulo="Leads por vendedor" cor="#16a34a" extra={<span className="chip">com / sem conversão</span>} />
          <table className="owners">
            <thead>
              <tr>
                <th>Vendedor</th>
                <th style={{ textAlign: "right" }}>Leads</th>
                <th style={{ textAlign: "right" }}>Convert.</th>
                <th style={{ textAlign: "right" }}>Taxa</th>
              </tr>
            </thead>
            <tbody>
              {vendedores.map((k) => {
                const d = porVendedor[k];
                return (
                  <tr key={k}>
                    <td>{k}</td>
                    <td style={{ textAlign: "right" }}>{d.total}</td>
                    <td style={{ textAlign: "right" }}>{d.converted}</td>
                    <td style={{ textAlign: "right" }}>{pct(d.conversion_rate)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <HighlightsCards highlights={dia.highlights} chaves={["leads_criados", "leads_sem_tarefa"]} />
    </>
  );
}
