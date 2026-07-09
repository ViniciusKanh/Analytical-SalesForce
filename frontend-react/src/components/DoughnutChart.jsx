import { useEffect, useRef } from "react";
import { Chart } from "chart.js/auto";

const COR = { high: "#ef4444", medium: "#f59e0b", low: "#eab308" };

// Doughnut de alertas por severidade. Os totais já vêm calculados
// (contagem simples no front, sem métrica de negócio nova).
export default function DoughnutChart({ alertas }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const contagem = { high: 0, medium: 0, low: 0 };
    (alertas || []).forEach((a) => {
      if (contagem[a.severity] != null) contagem[a.severity]++;
    });
    const tinta = (getComputedStyle(document.documentElement).getPropertyValue("--muted") || "#6b7280").trim();

    if (chartRef.current) chartRef.current.destroy();
    chartRef.current = new Chart(canvasRef.current, {
      type: "doughnut",
      data: {
        labels: ["Alta", "Média", "Baixa"],
        datasets: [
          {
            data: [contagem.high, contagem.medium, contagem.low],
            backgroundColor: [COR.high, COR.medium, COR.low],
            borderWidth: 0,
          },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom", labels: { color: tinta, boxWidth: 12 } } },
        cutout: "66%",
        animation: { animateScale: true },
      },
    });
    return () => chartRef.current?.destroy();
  }, [alertas]);

  return <canvas ref={canvasRef} height="210"></canvas>;
}
