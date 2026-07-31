import React, { useState } from 'react';

// Renders venue/in-play tactical insights (from the backend Insight Engine)
// as a standalone panel - NOT meant to be embedded in the live scoreboard.
//
// UPDATED: backend now sends structured { headline, pointers: [{label, value, unit, pct}] }
// instead of a single prose `text` string. Every stat is rendered as its own
// row (label + value), and any % is always shown alongside its underlying
// number - never a lone percentage.
export default function InsightPanel({ insights }) {
  const [expanded, setExpanded] = useState(false);

  if (!insights || insights.length === 0) {
    return (
      <div className="insight-deck">
        <div className="insight-deck-head">
          <span className="insight-deck-label">MATCH ROOM</span>
          <span className="insight-deck-sub">Venue &amp; in-play context, not a live score</span>
        </div>
        <div className="insight-empty">
          No tactical reads yet. Venue-linked insights appear once this ground is in our database; scoreline snapshots populate as soon as the scorecard loads.
        </div>
        <style>{panelStyles}</style>
      </div>
    );
  }

  const pregame = insights.find(i => i.type === 'venue_pregame_summary');
  const timeline = insights.filter(i => i.type !== 'venue_pregame_summary');

  const timelineDesc = [...timeline].reverse();
  const visibleTimeline = expanded ? timelineDesc : timelineDesc.slice(0, 3);

  return (
    <div className="insight-deck">
      <div className="insight-deck-head">
        <span className="insight-deck-label">MATCH ROOM</span>
        <span className="insight-deck-sub">Venue &amp; in-play context, not a live score</span>
      </div>

      {pregame && (
        <div className="insight-pregame">
          <div className="stat-kicker">BEFORE A BALL IS BOWLED</div>
          <PointerBlock headline={pregame.headline} pointers={pregame.pointers} />
        </div>
      )}

      {timelineDesc.length > 0 && (
        <>
          <div className="stat-kicker" style={{ marginTop: pregame ? '16px' : '0' }}>
            AS THE MATCH DEVELOPED
          </div>
          <div className="insight-timeline">
            {visibleTimeline.map((insight, i) => (
              <div key={i} className="insight-timeline-row">
                <PointerBlock headline={insight.headline} pointers={insight.pointers} gauge={insight.gauge} />
              </div>
            ))}
          </div>
          {timelineDesc.length > 3 && (
            <button
              type="button"
              className="stat-more stat-more-btn"
              onClick={() => setExpanded(v => !v)}
            >
              {expanded ? 'show less' : `+${timelineDesc.length - 3} more`}
            </button>
          )}
        </>
      )}

      <style>{panelStyles}</style>
    </div>
  );
}

// Formats a pointer value: if a % is present, always pair it with the
// underlying number - never render a lone percentage.
function formatPointerValue(p) {
  const sign = p.pct !== undefined && p.pct !== null && p.pct > 0 ? '+' : '';
  if (p.pct !== undefined && p.pct !== null) {
    return `${p.value}${p.unit || ''}  (${sign}${p.pct}%)`;
  }
  return `${p.value}${p.unit || ''}`;
}

function PointerBlock({ headline, pointers, gauge }) {
  return (
    <div className="pointer-block">
      {headline && <div className="pointer-headline">{headline}</div>}
      {gauge && (
        <span className={`pointer-gauge gauge-${gauge.level?.toLowerCase()}`}>
          {gauge.level}
        </span>
      )}
      {pointers && pointers.length > 0 && (
        <ul className="pointer-list">
          {pointers.map((p, i) => (
            <li key={i} className="pointer-row">
              <span className="pointer-label">{p.label}</span>
              <span className="pointer-value">{formatPointerValue(p)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const panelStyles = `
  .insight-deck {
    max-width: 1050px;
    margin: 0 auto;
    background: var(--outfield, #16191F);
    border: 1px solid rgba(240,242,245,0.08);
    border-radius: 4px;
    padding: 20px 24px;
  }
  .insight-deck-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px solid rgba(240,242,245,0.08);
    padding-bottom: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 6px;
  }
  .insight-deck-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    font-weight: bold;
    color: var(--bail-amber, #F5A623);
  }
  .insight-deck-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: rgba(240,242,245,0.4);
  }
  .insight-empty {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: rgba(240,242,245,0.4);
    padding: 24px 0;
    text-align: center;
  }
  .stat-kicker {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: rgba(240,242,245,0.5);
    font-weight: bold;
    margin-bottom: 8px;
  }
  .insight-timeline-row {
    padding: 10px 0;
  }
  .insight-timeline-row + .insight-timeline-row {
    border-top: 1px solid rgba(240,242,245,0.06);
  }

  /* Pointer block - shared by pregame + timeline entries */
  .pointer-headline {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 16px;
    letter-spacing: 0.01em;
    color: #fff;
    margin-bottom: 6px;
  }
  .pointer-gauge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 0.06em;
    padding: 2px 8px;
    border-radius: 3px;
    margin-bottom: 8px;
  }
  .gauge-low { color: #4ade80; background: rgba(74,222,128,0.1); }
  .gauge-moderate { color: #facc15; background: rgba(250,204,21,0.1); }
  .gauge-high { color: #fb923c; background: rgba(251,146,60,0.1); }
  .gauge-critical { color: var(--blood-red, #E8003A); background: rgba(232,0,58,0.1); }

  .pointer-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .pointer-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 3px 0;
    font-size: 13px;
    line-height: 1.5;
  }
  .pointer-label {
    color: rgba(240,242,245,0.6);
    font-family: 'Inter', sans-serif;
  }
  .pointer-value {
    color: rgba(240,242,245,0.95);
    font-family: 'JetBrains Mono', monospace;
    font-weight: bold;
    white-space: nowrap;
    margin-left: 16px;
  }

  .stat-more-btn {
    background: none;
    border: none;
    color: var(--bail-amber, #F5A623);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    cursor: pointer;
    padding: 8px 0 0;
  }
  .stat-more-btn:hover { color: #fff; }
`;
