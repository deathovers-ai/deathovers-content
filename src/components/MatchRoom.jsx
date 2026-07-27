import React, { useState } from 'react';

/**
 * MATCH ROOM INFO CARD - full redesign (CTO-approved scope, this sprint)
 *
 * Section 1 (always visible): Toss result + Weather + Dew Alert (2nd
 *   innings, evening matches only) + Pitch Report placeholder.
 *   Toss and Weather are both REAL now:
 *     - Toss parsed server-side from Cricbuzz's matchInfo.status,
 *       archived once at toss-time (see app.py's _toss_archive).
 *     - Weather fetched from Open-Meteo (free, no key) using coordinates
 *       Cricbuzz already provides in matchInfo.venueInfo.latitude/
 *       longitude - no separate geocoding step. Fetched once pregame +
 *       once per innings change (see app.py's _weather_cache), not on
 *       every poll.
 *     - Dew Alert only appears for evening/night matches (local start
 *       hour >= 16) once in the 2nd innings, when humidity crosses a
 *       real threshold - computed server-side in weather_service.py's
 *       check_dew_risk(), never guessed client-side.
 *   Pitch Report remains a placeholder - deliberately deferred (see
 *   conversation history: not enough signal in current data to label
 *   spin/pace/batting-friendly credibly yet).
 *
 * Sections 2-5 (Venue Record disclosure, all-time basis only - recency
 *   weighting deliberately dropped, see conversation history: pitch
 *   character changes are rare/slow, a 20-match window mostly adds
 *   noise from mixed tournaments/seasons rather than a real signal):
 *   2. Toss & Decision Record - toss lean, win% batting 1st/2nd
 *   3. Venue Score Record - highest/lowest/avg score
 *   4. Chase Record - highest successful chase, lowest defended
 *   5. Innings Score Range - explicit basis string, not just numbers
 *
 * Props:
 *   toss: { winner, decision } | null
 *   weather: { condition, temp_c, humidity_pct, rain_probability_pct, is_rain_code_now } | null
 *   dewRisk: { risk: "HIGH"|"MODERATE", reason: string } | null
 *   pregame: the venue_pregame_summary insight object from insight_engine.py
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

const CONDITION_ICONS = {
  'Clear': '☀️',
  'Mainly Clear': '🌤️',
  'Partly Cloudy': '⛅',
  'Overcast': '☁️',
  'Fog': '🌫️',
  'Light Drizzle': '🌦️', 'Drizzle': '🌦️', 'Heavy Drizzle': '🌧️',
  'Freezing Drizzle': '🌧️',
  'Light Rain': '🌧️', 'Rain': '🌧️', 'Heavy Rain': '🌧️',
  'Freezing Rain': '🌨️',
  'Light Snow': '🌨️', 'Snow': '❄️', 'Heavy Snow': '❄️', 'Snow Grains': '❄️',
  'Rain Showers': '🌧️', 'Violent Showers': '⛈️',
  'Snow Showers': '🌨️',
  'Thunderstorm': '⛈️',
};

function WeatherChip({ weather }) {
  if (!weather || !weather.condition) return null;
  const icon = CONDITION_ICONS[weather.condition] || '🌤️';
  const parts = [weather.condition];
  if (weather.temp_c != null) parts.push(`${Math.round(weather.temp_c)}°C`);
  return (
    <div className="info-chip">
      <span className="info-chip-icon" aria-hidden="true">{icon}</span>
      <span className="info-chip-text">
        {parts.join(', ')}
        {weather.rain_probability_pct != null && weather.rain_probability_pct >= 30 && (
          <span className="rain-probability"> · {weather.rain_probability_pct}% rain chance</span>
        )}
      </span>
    </div>
  );
}

function DewAlertChip({ dewRisk }) {
  if (!dewRisk || !dewRisk.risk) return null;
  return (
    <div className={`info-chip dew-alert dew-alert-${dewRisk.risk.toLowerCase()}`}>
      <span className="info-chip-icon" aria-hidden="true">💧</span>
      <span className="info-chip-text">{dewRisk.reason}</span>
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

export default function MatchInfoCard({ toss, weather, dewRisk, pregame }) {
  const [venueOpen, setVenueOpen] = useState(false);

  const hasToss = toss && toss.winner;
  const tossRecord = pregame?.toss_record;
  const scoreRecord = pregame?.score_record;
  const chaseRecord = pregame?.chase_record;
  const scoreRange = pregame?.score_range;
  const hasAnyVenueRecord = tossRecord || scoreRecord || chaseRecord || scoreRange;

  if (!hasToss && !weather && !hasAnyVenueRecord) return null;

  return (
    <div className="match-info-card">
      {/* --- Section 1: Toss / Weather / Dew Alert / Pitch Report --- */}
      <div className="info-chip-row">
        {hasToss
          ? <TossChip toss={toss} />
          : <PlaceholderChip icon="🪙" label="Toss result not yet available" />}
        {weather
          ? <WeatherChip weather={weather} />
          : <PlaceholderChip icon="🌤️" label="Weather not yet available" />}
        <DewAlertChip dewRisk={dewRisk} />
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

  .rain-probability {
    color: rgba(240,242,245,0.5);
  }

  .dew-alert {
    padding: 4px 10px;
    border-radius: 3px;
  }

  .dew-alert-high {
    background: rgba(232,0,58,0.1);
    border: 1px solid rgba(232,0,58,0.25);
  }
  .dew-alert-high .info-chip-text {
    color: #ff8fa3;
  }

  .dew-alert-moderate {
    background: rgba(245,166,35,0.1);
    border: 1px solid rgba(245,166,35,0.25);
  }
  .dew-alert-moderate .info-chip-text {
    color: var(--bail-amber, #F5A623);
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
