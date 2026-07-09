// Camada de acesso à API do Analytical-Force (FastAPI).
//
// Mantém o mesmo contrato do painel HTML anterior: a URL base e a chave de
// API (X-API-Key) ficam no localStorage do navegador — não há segredo
// embutido no build. Este arquivo só faz chamadas HTTP; nenhum cálculo de
// métrica é feito aqui (isso é responsabilidade do backend em Python).

const CHAVE_BASE = "af_base";
const CHAVE_KEY = "af_key";
const BASE_PADRAO = "https://viniciuskhan-analytical-force.hf.space";

export function getBaseUrl() {
  return (localStorage.getItem(CHAVE_BASE) || BASE_PADRAO).replace(/\/+$/, "");
}

export function setBaseUrl(url) {
  localStorage.setItem(CHAVE_BASE, url.trim());
}

export function getApiKey() {
  return localStorage.getItem(CHAVE_KEY) || "";
}

export function setApiKey(key) {
  localStorage.setItem(CHAVE_KEY, key.trim());
}

function headers() {
  const h = { "Content-Type": "application/json" };
  const k = getApiKey();
  if (k) h["X-API-Key"] = k;
  return h;
}

async function requisicao(caminho, opcoes = {}) {
  const resp = await fetch(getBaseUrl() + caminho, {
    ...opcoes,
    headers: { ...headers(), ...(opcoes.headers || {}) },
  });
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detalhe = typeof dados.detail === "string" ? dados.detail : JSON.stringify(dados.detail || dados);
    const erro = new Error(`Erro ${resp.status}: ${detalhe}`);
    erro.status = resp.status;
    throw erro;
  }
  return dados;
}

export async function verificarSaude() {
  const resp = await fetch(getBaseUrl() + "/health");
  if (!resp.ok) throw new Error("offline");
  return resp.json();
}

export const listarDias = () => requisicao("/days");
export const buscarDia = (data) => requisicao("/day/" + encodeURIComponent(data));
export const buscarHistorico = (dias) => requisicao("/history?days=" + dias);
export const buscarConfigCheck = () => requisicao("/config/check");

export const rodarAgente = (payload) =>
  requisicao("/run", { method: "POST", body: JSON.stringify(payload) });

// E-mails em cópia (Cc) — persistidos no Turso via ConfigRepository/agent_config.
export const listarEmailsCc = () => requisicao("/config/email-cc");
export const adicionarEmailCc = (email) =>
  requisicao("/config/email-cc", { method: "POST", body: JSON.stringify({ email }) });
export const removerEmailCc = (email) =>
  requisicao("/config/email-cc/" + encodeURIComponent(email), { method: "DELETE" });

// Consulta (busca/detalhe híbrida: cache Turso + Salesforce ao vivo).
// Somente leitura — espelha os tipos configurados em src/query/search_service.py.
export const consultaTipos = () => requisicao("/consulta/tipos");

export const consultaBuscar = (termo, tipos, limite = 20) => {
  const params = new URLSearchParams({ termo, limite: String(limite) });
  if (tipos && tipos.length) params.set("tipos", tipos.join(","));
  return requisicao("/consulta/busca?" + params.toString());
};

export const consultaDetalhar = (tipo, recordId) =>
  requisicao("/consulta/objeto/" + encodeURIComponent(tipo) + "/" + encodeURIComponent(recordId));
