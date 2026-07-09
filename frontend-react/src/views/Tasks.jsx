import SecaoHeader from "../components/SecaoHeader.jsx";
import StatGrid from "../components/StatGrid.jsx";
import { num, pct } from "../format.js";

export default function Tasks({ dia }) {
  const T = dia.metrics?.tasks || {};
  return (
    <div className="card">
      <SecaoHeader icone="✅" titulo={"Tarefas — " + dia.date} cor="#f59e0b" />
      <StatGrid
        itens={[
          ["🆕", "Criadas", num(T.tasks_created), "blue"],
          ["✔️", "Concluídas", num(T.tasks_completed), "green"],
          ["📊", "Conclusão", pct(T.completion_rate), "violet"],
          ["⏰", "Vencidas", num(T.tasks_overdue), "red"],
          ["📆", "Futuras", num(T.tasks_future), "teal"],
          ["🔗", "Vencidas→Opps", num(T.overdue_tasks_linked_to_opportunities), "amber"],
          ["🔗", "Vencidas→Leads", num(T.overdue_tasks_linked_to_leads), "amber"],
          ["⏳", "Atraso médio (dias)", num(T.avg_overdue_delay_days), "red"],
        ]}
      />
      {T.top_overdue_owner && (
        <div style={{ marginTop: 12 }}>
          <span className="chip">
            Mais vencidas: {T.top_overdue_owner} ({num(T.top_overdue_owner_count)})
          </span>
        </div>
      )}
    </div>
  );
}
