import { VIEW_TITULOS } from "./Sidebar.jsx";

export default function Topbar({
  view,
  online,
  dias,
  diaAtual,
  onSelecionarDia,
  onRecarregar,
  onAlternarTema,
  tema,
  onAbrirRun,
  onAlternarSidebar,
  carregando,
}) {
  return (
    <header className="topbar">
      <button className="hamb" type="button" onClick={onAlternarSidebar}>
        ☰
      </button>
      <h2 className="vtitle">{VIEW_TITULOS[view] || view}</h2>
      <div className="spacer"></div>
      <div className="pill">
        <span className={"dot " + (online ? "on" : "off")}></span>
        <span>{online == null ? "…" : online ? "Online" : "Offline"}</span>
      </div>
      <select
        className="sel"
        title="Dia"
        value={diaAtual || ""}
        onChange={(e) => onSelecionarDia(e.target.value)}
      >
        {dias.length === 0 && <option>—</option>}
        {dias.map((d) => (
          <option key={d} value={d}>
            {d}
          </option>
        ))}
      </select>
      <button className="iconbtn" title="Atualizar" onClick={onRecarregar} disabled={carregando}>
        <span style={carregando ? { display: "inline-block", animation: "spin .8s linear infinite" } : undefined}>↻</span>
      </button>
      <button className="iconbtn" title="Tema" onClick={onAlternarTema}>
        {tema === "dark" ? "☀️" : "🌙"}
      </button>
      <button className="btn btn-primary btn-sm" onClick={onAbrirRun}>
        ▶ Rodar
      </button>
    </header>
  );
}
