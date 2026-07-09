import { useEffect, useRef } from "react";
import { Chart } from "chart.js/auto";

export default function TrendChart({ dias, metrica, rotulo }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!dias.length) {
      chartRef.current?.destroy();
      chartRef.current = null;
      return;
    }
    const [grupo, campo] = metrica.split(".");
    const labels = dias.map((d) => (d.date || "").slice(5));
    const valores = dias.map((d) => {
      const v = (d.metrics?.[grupo] || {})[campo];
      return typeof v === "number" ? v : v == null ? null : parseFloat(v);
    });
    const tinta = (getComputedStyle(document.documentElement).getPropertyValue("--muted") || "#6b7280").trim();

    chartRef.current?.destroy();
    chartRef.current = new Chart(canvasRef.current, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: rotulo,
            data: valores,
            borderColor: "#7c3aed",
            backgroundColor: "rgba(124,58,237,.16)",
            fill: true,
            tension: 0.35,
            spanGaps: true,
            pointRadius: 3,
            pointBackgroundColor: "#7c3aed",
          },
        ],
      },
      options: {
        plugins: { legend: { labels: { color: tinta } } },
        scales: {
          x: { ticks: { color: tinta }, grid: { display: false } },
          y: { ticks: { color: tinta }, grid: { color: "rgba(148,163,184,.15)" } },
        },
      },
    });
    return () => chartRef.current?.destroy();
  }, [dias, metrica, rotulo]);

  return <canvas ref={canvasRef} height="110"></canvas>;
}
