import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import AlertList from "../components/AlertList.jsx";
import DoughnutChart from "../components/DoughnutChart.jsx";
import HighlightsCards from "../components/HighlightsCards.jsx";
import { moeda, num, pct, pipelineVal, extrairResumo, renderResumoHtml } from "../format.js";

const ACC = "#6366f1";

function MetaChips({ dia }) {
  const altos = (dia.alerts || []).filter((a) => a.severity === "high").length;
  const entregas = dia.deliveries || {};
  return (
    <div className="meta">
      <span className="chip">📅 {dia.date}</span>
      <span className="chip">🤖 {dia.provider || "—"}</span>
      <span className="chip">
        🚨 {dia.alerts_count || 0} · {altos} altos
      </span>
      {"email_enviado" in entregas && (
        <span className={"chip " + (entregas.email_enviado ? "good" : "bad")}>
          {entregas.email_enviado ? "✓ E-mail" : "✕ E-mail"}
        </span>
      )}
      {"clickup_tarefas" in entregas && (
        <span className={"chip " + (entregas.clickup_tarefas ? "good" : "")}>
          ClickUp: {entregas.clickup_tarefas || 0}
        </span>
      )}
    </div>
  );
}

export default function Dashboard({ dia, onVerAlertas }) {
  const L = dia.metrics?.leads || {};
  const O = dia.metrics?.opportunities || {};
  const T = dia.metrics?.tasks || {};
  const Sa = dia.metrics?.satisfaction || {};
  const C = dia.metrics?.cancellations || {};
  const Co = dia.metrics?.contracts || {};
  const resumo = extrairResumo(dia.report_markdown);

  const cards = [
    ["🌱", "Leads novos", num(L.new_leads), "green"],
    ["🎯", "Conversão", pct(L.conversion_rate), "blue"],
    ["💰", "Pipeline aberto", moeda(pipelineVal(O)), "violet"],
    ["✨", "Oportunidades criadas", num(O.new_opportunities), "blue"],
    ["🏆", "Ganhas", num(O.won_opportunities), "blue"],
    ["📉", "Perdidas", num(O.lost_opportunities), "red"],
    ["🚧", "Paradas", num(O.stalled_opportunities), "amber"],
    ["⏰", "Tarefas vencidas", num(T.tasks_overdue), "amber"],
  ];
  if (Sa.configured && Sa.responses) cards.push(["😊", "Satisfação", num(Sa.avg_score), "teal"]);
  if (C.configured && C.cancellations_count) cards.push(["❌", "Cancelamentos", num(C.cancellations_count), "red"]);
  if (Co.configured) cards.push(["📄", "Contratos modificados", num(Co.modified_today_count), "violet"]);
  if (Co.readjustment_configured && Co.readjustment_month_count) {
    cards.push(["💹", "Reajuste no mês", moeda(Co.readjustment_month_total), "teal"]);
  }

  return (
    <>
      <div className="card">
        <SecaoHeader icone="🏠" titulo="Resumo do dia" cor={ACC} extra={<MetaChips dia={dia} />} />
        {resumo && (
          <div className="hero">
            <div className="h">🧠 Análise do dia</div>
            <div dangerouslySetInnerHTML={{ __html: renderResumoHtml(resumo) }} />
          </div>
        )}
        <StatGrid itens={cards} />
      </div>

      {Co.readjustment_configured && Co.readjustment_month_count > 0 && (
        <div className="card af-glow">
          <SecaoHeader
            icone="💹"
            titulo="Reajuste de contratos no mês"
            cor="#0d9488"
            extra={<span className="chip">{num(Co.readjustment_month_count)} contrato(s)</span>}
          />
          <StatGrid
            itens={[
              ["💰", "Total reajustado", moeda(Co.readjustment_month_total), "teal"],
              ["📈", "Reajuste médio", pct(Co.readjustment_month_avg_percent), "blue"],
              ...(Co.readjustment_inconsistent_count
                ? [["⚠️", "Possível inconsistência", num(Co.readjustment_inconsistent_count), "amber"]]
                : []),
            ]}
          />
          <div className="disclaimer">⚠️ {Co.readjustment_disclaimer}</div>
        </div>
      )}

      <div className="card">
        <SecaoHeader
          icone="🚨"
          titulo="Alertas por severidade"
          cor="#ef4444"
          extra={
            <span className="chip" style={{ cursor: "pointer" }} onClick={onVerAlertas}>
              Ver todos →
            </span>
          }
        />
        <div className="split">
          <div>
            <AlertList alertas={(dia.alerts || []).slice(0, 4)} />
          </div>
          <div>
            <DoughnutChart alertas={dia.alerts || []} />
          </div>
        </div>
      </div>

      <HighlightsCards
        highlights={dia.highlights}
        chaves={["oportunidades_criadas", "contratos_modificados", "satisfacoes_do_dia"]}
      />
    </>
  );
}
