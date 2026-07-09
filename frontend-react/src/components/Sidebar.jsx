const ITENS = [
  { v: "dashboard", i: "🏠", t: "Dashboard" },
  { v: "oportunidades", i: "💼", t: "Oportunidades" },
  { v: "leads", i: "🌱", t: "Leads" },
  { v: "tarefas", i: "✅", t: "Tarefas" },
  { v: "satisfacao", i: "😊", t: "Satisfação" },
  { v: "cancelamentos", i: "❌", t: "Cancelamentos" },
  { v: "busca", i: "🔎", t: "Consulta" },
  { v: "alertas", i: "🚨", t: "Alertas" },
  { v: "tendencias", i: "📈", t: "Tendências" },
  { v: "relatorio", i: "📄", t: "Relatório" },
  { v: "config", i: "⚙️", t: "Configuração" },
];

export default function Sidebar({ view, onNavigate, aberta }) {
  return (
    <aside className={"sidebar" + (aberta ? " open" : "")}>
      <div className="sb-brand">
        {/* TODO: substituir pelo arquivo real da logo Penso (aguardando upload como anexo). */}
        <div className="logo penso-logo">P</div>
        <div>
          <h1>Analytical-Force</h1>
          <div className="s">Penso · Diagnóstico comercial</div>
        </div>
      </div>
      <nav>
        {ITENS.map((it) => (
          <a
            key={it.v}
            className={view === it.v ? "active" : ""}
            onClick={() => onNavigate(it.v)}
          >
            <span className="i">{it.i}</span>
            {it.t}
          </a>
        ))}
      </nav>
      <div className="sb-foot">
        <img
          src="https://avatars.githubusercontent.com/u/66964047?s=400&u=ef769a81cacd810da6761e08129a1860dd11e36c&v=4"
          alt="Vinicius"
        />
        <div>
          <div className="n">Vinicius de Souza Santos</div>
          <div className="r">Desenvolvedor</div>
        </div>
      </div>
    </aside>
  );
}

export const VIEW_TITULOS = Object.fromEntries(ITENS.map((it) => [it.v, it.t === "Alertas" ? "Alertas & riscos" : it.t]));
