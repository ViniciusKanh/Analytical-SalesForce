export default function Toasts({ itens }) {
  return (
    <div id="toasts">
      {itens.map((t) => (
        <div key={t.id} className={"toast " + (t.tipo || "")}>
          {t.mensagem}
        </div>
      ))}
    </div>
  );
}
