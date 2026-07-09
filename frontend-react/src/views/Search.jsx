import { useEffect, useMemo, useState } from "react";
import SecaoHeader from "../components/SecaoHeader.jsx";
import { consultaTipos, consultaBuscar, consultaDetalhar } from "../api.js";

// Tela de Consulta: busca e detalhe somente-leitura sobre Salesforce, com
// cache Turso como camada rápida (modo híbrido). Nenhum cálculo é feito
// aqui — apenas exibição do que o backend Python já retornou.

const ROTULOS_TIPO = {
  conta: { icone: "🏢", cor: "#0018FF" },
  oportunidade: { icone: "💼", cor: "#16C79A" },
  contrato: { icone: "📄", cor: "#0004DD" },
  item: { icone: "🧾", cor: "#FFC453" },
};

export default function Search({ notificar }) {
  const [tiposInfo, setTiposInfo] = useState(null);
  const [tiposAtivos, setTiposAtivos] = useState([]);
  const [termo, setTermo] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [resultados, setResultados] = useState(null);
  const [erroBusca, setErroBusca] = useState(null);

  const [selecionado, setSelecionado] = useState(null); // { tipo, id, name }
  const [detalhe, setDetalhe] = useState(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [erroDetalhe, setErroDetalhe] = useState(null);

  useEffect(() => {
    consultaTipos()
      .then((d) => {
        setTiposInfo(d);
        setTiposAtivos((d.tipos || []).map((t) => t.tipo));
      })
      .catch(() => setTiposInfo(null));
  }, []);

  const tiposDisponiveis = useMemo(() => tiposInfo?.tipos || [], [tiposInfo]);

  function alternarTipo(tipo) {
    setTiposAtivos((atuais) =>
      atuais.includes(tipo) ? atuais.filter((t) => t !== tipo) : [...atuais, tipo]
    );
  }

  async function executarBusca(e) {
    e?.preventDefault();
    const t = termo.trim();
    if (t.length < 2) {
      setErroBusca("Digite ao menos 2 caracteres.");
      return;
    }
    setBuscando(true);
    setErroBusca(null);
    setResultados(null);
    try {
      const d = await consultaBuscar(t, tiposAtivos, 20);
      setResultados(d.resultados || {});
    } catch (err) {
      setErroBusca(err.message);
      notificar?.("Falha na busca: " + err.message, "bad");
    } finally {
      setBuscando(false);
    }
  }

  async function abrirDetalhe(tipo, item) {
    setSelecionado({ tipo, id: item.id, name: item.name });
    setDetalhe(null);
    setErroDetalhe(null);
    setCarregandoDetalhe(true);
    try {
      const d = await consultaDetalhar(tipo, item.id);
      setDetalhe(d);
    } catch (err) {
      setErroDetalhe(err.message);
    } finally {
      setCarregandoDetalhe(false);
    }
  }

  const totalResultados = resultados
    ? Object.values(resultados).reduce((acc, arr) => acc + arr.length, 0)
    : 0;

  return (
    <>
      <div className="card">
        <SecaoHeader
          icone="🔎"
          titulo="Consulta — Contratos, Clientes e Oportunidades"
          cor="linear-gradient(120deg,#0004DD,#0018FF)"
          extra={
            <span className="chip">
              Fonte: cache Turso + Salesforce (somente leitura)
            </span>
          }
        />

        <form onSubmit={executarBusca}>
          <label className="lbl">Buscar por nome</label>
          <div style={{ display: "flex", gap: 9 }}>
            <input
              type="text"
              placeholder="Ex.: Contrato 4521, Empresa XPTO, Oportunidade Renovação…"
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              autoFocus
            />
            <button className="btn btn-primary btn-sm" type="submit" disabled={buscando}>
              {buscando ? "Buscando…" : "Buscar"}
            </button>
          </div>
        </form>

        <div className="filters" style={{ marginTop: 14 }}>
          {tiposDisponiveis.map((t) => (
            <span
              key={t.tipo}
              className={"fchip" + (tiposAtivos.includes(t.tipo) ? " active" : "")}
              onClick={() => alternarTipo(t.tipo)}
              title={t.objeto}
            >
              {ROTULOS_TIPO[t.tipo]?.icone || "•"} {t.rotulo}
            </span>
          ))}
        </div>

        {tiposInfo && !tiposInfo.itens_do_contrato_configurados && (
          <div className="empty" style={{ textAlign: "left", padding: "10px 0 0", fontSize: 12.5 }}>
            ⚙️ Vínculo Contrato → Itens não configurado (defina{" "}
            <code>SF_CONTRACT_ITEM_PARENT_FIELD</code> no .env). O contrato ainda pode ser
            consultado, mas sem a lista de itens relacionados.
          </div>
        )}

        {erroBusca && <div className="err" style={{ marginTop: 14 }}>{erroBusca}</div>}
      </div>

      <div className="split">
        <div className="card">
          <SecaoHeader
            icone="📋"
            titulo={resultados ? `Resultados (${totalResultados})` : "Resultados"}
            cor="#0018FF"
          />
          {buscando && <div className="empty">Buscando…</div>}
          {!buscando && !resultados && (
            <div className="empty">Digite um termo e clique em Buscar.</div>
          )}
          {!buscando && resultados && totalResultados === 0 && (
            <div className="empty">Nenhum resultado para "{termo}".</div>
          )}
          {!buscando &&
            resultados &&
            Object.entries(resultados).map(([tipo, itens]) => (
              <div key={tipo} style={{ marginBottom: 16 }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 800,
                    textTransform: "uppercase",
                    letterSpacing: ".05em",
                    color: "var(--muted)",
                    marginBottom: 8,
                  }}
                >
                  {ROTULOS_TIPO[tipo]?.icone} {tiposInfo?.tipos?.find((t) => t.tipo === tipo)?.rotulo || tipo}
                </div>
                <div className="dgrid">
                  {itens.map((item) => (
                    <div
                      key={item.id}
                      className="dcard"
                      style={{
                        cursor: "pointer",
                        border:
                          selecionado?.id === item.id ? "2px solid #0018FF" : "1px solid var(--line)",
                      }}
                      onClick={() => abrirDetalhe(tipo, item)}
                    >
                      <div className="dh" style={{ background: ROTULOS_TIPO[tipo]?.cor || "#0018FF" }}>
                        <span>{item.name}</span>
                      </div>
                      {item.subtitle && (
                        <div style={{ padding: "10px 14px", fontSize: 12.5, color: "var(--muted)" }}>
                          {item.subtitle}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
        </div>

        <div className="card">
          <SecaoHeader icone="🗂️" titulo="Detalhe" cor="#171717" />
          {!selecionado && <div className="empty">Selecione um resultado para ver os detalhes.</div>}
          {selecionado && carregandoDetalhe && <div className="empty">Carregando detalhe…</div>}
          {selecionado && erroDetalhe && <div className="err">{erroDetalhe}</div>}
          {selecionado && detalhe && (
            <>
              <div className="chip" style={{ marginBottom: 12 }}>
                Origem: {detalhe.origem}
              </div>
              <table className="owners">
                <tbody>
                  {(detalhe.campos || []).map((c) => (
                    <tr key={c.campo}>
                      <th style={{ whiteSpace: "nowrap" }}>{c.campo}</th>
                      <td>{String(c.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {detalhe.itens_do_contrato != null && (
                <div style={{ marginTop: 18 }}>
                  <SecaoHeader icone="🧾" titulo={`Itens do contrato (${detalhe.itens_do_contrato.length})`} cor="#FFC453" />
                  {detalhe.itens_do_contrato.length === 0 ? (
                    <div className="empty">Nenhum item vinculado.</div>
                  ) : (
                    <div className="dgrid">
                      {detalhe.itens_do_contrato.map((it, idx) => (
                        <div className="dcard" key={it.Id || idx}>
                          <div className="dh" style={{ background: "#FFC453", color: "#171717" }}>
                            {it.Name || it.Id}
                          </div>
                          <ul>
                            {Object.entries(it)
                              .filter(([k, v]) => k !== "attributes" && v != null && k !== "Name")
                              .slice(0, 6)
                              .map(([k, v]) => (
                                <li key={k}>
                                  <b>{k}:</b> {String(v)}
                                </li>
                              ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
