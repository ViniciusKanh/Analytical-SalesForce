import { moeda } from "../format.js";

const COR = { high: "#ef4444", medium: "#f59e0b", low: "#eab308" };
const ROTULO = { high: "ALTA", medium: "MÉDIA", low: "BAIXA" };

function Detalhes({ alerta }) {
  const registros = (alerta.affected_records || []).slice(0, 8);
  if (!registros.length && !alerta.action_plan) return null;
  return (
    <details>
      <summary>Ver detalhes</summary>
      {registros.length > 0 && (
        <ul className="recs">
          {registros.map((r, i) => {
            const nome = r.name || r.id || "registro";
            const info = r.info ? " — " + r.info : r.amount != null ? " — " + moeda(r.amount) : "";
            return (
              <li key={i}>
                {nome}
                {info}
                {r.url && (
                  <>
                    {" "}
                    ·{" "}
                    <a href={r.url} target="_blank" rel="noreferrer">
                      abrir
                    </a>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {alerta.action_plan && <div className="plan">{alerta.action_plan}</div>}
    </details>
  );
}

export default function AlertList({ alertas }) {
  if (!alertas || !alertas.length) {
    return <div className="empty">✅ Nenhum alerta.</div>;
  }
  return (
    <>
      {alertas.map((a, i) => {
        const cor = COR[a.severity] || "#9aa3b2";
        const rotulo = ROTULO[a.severity] || "INFO";
        return (
          <div className="alert" style={{ borderLeftColor: cor }} key={i}>
            <span className="badge" style={{ background: cor }}>
              {rotulo}
            </span>
            <span className="t">{a.title || ""}</span>
            <div className="d">
              {a.category || ""}
              {a.description ? " — " + a.description : ""}
            </div>
            {a.recommended_action && (
              <div className="a">
                <b>Ação:</b> {a.recommended_action}
              </div>
            )}
            <Detalhes alerta={a} />
          </div>
        );
      })}
    </>
  );
}
