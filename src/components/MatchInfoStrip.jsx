import React, { useState } from 'react';

/**
 * MATCH INFO STRIP
 * Replaces the old always-expanded, prose-paragraph pregame venue block.
 * Toss result stays visible throughout the match (it's a fixed fact people
 * reference all match long - "why is X batting first"). Venue record
 * (toss %, win %, chase history) moves behind a disclosure - reference
 * material you dip into, not a wall of numbers you stare at every time
 * you open the Match Room.
 *
 * NOTE: weather was scoped originally but confirmed NOT available in the
 * Cricbuzz RapidAPI payload this backend uses (checked matchInfo directly
 * against live matches - no weather field present anywhere in the
 * response). Dropped rather than shipped as a fake/always-empty field.
 * If a future weather source is added, re-introduce the chip then.
 *
 * Props:
 *   toss: { winner: string, decision: "bat"|"bowl" } | null
 *   venuePointers: [{label, value, unit?, pct?}] - the existing pregame
 *     pointer list (toss %, win %, chase records etc), now tucked behind
 *     the disclosure instead of always shown inline.
 */

function TossChip({ toss }) {
  if (!toss || !toss.winner) return null;
  const decisionLabel = toss.decision === 'bat' ? 'elected to bat' : 'elected to bowl';
  return (
    <div className="info-chip">
      <span className="info-chip-icon" aria-hidden="true">🪙</span>
      <span className="info-chip-text">
        <strong>{toss.winner}</strong> won the toss, {decisionLabel}
      </span>
    </div>
  );
}

function formatPointerValue(p) {
  const sign = p.pct !== undefined && p.pct !== null && p.pct > 0 ? '+' : '';
  if (p.pct !== undefined && p.pct !== null) {
    return `${p.value}${p.unit || ''}  (${sign}${p.pct}%)`;
  }
  return `${p.value}${p.unit || ''}`;
}

export default function MatchInfoStrip({ toss, venuePointers }) {
  const [venueOpen, setVenueOpen] = useState(false);

  const hasToss = toss && toss.winner;
  const hasVenuePointers = venuePointers && venuePointers.length > 0;

  if (!hasToss && !hasVenuePointers) return null;

  return (
    <div className="match-info-strip">
      {hasToss && (
        <div className="info-chip-row">
          <TossChip toss={toss} />
        </div>
      )}

      {hasVenuePointers && (
        <div className="venue-disclosure">
          <button
            type="button"
            className="venue-disclosure-toggle"
            onClick={() => setVenueOpen(v => !v)}
            aria-expanded={venueOpen}
          >
            <span>Venue Record</span>
            <span className={`venue-disclosure-caret ${venueOpen ? 'open' : ''}`} aria-hidden="true">▾</span>
          </button>
          {venueOpen && (
            <ul className="venue-pointer-list">
              {venuePointers.map((p, i) => (
                <li key={i} className="venue-pointer-row">
                  <span className="venue-pointer-label">{p.label}</span>
                  <span className="venue-pointer-value">{formatPointerValue(p)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .match-info-strip {
    max-width: 1050px;
    margin: 0 auto 16px;
    background: var(--outfield, #16191F);
    border: 1px solid rgba(240,242,245,0.08);
    border-radius: 4px;
    padding: 14px 20px;
  }

  .info-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
  }

  .info-chip {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .info-chip-icon {
    font-size: 16px;
    line-height: 1;
  }

  .info-chip-text {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    color: rgba(240,242,245,0.85);
    line-height: 1.3;
  }

  .info-chip-text strong {
    color: #fff;
    font-weight: 700;
  }

  .venue-disclosure {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(240,242,245,0.06);
  }

  .info-chip-row + .venue-disclosure {
    margin-top: 12px;
  }

  .venue-disclosure-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.06em;
    font-weight: bold;
    color: var(--bail-amber, #F5A623);
    text-transform: uppercase;
  }

  .venue-disclosure-toggle:hover { color: #fff; }

  .venue-disclosure-caret {
    display: inline-block;
    transition: transform 0.15s ease;
    font-size: 10px;
  }
  .venue-disclosure-caret.open { transform: rotate(180deg); }

  .venue-pointer-list {
    list-style: none;
    margin: 10px 0 0;
    padding: 0;
  }

  .venue-pointer-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 4px 0;
    font-size: 13px;
    line-height: 1.5;
  }
  .venue-pointer-row + .venue-pointer-row {
    border-top: 1px solid rgba(240,242,245,0.04);
  }

  .venue-pointer-label {
    color: rgba(240,242,245,0.6);
    font-family: 'Inter', sans-serif;
  }

  .venue-pointer-value {
    color: rgba(240,242,245,0.95);
    font-family: 'JetBrains Mono', monospace;
    font-weight: bold;
    white-space: nowrap;
    margin-left: 16px;
  }

  @media (max-width: 480px) {
    .info-chip-row {
      flex-direction: column;
      gap: 10px;
    }
  }
`;
