const candles = [[0,345,28],[22,330,32],[46,312,30],[204,294,26],[227,285,24],[249,270,26],[273,263,26],[298,253,25],[320,263,29],[342,252,26],[365,239,30],[388,219,31],[410,201,32],[434,210,28],[493,118,30],[517,102,27],[540,73,32],[564,67,35],[587,72,27],[609,34,30]];
export function MarketIllustration() {
  return <figure className="market-illustration" aria-label="Decorative market illustration. Demonstration prices, not a market feed.">
    <svg viewBox="0 0 610 420" preserveAspectRatio="none" aria-hidden="true" className="market-canvas">
      <path className="market-wave" d="M0 183C128 100 185 285 310 264S460 162 610 249V420H0Z" />
      <path className="market-wave pale" d="M0 325C170 375 174 219 295 247S480 378 610 293V420H0Z" />
      <g className="candles">{candles.map(([x=0,y=0,h=0],i) => <g key={i} className={i % 4 === 1 ? 'gold-candle' : 'blue-candle'}>
        <path d={`M${x+6} ${y-15}v${h+32}`} /><rect x={x} y={y} width="12" height={h} />
      </g>)}</g>
      <path className="market-curve" d="M40 420C134 363 121 337 201 340S294 298 341 253S401 278 463 268S541 179 618 163" pathLength="1" />
    </svg>
    <div className="quote-card quote-eur" aria-hidden="true"><span>EUR/USD</span><strong><i>▲</i> 1.1258</strong><small>+0.42%</small></div>
    <div className="quote-card quote-gold" aria-hidden="true"><span>XAU/USD</span><strong>2,336.50</strong><small>▲+0.18%</small></div>
    <figcaption>Illustrative market data</figcaption>
  </figure>;
}
