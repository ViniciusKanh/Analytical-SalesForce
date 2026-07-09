import { useEffect, useState } from "react";

export default function RunModal({ aberto, onFechar, onExecutar, executando, segundos, erro }) {
  const [data, setData] = useState("");
  const [enviarEmail, setEnviarEmail] = useState(false);
  const [criarClickup, setCriarClickup] = useState(false);

  useEffect(() => {
    if (aberto) {
      const ontem = new Date(Date.now() - 86400000);
      setData(ontem.toISOString().slice(0, 10));
    }
  }, [aberto]);

  return (
    <div className={"backdrop" + (aberto ? " open" : "")}>
      <div className="modal">
        <div className="mh">
          <h3>▶ Rodar o agente</h3>
          <button className="x" onClick={onFechar}>
            ✕
          </button>
        </div>
        <label className="lbl">Data de referência</label>
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
        <div style={{ display: "flex", gap: 22, margin: "16px 0", flexWrap: "wrap" }}>
          <label className="switch">
            <input type="checkbox" checked={enviarEmail} onChange={(e) => setEnviarEmail(e.target.checked)} />
            <span className="track"></span> Enviar e-mail
          </label>
          <label className="switch">
            <input type="checkbox" checked={criarClickup} onChange={(e) => setCriarClickup(e.target.checked)} />
            <span className="track"></span> Criar tarefas ClickUp
          </label>
        </div>
        {executando && (
          <div>
            <div style={{ fontSize: 13, color: "var(--muted)" }}>Executando… {segundos}s</div>
            <div className="bar"></div>
          </div>
        )}
        {!executando && erro && (
          <div className="err" style={{ marginTop: 12, fontSize: 13 }}>
            ⚠️ {erro}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 9, marginTop: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={onFechar}>
            Cancelar
          </button>
          <button
            className="btn btn-primary btn-sm"
            disabled={executando}
            onClick={() => onExecutar({ date: data || null, send_email: enviarEmail, create_clickup: criarClickup })}
          >
            ▶ Executar
          </button>
        </div>
      </div>
    </div>
  );
}
