import SecaoHeader from "./SecaoHeader.jsx";

const COR = {
  leads_criados: "#16a34a",
  leads_sem_tarefa: "#f59e0b",
  oportunidades_travadas: "#e11d48",
  oportunidades_ganhas: "#2563eb",
  cancelamentos: "#be123c",
  satisfacoes_piores: "#0d9488",
};
const ROTULO = {
  leads_criados: "🆕 Leads criados",
  leads_sem_tarefa: "⏳ Leads sem 1ª tarefa",
  oportunidades_travadas: "🚧 Oportunidades travadas",
  oportunidades_ganhas: "🏆 Oportunidades ganhas",
  cancelamentos: "❌ Cancelamentos",
  satisfacoes_piores: "😟 Piores satisfações",
};

// Renderiza os "Registros do dia" — links diretos para os registros no
// Salesforce, agrupados por categoria. Recebe o objeto `highlights` já
// calculado pelo backend e a lista de chaves a exibir nesta tela.
export default function HighlightsCards({ highlights, chaves }) {
  const h = highlights || {};
  const ks = chaves.filter((k) => (h[k] || []).length);
  if (!ks.length) return null;
  return (
    <div className="card">
      <SecaoHeader icone="🔗" titulo="Registros (links Salesforce)" cor="#6366f1" />
      <div className="dgrid">
        {ks.map((k) => {
          const itens = (h[k] || []).slice(0, 15);
          const cor = COR[k] || "#6366f1";
          return (
            <div className="dcard" key={k}>
              <div className="dh" style={{ background: `linear-gradient(100deg,${cor},${cor}cc)` }}>
                {ROTULO[k] || k}
                <span className="ct">{(h[k] || []).length}</span>
              </div>
              <ul>
                {itens.map((r, i) => {
                  const nome = r.name || r.id || "registro";
                  const info = r.info ? <span className="info"> ({r.info})</span> : null;
                  return (
                    <li key={i}>
                      {r.url ? (
                        <a href={r.url} target="_blank" rel="noreferrer">
                          {nome}
                        </a>
                      ) : (
                        nome
                      )}
                      {info}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
