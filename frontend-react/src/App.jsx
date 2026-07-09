import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Topbar from "./components/Topbar.jsx";
import RunModal from "./components/RunModal.jsx";
import Toasts from "./components/Toasts.jsx";
import Dashboard from "./views/Dashboard.jsx";
import Opportunities from "./views/Opportunities.jsx";
import Leads from "./views/Leads.jsx";
import Tasks from "./views/Tasks.jsx";
import Satisfaction from "./views/Satisfaction.jsx";
import Cancellations from "./views/Cancellations.jsx";
import Alerts from "./views/Alerts.jsx";
import Trends from "./views/Trends.jsx";
import Report from "./views/Report.jsx";
import Config from "./views/Config.jsx";
import { verificarSaude, listarDias, buscarDia, rodarAgente } from "./api.js";

let proximoIdToast = 1;

export default function App() {
  const [view, setView] = useState("dashboard");
  const [sidebarAberta, setSidebarAberta] = useState(false);
  const [tema, setTema] = useState(localStorage.getItem("af_theme") === "dark" ? "dark" : "light");
  const [online, setOnline] = useState(null);
  const [dias, setDias] = useState([]);
  const [dia, setDia] = useState(null);
  const [runModalAberto, setRunModalAberto] = useState(false);
  const [executando, setExecutando] = useState(false);
  const [segundos, setSegundos] = useState(0);
  const [toasts, setToasts] = useState([]);
  const timerRef = useRef(null);

  const notificar = useCallback((mensagem, tipo) => {
    const id = proximoIdToast++;
    setToasts((t) => [...t, { id, mensagem, tipo }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tema);
  }, [tema]);

  const checarSaude = useCallback(async () => {
    try {
      await verificarSaude();
      setOnline(true);
    } catch {
      setOnline(false);
    }
  }, []);

  const carregarDia = useCallback(
    async (data) => {
      if (!data || data === "—") return;
      try {
        const d = await buscarDia(data);
        setDia(d);
      } catch (e) {
        notificar("Falha ao carregar o dia: " + e.message, "bad");
      }
    },
    [notificar]
  );

  const carregarDias = useCallback(async () => {
    try {
      const d = await listarDias();
      const lista = d.dates || [];
      setDias(lista);
      if (lista.length && (!dia || !lista.includes(dia.date))) {
        carregarDia(lista[0]);
      }
    } catch {
      /* mantém a tela anterior; o indicador "Offline" já avisa. */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dia]);

  useEffect(() => {
    checarSaude();
    carregarDias();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function irPara(v) {
    setView(v);
    setSidebarAberta(false);
  }

  function alternarTema() {
    const novo = tema === "dark" ? "light" : "dark";
    setTema(novo);
    localStorage.setItem("af_theme", novo);
  }

  function recarregar() {
    carregarDias();
    if (dia) carregarDia(dia.date);
    notificar("Atualizando…");
  }

  async function executarAgente(payload) {
    setExecutando(true);
    setSegundos(0);
    timerRef.current = setInterval(() => setSegundos((s) => s + 1), 1000);
    try {
      const resultado = await rodarAgente(payload);
      setDia(resultado);
      notificar("Execução concluída ✓", "ok");
      setRunModalAberto(false);
      carregarDias();
    } catch (e) {
      notificar("Falha: " + e.message, "bad");
    } finally {
      clearInterval(timerRef.current);
      setExecutando(false);
      checarSaude();
    }
  }

  function renderView() {
    if (view === "config") return <Config notificar={notificar} onConfigSalva={() => { checarSaude(); carregarDias(); }} />;
    if (view === "tendencias") return <Trends />;
    if (!dia) {
      return (
        <div className="card">
          <div className="empty">
            Nenhum dia carregado.
            <br />
            <br />
            Clique em <b>▶ Rodar</b> para gerar o primeiro relatório, ou selecione um dia salvo no topo.
          </div>
        </div>
      );
    }
    switch (view) {
      case "dashboard":
        return <Dashboard dia={dia} onVerAlertas={() => irPara("alertas")} />;
      case "oportunidades":
        return <Opportunities dia={dia} />;
      case "leads":
        return <Leads dia={dia} />;
      case "tarefas":
        return <Tasks dia={dia} />;
      case "satisfacao":
        return <Satisfaction dia={dia} />;
      case "cancelamentos":
        return <Cancellations dia={dia} />;
      case "alertas":
        return <Alerts dia={dia} />;
      case "relatorio":
        return <Report dia={dia} />;
      default:
        return <div className="empty">—</div>;
    }
  }

  return (
    <div className="app">
      <Sidebar view={view} onNavigate={irPara} aberta={sidebarAberta} />
      <div className="mainwrap">
        <Topbar
          view={view}
          online={online}
          dias={dias}
          diaAtual={dia?.date}
          onSelecionarDia={carregarDia}
          onRecarregar={recarregar}
          onAlternarTema={alternarTema}
          tema={tema}
          onAbrirRun={() => setRunModalAberto(true)}
          onAlternarSidebar={() => setSidebarAberta((v) => !v)}
        />
        <main>{renderView()}</main>
        <div className="integr">
          <span>Integrações</span>
          <img src="https://upload.wikimedia.org/wikipedia/commons/f/f9/Salesforce.com_logo.svg" style={{ height: 16 }} alt="Salesforce" title="Salesforce" />
          <img src="https://cdn.simpleicons.org/turso/4FF8D2" alt="Turso" title="Turso" />
          <img src="https://cdn.simpleicons.org/huggingface/FFD21E" alt="Hugging Face" title="Hugging Face" />
          <img src="https://cdn.simpleicons.org/clickup/7B68EE" alt="ClickUp" title="ClickUp" />
          <img src="https://cdn.simpleicons.org/gmail/EA4335" alt="Gmail" title="Gmail" />
          <img src="https://cdn.simpleicons.org/fastapi/009688" alt="FastAPI" title="FastAPI" />
        </div>
      </div>
      <RunModal
        aberto={runModalAberto}
        onFechar={() => setRunModalAberto(false)}
        onExecutar={executarAgente}
        executando={executando}
        segundos={segundos}
      />
      <Toasts itens={toasts} />
    </div>
  );
}
