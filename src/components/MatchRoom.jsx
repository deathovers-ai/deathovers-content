import React, { useEffect, useState } from 'react';
import MatchInfoCard from './MatchInfoStrip.jsx';
import InsightPanel from './InsightPanel.jsx';

const MATCH_API = 'https://deathovers-ai-engine.onrender.com/api/match-details';

export default function MatchRoom() {
  const [matchId, setMatchId] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id');
    if (!id) {
      setError('No match specified. Open a live match from the home page.');
      setLoading(false);
      return;
    }
    setMatchId(id);
  }, []);

  useEffect(() => {
    if (!matchId) return undefined;
    let cancelled = false;

    async function fetchDetails() {
      try {
        const response = await fetch(`${MATCH_API}/${matchId}`);
        if (!response.ok) throw new Error(`Server returned ${response.status}`);
        const nextData = await response.json();
        if (!cancelled) {
          setData(nextData);
          setError(null);
          setLoading(false);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setError(fetchError.message || 'Failed to load match data');
          setLoading(false);
        }
      }
    }

    fetchDetails();
    const interval = window.setInterval(fetchDetails, 30000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [matchId]);

  const insights = data?.intelligence?.insights || [];
  const pregame = insights.find((insight) => insight.type === 'venue_pregame_summary');
  const timelineInsights = insights.filter((insight) => insight.type !== 'venue_pregame_summary');
  const team1 = data?.innings?.[0]?.team;
  const team2 = data?.innings?.[1]?.team;

  return (
    <main className="match-room">
      <header className="match-room-header room-enter">
        <a href="/" className="back-link">&lt;- BACK TO LIVE</a>
        <div className="room-title-row">
          <div>
            <p className="eyebrow"><i aria-hidden="true" /> LIVE MATCH ROOM</p>
            <h1 className="match-room-title">
              {team1 || 'MATCH'} <span>vs</span> {team2 || 'ROOM'}
            </h1>
          </div>
          <p className="room-purpose">Live chase decisions, grounded in the current score and comparable chases.</p>
        </div>
      </header>

      {loading && <StatusCard label="Loading live match context" />}
      {error && <StatusCard label={`Couldn't load this match: ${error}`} error />}

      {!loading && !error && (
        <div className="room-stack">
          <ChasePanel chase={data?.chase} />
          <MatchInfoCard toss={data?.toss} weather={data?.weather} dewRisk={data?.dewRisk} pregame={pregame} />
          <InsightPanel insights={timelineInsights} />
        </div>
      )}

      <style>{styles}</style>
    </main>
  );
}

function StatusCard({ label, error = false }) {
  return <div className={`room-status ${error ? 'room-status-error' : ''}`}><span>{label}</span></div>;
}

function ChasePanel({ chase }) {
  const state = chase?.state;
  if (!state) return null;

  if (chase.status !== 'qualified') {
    const waiting = chase.status === 'awaiting_historical_cohort';
    return (
      <section className="chase-card chase-card-pending room-enter">
        <div className="chase-card-topline"><span className="engine-live-dot" /> CHASE ENGINE</div>
        <h2>{waiting ? 'BUILDING THE HISTORICAL READ' : 'HISTORICAL READ NOT AVAILABLE'}</h2>
        <p>The live score is ready. We will only show a comparison after a qualified historical cohort is available.</p>
        <ScoreStrip state={state} />
      </section>
    );
  }

  const cohort = chase.cohort;
  const ahead = (cohort.pace_gap_runs || 0) >= 0;
  const verdict = ahead ? 'AHEAD OF HISTORICAL PACE' : 'BEHIND HISTORICAL PACE';
  const paceText = formatSigned(cohort.pace_gap_runs, ' runs');
  const wicketText = formatSigned(cohort.wicket_gap, ' vs par');
  const firstInnings = chase.first_innings;
  const scope = cohort.venue_scope ? 'Venue-specific cohort' : 'Format-wide fallback';

  return (
    <section className={`chase-card ${ahead ? 'chase-card-ahead' : 'chase-card-behind'} room-enter`}>
      <div className="chase-card-topline"><span className="engine-live-dot" /> CHASE ENGINE <span className="engine-refresh">UPDATES LIVE</span></div>
      <div className="chase-hero">
        <div>
          <p className="chase-kicker">HISTORICAL CHASE PATH</p>
          <h2>{verdict}</h2>
          <p className="chase-summary">
            At this point in comparable chases, this innings is {ahead ? 'ahead' : 'behind'} the successful pace line.
          </p>
        </div>
        <div className="recovery-orb" aria-label={`${Math.round(cohort.recovery_rate * 100)} percent historical recovery rate`}>
          <strong>{Math.round(cohort.recovery_rate * 100)}%</strong><span>RECOVERY</span>
        </div>
      </div>

      <ScoreStrip state={state} />

      <div className="chase-metrics">
        <Metric label="Pace gap" value={paceText} emphasis={ahead ? 'positive' : 'negative'} />
        <Metric label="Wicket par" value={cohort.average_successful_wickets == null ? '-' : `${cohort.average_successful_wickets.toFixed(1)} wkts`} detail={wicketText} />
        <Metric label="Comparable chases" value={`${cohort.sample_size}`} detail={`${cohort.wins} successful`} />
        <Metric label="Evidence" value={scope} compact />
      </div>

      {firstInnings && (
        <div className="innings-context">
          <span>1ST INNINGS CONTEXT</span>
          <strong>{firstInnings.runs}/{firstInnings.wickets}</strong>
          <small>Target {state.target} · held only for this match</small>
        </div>
      )}
    </section>
  );
}

function ScoreStrip({ state }) {
  return (
    <div className="score-strip">
      <div><span>CHASE SCORE</span><strong>{state.runs}/{state.wickets}</strong></div>
      <div><span>TO WIN</span><strong>{state.runs_required} <em>from {state.legal_balls_remaining} balls</em></strong></div>
      <div><span>REQUIRED RATE</span><strong>{state.required_run_rate.toFixed(2)}</strong></div>
    </div>
  );
}

function Metric({ label, value, detail, emphasis, compact = false }) {
  return (
    <div className={`chase-metric ${emphasis ? `metric-${emphasis}` : ''} ${compact ? 'metric-compact' : ''}`}>
      <span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}
    </div>
  );
}

