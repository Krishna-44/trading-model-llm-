/** Expiry payoff curve for an option strategy — profit (green) vs loss (red)
 *  across the underlying price, with the zero line and a spot marker. */
export function PayoffChart({ payoff, spot }: { payoff: { s: number; p: number }[]; spot: number }) {
  if (!payoff || payoff.length < 2) return null;
  const W = 220, H = 56;
  const ss = payoff.map((d) => d.s), ps = payoff.map((d) => d.p);
  const sMin = Math.min(...ss), sMax = Math.max(...ss), sSpan = sMax - sMin || 1;
  const pMin = Math.min(...ps), pMax = Math.max(...ps), pSpan = pMax - pMin || 1;
  const x = (s: number) => ((s - sMin) / sSpan) * W;
  const y = (p: number) => H - ((p - pMin) / pSpan) * H;
  const zeroY = y(0);
  const spotX = x(spot);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-14 mt-1" preserveAspectRatio="none">
      {pMin < 0 && pMax > 0 && (
        <line x1="0" y1={zeroY} x2={W} y2={zeroY} stroke="var(--border)" strokeWidth="1" strokeDasharray="3 3" />
      )}
      {spotX >= 0 && spotX <= W && (
        <line x1={spotX} y1="0" x2={spotX} y2={H} stroke="var(--foreground)" strokeOpacity="0.25" strokeWidth="1" />
      )}
      {payoff.slice(1).map((d, i) => {
        const a = payoff[i];
        const up = (a.p + d.p) / 2 >= 0;
        return (
          <line key={i} x1={x(a.s)} y1={y(a.p)} x2={x(d.s)} y2={y(d.p)}
            stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.5" />
        );
      })}
    </svg>
  );
}
