import React, { useState } from 'react';

// Renders venue/in-play tactical insights (from the backend Insight Engine)
// as a standalone panel - NOT meant to be embedded in the live scoreboard.
// A point-in-time read like "52% below on-pace" is true for one ball and
// stale a moment later; sticking it under the live score misrepresents it
// as a persistent fact. This lives in its own Match Room view instead,
// where it reads as what it actually is: tactical analysis, not a stat.
export default function InsightPanel({ insights }) {
  const [expanded, setExpanded] = useState(false);

  if (!insights || insights.length === 0) {
    return (
      <div className="insight-deck">
        <div className="insight-deck-head">
          <span className="insight-deck-label">MATCH ROOM</span>
          <span className="insight-deck-sub">Venue &amp; in-play context, not a live score</span>
        </div>
        <div className="insight-empty">No tactical reads yet for this match.</div>
        <style>{panelStyles}</style>
      </div>
    );
  }

  // Pre-match venue context is a standing fact, not a moment - it stays
  // pinned separately rather than mixed into the chronological log below.
  const pregame = insights.find(i => i.type === 'venue_pregame_summary');
  const timeline = insights.filter(i => i.type !== 'venue_pregame_summary');

  // Newest first: the API appends as the match progresses, so reverse
  // for display so the most recent read is what you see without scrolling.
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
          <p className="insight-pregame-text">{pregame.text}</p>
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
                <div className="insight-timeline-text">{insight.text}</div>
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
  .insight-pregame-text {
    font-size: 13px;
    line-height: 1.6;
    color: rgba(240,242,245,0.85);
    margin: 6px 0 0;
  }
  .insight-timeline-row {
    padding: 8px 0;
  }
  .insight-timeline-row + .insight-timeline-row {
    border-top: 1px solid rgba(240,242,245,0.06);
  }
  .insight-timeline-text {
    font-size: 13px;
    line-height: 1.5;
    color: rgba(240,242,245,0.7);
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
