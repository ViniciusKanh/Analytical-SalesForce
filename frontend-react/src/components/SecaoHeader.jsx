export default function SecaoHeader({ icone, titulo, cor, extra }) {
  return (
    <div className="sec-h">
      <div className="sh-left">
        <span className="sh-ic" style={{ background: cor }}>
          {icone}
        </span>
        <h2>{titulo}</h2>
      </div>
      {extra || null}
    </div>
  );
}
