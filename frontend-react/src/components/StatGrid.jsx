// Grade de KPIs. Recebe uma lista de [icone, rotulo, valorFormatado, classeCor].
// Os valores já vêm formatados (pt-BR) pelas views — este componente só exibe.
export default function StatGrid({ itens }) {
  return (
    <div className="kpis">
      {itens.map(([icone, rotulo, valor, cls], i) => (
        <div className={"kpi " + (cls || "")} key={i}>
          <div className="ic">{icone}</div>
          <div className="lab">{rotulo}</div>
          <div className="val">{valor}</div>
        </div>
      ))}
    </div>
  );
}
