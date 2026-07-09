import { useEffect, useState } from "react";
import SecaoHeader from "../components/SecaoHeader.jsx";
import TrendChart from "../components/TrendChart.jsx";
import { buscarHistorico } from "../api.js";

const METRICAS = [
  ["opportunities.open_pipeline_product_value", "Pipeline (produtos)"],
  ["opportunities.open_pipeline_amount", "Pipeline (Amount)"],
  ["leads.new_leads", "Leads novos"],
  ["leads.conversion_rate", "Conversão (%)"],
  ["opportunities.won_opportunities", "Ganhas"],
  ["opportunities.stalled_opportunities", "Paradas"],
  ["tasks.tasks_overdue", "Tarefas vencidas"],
  ["satisfaction.avg_score", "Satisfação"],
];

export default function Trends() {
  const [metrica, setMetrica] = useState(METRICAS[0][0]);
  const [dias, setDias] = useState(7);
  const [serie, setSerie] = useState([]);
  const [status, setStatus] = useState("Carregando série do banco…");

  async function carregar() {
    setStatus("Carregando do Turso…");
    try {
      const d = await buscarHistorico(dias);
      const lista = d.days || [];
      setSerie(lista);
      setStatus(lista.length ? `${lista.length} dia(s) · ${METRICAS.find((m) => m[0] === metrica)?.[1]}` : "Sem dados salvos ainda — rode o agente em alguns dias.");
    } catch (e) {
      setStatus("Falha: " + e.message);
    }
  }

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="card">
      <SecaoHeader
        icone="📈"
        titulo="Tendências (histórico do Turso)"
        cor="#8b5cf6"
        extra={
          <span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select className="sel" value={metrica} onChange={(e) => setMetrica(e.target.value)}>
              {METRICAS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <select className="sel" value={dias} onChange={(e) => setDias(Number(e.target.value))}>
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
              <option value={30}>30 dias</option>
            </select>
            <button className="btn btn-ghost btn-sm" onClick={carregar}>
              Carregar
            </button>
          </span>
        }
      />
      <TrendChart dias={serie} metrica={metrica} rotulo={METRICAS.find((m) => m[0] === metrica)?.[1] || metrica} />
      <div className="empty" style={{ padding: 12 }}>
        {status}
      </div>
    </div>
  );
}
