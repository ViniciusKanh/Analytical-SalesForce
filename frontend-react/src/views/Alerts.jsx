import { useState } from "react";
import SecaoHeader from "../components/SecaoHeader.jsx";
import AlertList from "../components/AlertList.jsx";
import DoughnutChart from "../components/DoughnutChart.jsx";

const FILTROS = [
  ["all", "Todos"],
  ["high", "Altos"],
  ["medium", "Médios"],
  ["low", "Baixos"],
];

export default function Alerts({ dia }) {
  const [filtro, setFiltro] = useState("all");
  const alertas = dia.alerts || [];
  const contagem = { all: alertas.length, high: 0, medium: 0, low: 0 };
  alertas.forEach((a) => {
    if (contagem[a.severity] != null) contagem[a.severity]++;
  });
  const filtrados = filtro === "all" ? alertas : alertas.filter((a) => a.severity === filtro);

  return (
    <div className="card">
      <SecaoHeader icone="🚨" titulo={"Alertas & riscos — " + dia.date} cor="#ef4444" />
      <div className="split">
        <div>
          <div className="filters">
            {FILTROS.map(([k, l]) => (
              <span key={k} className={"fchip" + (filtro === k ? " active" : "")} onClick={() => setFiltro(k)}>
                {l} ({contagem[k] || 0})
              </span>
            ))}
          </div>
          <AlertList alertas={filtrados} />
        </div>
        <div>
          <DoughnutChart alertas={alertas} />
        </div>
      </div>
    </div>
  );
}
