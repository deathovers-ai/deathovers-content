import React, { useState } from 'react';

/**
 * MATCH ROOM INFO CARD - full redesign (CTO-approved scope, this sprint)
 *
 * Section 1 (always visible): Toss result + Weather + Pitch Report.
 *   Toss is real (parsed server-side from Cricbuzz's matchInfo.status,
 *   archived once at toss-time - see app.py's _toss_archive). Weather and
 *   Pitch Report are PLACEHOLDERS - Cricbuzz's payload has no weather
 *   field (confirmed directly against live data) and pitch-character
 *   scoring was deliberately deferred (not enough signal in current data
 *   to label spin/pace/batting-friendly credibly). Placeholders render a
 *   clearly-labeled "not yet available" state, never a fabricated value.
 *
 * Sections 2-5 (Venue Record disclosure, all-time basis only - recency
 *   weighting was considered and deliberately dropped, see conversation
 *   history: pitch character changes are rare/slow, a 20-match recent
 *   window mostly adds noise from mixed tournaments/seasons rather than
 *   a real signal):
 *   2. Toss & Decision Record - toss lean, win% batting 1st/2nd
 *   3. Venue Score Record - highest/lowest/avg score
 *   4. Chase Record - highest successful chase, lowest defended
 *   5. Innings Score Range - explicit basis string, not just numbers
 *
 * Props:
 *   toss: { winner, decision } | null
 *   pregame: the venue_pregame_summary insight object from insight_engine.py
 *     - { headline, sample_size, toss_record, score_record, chase_record,
 *         score_range }, each sub-record itself possibly null if that
 *         section's data wasn't available.
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

function PlaceholderChip({ icon, label }) {
  return (
    <div className="info-chip info-chip-placeholder">
      <span className="info-chip-icon" aria-hidden="true">{icon}</span>
      <span className="info-chip-text info-chip-text-placeholder">{label}</span>
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

function RecordSection({ title, basis, pointers }) {
  if (!pointers || pointers.length === 0) return null;
  return (
    <div className="record-section">
      <div className="record-section-head">
        <span className="record-section-title">{title}</span>
        <span className="record-section-basis">{basis}</span>
      </div>
      <ul className="venue-pointer-list">
        {pointers.map((p, i) => (
          <li key={i} className="venue-pointer-row">
            <span className="venue-pointer-label">{p.label}</span>
            <span className="venue-pointer-value">{formatPointerValue(p)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScoreRangeSection({ scoreRange }) {
  if (!scoreRange) return null;
  return (
    <div className="record-section">
      <div className="record-section-head">
        <span className="record-section-title">Innings Score Range</span>
      </div>
      <div className="score-range-bar-wrap">
        <div className="score-range-values">
          <span className="score-range-low">{scoreRange.low}</span>
          <span className="score-range-high">{scoreRange.high}</span>
        </div>
        <div className="score-range-bar" aria-hidden="true">
          <div className="score-range-bar-fill" />
        </div>
      </div>
      <div className="record-section-basis score-range-basis">{scoreRange.basis}</div>
    </div>
  );
}

export default function MatchInfoCard({ toss, pregame }) {
  const [venueOpen, setVenueOpen] = useState(false);

  const hasToss = toss && toss.winner;
  const tossRecord = pregame?.toss_record;
  const scoreRecord = pregame?.score_record;
  const chaseRecord = pregame?.chase_record;
  const scoreRange = pregame?.score_range;
  const hasAnyVenueRecord = tossRecord || scoreRecord || chaseRecord || scoreRange;

  if (!hasToss && !hasAnyVenueRecord) return null;

  return (
    <div className="match-info-card">
      {/* --- Section 1: Toss / Weather / Pitch Report --- */}
      <div className="info-chip-row">
        {hasToss
          ? <TossChip toss={toss} />
          : <PlaceholderChip icon="🪙" label="Toss result not yet available" />}
        <PlaceholderChip icon="🌤️" label="Weather — coming soon" />
        <PlaceholderChip icon="🎯" label="Pitch report — coming soon" />
      </div>

      {/* --- Sections 2-5: Venue Record disclosure --- */}
      {hasAnyVenueRecord && (
        <div className="venue-disclosure">
          <button
            type="button"
            className="venue-disclosure-toggle"
            onClick={() => setVenueOpen(v => !v)}
            aria-expanded={venueOpen}
          >
            <span>Venue Record{pregame?.sample_size ? ` \u2014 ${pregame.sample_size} matches` : ''}</span>
            <span className={`venue-disclosure-caret ${venueOpen ? 'open' : ''}`} aria-hidden="true">▾</span>
          </button>

          {venueOpen && (
            <div className="venue-record-sections">
              {tossRecord && (
                <RecordSection
                  title="Toss & Decision Record"
                  basis={tossRecord.basis}
                  pointers={tossRecord.pointers}
                />
              )}
              {scoreRecord && (
                <RecordSection
                  title="Venue Score Record"
                  basis={scoreRecord.basis}
                  pointers={scoreRecord.pointers}
                />
              )}
              {chaseRecord && (
                <RecordSection
                  title="Chase Record"
                  basis={chaseRecord.basis}
                  pointers={chaseRecord.pointers}
                />
              )}
              <ScoreRangeSection scoreRange={scoreRange} />
            </div>
          )}
        </div>
      )}

      <style>{styles}</style>
    </div>
  );
}

const styles = `
  .match-info-card {
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

  .info-chip-placeholder {
    opacity: 0.5;
  }

  .info-chip-text-placeholder {
    font-style: italic;
  }

  .venue-disclosure {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(240,242,245,0.06);
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

  .venue-record-sections {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .record-section {
    background: rgba(0,0,0,0.15);
    border: 1px solid rgba(240,242,245,0.05);
    border-radius: 3px;
    padding: 10px 14px;
  }

  .record-section-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 8px;
  }

  .record-section-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.05em;
    font-weight: bold;
    color: rgba(240,242,245,0.75);
    text-transform: uppercase;
  }

  .record-section-basis {
    font-family: 'Inter', sans-serif;
    font-size: 10px;
    color: rgba(240,242,245,0.35);
    font-style: italic;
  }

  .venue-pointer-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .venue-pointer-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 3px 0;
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

  .score-range-bar-wrap {
    padding: 4px 0 2px;
  }

  .score-range-values {
    display: flex;
    justify-content: space-between;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: bold;
    color: #fff;
    margin-bottom: 6px;
  }

  .score-range-bar {
    height: 5px;
    border-radius: 3px;
    background: rgba(240,242,245,0.08);
    overflow: hidden;
  }

  .score-range-bar-fill {
    height: 100%;
    width: 100%;
    background: linear-gradient(90deg, var(--bail-amber, #F5A623), var(--blood-red, #E8003A));
    border-radius: 3px;
  }

  .score-range-basis {
    margin-top: 8px;
  }

  @media (max-width: 480px) {
    .info-chip-row {
      flex-direction: column;
      gap: 10px;
    }
    .record-section-head {
      flex-direction: column;
    }
  }
`;