function formatSigned(value, suffix) {
  if (value == null) return '-';
  const rounded = Math.abs(value) < 10 ? value.toFixed(1) : Math.round(value);
  return `${value > 0 ? '+' : ''}${rounded}${suffix}`;
}

const styles = `
  .match-room { max-width: 1050px; margin: 0 auto; padding: 20px 0 36px; }
  .room-enter { animation: room-rise .48s cubic-bezier(.16, 1, .3, 1) both; }
  .match-room-header { margin-bottom: 18px; }
  .back-link { display: inline-block; font: 700 10px 'JetBrains Mono', monospace; letter-spacing: .09em; color: rgba(240,242,245,.48); text-decoration: none; margin-bottom: 18px; transition: color .18s ease, transform .18s ease; }
  .back-link:hover { color: var(--bail-amber); transform: translateX(-3px); }
  .room-title-row { display: flex; justify-content: space-between; align-items: end; gap: 24px; }
  .eyebrow, .chase-card-topline { font: 700 10px 'JetBrains Mono', monospace; letter-spacing: .1em; color: var(--bail-amber); }
  .eyebrow i { display: inline-block; width: 6px; height: 6px; margin-right: 7px; vertical-align: 1px; border-radius: 50%; background: var(--blood-red); box-shadow: 0 0 0 4px rgba(232,0,58,.12); animation: room-pulse 1.8s ease-in-out infinite; }
  .match-room-title { margin-top: 7px; font: 42px/1 'Bebas Neue', sans-serif; letter-spacing: .025em; color: #fff; }
  .match-room-title span { color: var(--blood-red); font-size: 23px; margin: 0 9px; }
  .room-purpose { max-width: 280px; font-size: 12px; color: rgba(240,242,245,.46); line-height: 1.5; text-align: right; }
  .room-stack { display: grid; gap: 16px; }
  .room-status { min-height: 180px; display: grid; place-items: center; border: 1px solid rgba(240,242,245,.08); border-radius: 8px; background: linear-gradient(125deg, rgba(245,166,35,.08), rgba(22,25,31,.8)); font: 11px 'JetBrains Mono', monospace; letter-spacing: .04em; color: rgba(240,242,245,.5); }
  .room-status-error { color: #ff8fa3; border-color: rgba(232,0,58,.28); }
  .chase-card { position: relative; overflow: hidden; border: 1px solid rgba(240,242,245,.12); border-radius: 8px; padding: 20px 22px 18px; background: radial-gradient(circle at 92% 10%, rgba(245,166,35,.12), transparent 30%), #11141a; }
  .chase-card::after { content: ''; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--bail-amber); }
  .chase-card-behind::after { background: var(--blood-red); }
  .chase-card-pending { background: linear-gradient(125deg, rgba(245,166,35,.08), #11141a 55%); }
  .chase-card-pending h2 { margin: 11px 0 5px; font: 28px/1 'Bebas Neue', sans-serif; color: #fff; }
  .chase-card-pending p { margin: 0 0 16px; max-width: 620px; color: rgba(240,242,245,.55); font-size: 13px; line-height: 1.5; }
  .chase-card-topline { display: flex; align-items: center; gap: 7px; }
  .engine-live-dot { width: 6px; height: 6px; border-radius: 50%; background: #62d794; box-shadow: 0 0 0 4px rgba(98,215,148,.1); animation: room-pulse 1.7s ease-in-out infinite; }
  .engine-refresh { margin-left: auto; color: rgba(240,242,245,.35); font-size: 9px; font-weight: 400; }
  .chase-hero { display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 16px 0 18px; }
  .chase-kicker { margin-bottom: 5px; font: 700 10px 'JetBrains Mono', monospace; color: rgba(240,242,245,.43); letter-spacing: .08em; }
  .chase-hero h2 { color: #fff; font: 36px/1 'Bebas Neue', sans-serif; letter-spacing: .025em; }
  .chase-card-behind .chase-hero h2 { color: #ff8fa3; }
  .chase-summary { max-width: 560px; margin-top: 7px; color: rgba(240,242,245,.6); font-size: 13px; line-height: 1.45; }
  .recovery-orb { flex: 0 0 86px; height: 86px; display: grid; place-content: center; text-align: center; border: 1px solid rgba(245,166,35,.42); border-radius: 50%; background: rgba(245,166,35,.06); box-shadow: inset 0 0 26px rgba(245,166,35,.08); }
  .chase-card-behind .recovery-orb { border-color: rgba(232,0,58,.5); background: rgba(232,0,58,.07); }
  .recovery-orb strong { font: 29px/1 'JetBrains Mono', monospace; color: #fff; letter-spacing: -.08em; }
  .recovery-orb span { margin-top: 4px; font: 700 8px 'JetBrains Mono', monospace; letter-spacing: .08em; color: rgba(240,242,245,.48); }
  .score-strip { display: grid; grid-template-columns: .8fr 1.45fr .9fr; border: 1px solid rgba(240,242,245,.09); border-radius: 5px; background: rgba(0,0,0,.17); }
  .score-strip > div { min-width: 0; padding: 11px 13px; }
  .score-strip > div + div { border-left: 1px solid rgba(240,242,245,.09); }
  .score-strip span, .chase-metric > span, .innings-context > span { display: block; font: 700 9px 'JetBrains Mono', monospace; letter-spacing: .07em; color: rgba(240,242,245,.42); text-transform: uppercase; }
  .score-strip strong { display: block; margin-top: 5px; color: #fff; font: 700 18px/1.1 'JetBrains Mono', monospace; letter-spacing: -.04em; }
  .score-strip em { color: rgba(240,242,245,.47); font: 400 10px 'Inter', sans-serif; letter-spacing: 0; font-style: normal; }
  .chase-metrics { display: grid; grid-template-columns: repeat(4, 1fr); margin-top: 12px; border-top: 1px solid rgba(240,242,245,.07); }
  .chase-metric { min-width: 0; padding: 12px 12px 0 0; }
  .chase-metric + .chase-metric { padding-left: 12px; border-left: 1px solid rgba(240,242,245,.07); }
  .chase-metric strong { display: block; overflow: hidden; margin-top: 5px; color: #fff; font: 700 15px/1.2 'JetBrains Mono', monospace; text-overflow: ellipsis; white-space: nowrap; letter-spacing: -.04em; }
  .chase-metric small { display: block; margin-top: 3px; color: rgba(240,242,245,.42); font: 10px 'Inter', sans-serif; }
  .metric-positive strong { color: #69d99a; } .metric-negative strong { color: #ff8fa3; } .metric-compact strong { font: 11px/1.35 'Inter', sans-serif; letter-spacing: 0; white-space: normal; }
  .innings-context { display: flex; align-items: baseline; flex-wrap: wrap; gap: 7px; margin-top: 13px; padding-top: 11px; border-top: 1px solid rgba(240,242,245,.07); }
  .innings-context > span { color: var(--bail-amber); } .innings-context strong { font: 700 12px 'JetBrains Mono', monospace; color: #fff; } .innings-context small { color: rgba(240,242,245,.38); font-size: 10px; }
  @keyframes room-rise { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes room-pulse { 50% { opacity: .38; transform: scale(.88); } }
  @media (max-width: 680px) { .match-room { padding-top: 12px; } .room-title-row { align-items: start; flex-direction: column; gap: 10px; } .room-purpose { max-width: none; text-align: left; } .match-room-title { font-size: 35px; } .chase-card { padding: 17px 16px; } .chase-hero { align-items: flex-start; } .chase-hero h2 { font-size: 30px; } .recovery-orb { flex-basis: 74px; width: 74px; height: 74px; } .recovery-orb strong { font-size: 23px; } .score-strip { grid-template-columns: 1fr 1fr; } .score-strip > div:last-child { grid-column: 1 / -1; border-top: 1px solid rgba(240,242,245,.09); border-left: 0; } .chase-metrics { grid-template-columns: 1fr 1fr; } .chase-metric:nth-child(3) { border-left: 0; } .chase-metric:nth-child(n+3) { border-top: 1px solid rgba(240,242,245,.07); padding-top: 12px; } }
  @media (prefers-reduced-motion: reduce) { .room-enter, .engine-live-dot, .eyebrow i { animation: none; } .back-link { transition: none; } }
`;
