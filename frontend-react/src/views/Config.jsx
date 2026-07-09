import { useEffect, useState } from "react";
import SecaoHeader from "../components/SecaoHeader.jsx";
import {
  getBaseUrl,
  setBaseUrl,
  getApiKey,
  setApiKey,
  verificarSaude,
  listarEmailsCc,
  adicionarEmailCc,
  removerEmailCc,
} from "../api.js";

export default function Config({ notificar, onConfigSalva }) {
  const [base, setBase] = useState(getBaseUrl());
  const [key, setKey] = useState(getApiKey());
  const [emailsCc, setEmailsCc] = useState([]);
  const [novoEmail, setNovoEmail] = useState("");
  const [carregandoCc, setCarregandoCc] = useState(true);

  async function carregarEmailsCc() {
    setCarregandoCc(true);
    try {
      const d = await listarEmailsCc();
      setEmailsCc(d.emails_cc || []);
    } catch (e) {
      notificar("Falha ao carregar e-mails em cópia: " + e.message, "bad");
    } finally {
      setCarregandoCc(false);
    }
  }

  useEffect(() => {
    carregarEmailsCc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function salvarConexao() {
    setBaseUrl(base);
    setApiKey(key);
    notificar("Configuração salva", "ok");
    onConfigSalva?.();
  }

  async function testarConexao() {
    setBaseUrl(base);
    setApiKey(key);
    try {
      await verificarSaude();
      notificar("Online ✓", "ok");
    } catch {
      notificar("Sem conexão", "bad");
    }
    onConfigSalva?.();
  }

  async function handleAdicionarEmail(e) {
    e.preventDefault();
    const email = novoEmail.trim();
    if (!email) return;
    try {
      const d = await adicionarEmailCc(email);
      setEmailsCc(d.emails_cc || []);
      setNovoEmail("");
      notificar("E-mail cadastrado em cópia", "ok");
    } catch (err) {
      notificar(err.message, "bad");
    }
  }

  async function handleRemoverEmail(email) {
    try {
      const d = await removerEmailCc(email);
      setEmailsCc(d.emails_cc || []);
      notificar("E-mail removido da cópia", "ok");
    } catch (err) {
      notificar(err.message, "bad");
    }
  }

  return (
    <>
      <div className="card" style={{ maxWidth: 620 }}>
        <SecaoHeader icone="⚙️" titulo="Conexão" cor="#64748b" />
        <label className="lbl">URL da API (Space)</label>
        <input type="text" value={base} onChange={(e) => setBase(e.target.value)} />
        <div style={{ height: 12 }}></div>
        <label className="lbl">X-API-Key (vazio se o Space não exige)</label>
        <input type="password" value={key} onChange={(e) => setKey(e.target.value)} />
        <div style={{ display: "flex", gap: 9, marginTop: 18, flexWrap: "wrap" }}>
          <button className="btn btn-ghost btn-sm" onClick={testarConexao}>
            Testar conexão
          </button>
          <button className="btn btn-primary btn-sm" onClick={salvarConexao}>
            Salvar
          </button>
        </div>
        <div className="empty" style={{ textAlign: "left", padding: "16px 0 0", color: "var(--muted)" }}>
          As telas leem os dados salvos no Turso (GET /day). Use <b>▶ Rodar</b> para gerar um novo dia.
        </div>
      </div>

      <div className="card" style={{ maxWidth: 620 }}>
        <SecaoHeader icone="✉️" titulo="E-mails em cópia (Cc)" cor="#0d9488" />
        <div className="empty" style={{ textAlign: "left", padding: 0, color: "var(--muted)", fontSize: 13 }}>
          Além do destinatário principal (fixo, definido no Space), estes e-mails recebem cópia do relatório
          diário. Cadastrados aqui — persistidos no Turso, sem precisar de redeploy.
        </div>

        {carregandoCc ? (
          <div className="empty">Carregando…</div>
        ) : emailsCc.length === 0 ? (
          <div className="empty">Nenhum e-mail em cópia cadastrado.</div>
        ) : (
          <ul className="cclist">
            {emailsCc.map((e) => (
              <li className="ccrow" key={e}>
                <span>{e}</span>
                <button onClick={() => handleRemoverEmail(e)}>Remover</button>
              </li>
            ))}
          </ul>
        )}

        <form className="ccadd" onSubmit={handleAdicionarEmail}>
          <input
            type="email"
            placeholder="novo-email@empresa.com"
            value={novoEmail}
            onChange={(e) => setNovoEmail(e.target.value)}
            required
          />
          <button className="btn btn-primary btn-sm" type="submit">
            Adicionar
          </button>
        </form>
      </div>
    </>
  );
}
