export function Gauge({ value, threshold = 62, label }: { value: number; threshold?: number; label?: string }) {
  const v = Math.max(0, Math.min(100, value || 0));
  const r = 70;
  const c = 2 * Math.PI * r;
  const arc = (c * 270) / 360;
  const offset = arc * (1 - v / 100);
  const tickAngle = (threshold / 100) * 270 - 135;

  return (
    <div className="relative w-full flex items-center justify-center">
      <svg viewBox="0 0 200 180" className="w-full max-w-[260px]">
        <defs>
          <linearGradient id="gaugeGrad" x1="0" x2="1">
            <stop offset="0%" stopColor="#f43f5e" />
            <stop offset="50%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>
        </defs>
        <g transform="translate(100 100) rotate(135)">
          <circle r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={14} strokeDasharray={`${arc} ${c}`} strokeLinecap="round" />
          <circle r={r} fill="none" stroke="url(#gaugeGrad)" strokeWidth={14} strokeDasharray={`${arc} ${c}`} strokeDashoffset={offset} strokeLinecap="round" style={{ transition: "stroke-dashoffset 600ms ease" }} />
        </g>
        <g transform={`translate(100 100) rotate(${tickAngle})`}>
          <line x1={0} y1={-r - 10} x2={0} y2={-r + 10} stroke="#22d3ee" strokeWidth={2} />
        </g>
        <text x={100} y={92} textAnchor="middle" className="num" fill="currentColor" fontSize={32} fontWeight={700}>{v.toFixed(0)}%</text>
        {label && <text x={100} y={115} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={11}>{label}</text>}
        <text x={100} y={148} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize={9}>threshold {threshold}%</text>
      </svg>
    </div>
  );
}
