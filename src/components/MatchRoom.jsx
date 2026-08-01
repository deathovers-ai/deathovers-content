import React, { useState, useEffect } from 'react';
import MatchInfoCard from './MatchInfoStrip.jsx';
import InsightPanel from './InsightPanel.jsx';

// Standalone page-level component: fetches one match's details independently
// of the live carousel, so this URL works even when landed on directly
// (shared link, bookmark) rather than only via click-through from "/".
export default function MatchRoom() {
  const [matchId, setMatchId] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');
    if (!id) {
      setError('No match specified.');
      setLoading(false);
      return;
    }
    setMatchId(id);
  }, []);

  useEffect(() => {
    if (!matchId) return;
    let cancelled = false;

    async function fetchDetails() {
      try {
        const res = await fetch(`https://deathovers-ai-engine.onrender.com/api/match-details/${matchId}`);
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const json = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Failed to load match data');
          setLoading(false);
        }
      }
    }

    fetchDetails();
    // Insights are point-in-time reads, not a live scoreboard - poll
    // slowly (60s) just to catch newly appended insights as the match
    // progresses, without the tight polling the live scorecard needs.
    const interval = setInterval(fetchDetails, 60000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [matchId]);

  const insights = data?.intelligence?.insights || [];
  const team1 = data?.innings?.[0]?.team;
  const team2 = data?.innings?.[1]?.team;

  // venue_pregame_summary is now rendered by MatchInfoCard, not
  // InsightPanel - pull it out here and pass the rest through separately
  // so it doesn't get shown twice.
  const pregame = insights.find(i => i.type === 'venue_pregame_summary');
  const timelineInsights = insights.filter(i => i.type !== 'venue_pregame_summary');

  return (
    <div className="match-room">
      <div className="match-room-header">
        <a href="/" className="back-link">← BACK TO LIVE</a>
        {(team1 || team2) && (
          <h1 className="match-room-title">
            {team1 || 'TBD'} <span className="vs">vs</span> {team2 || 'TBD'}
          </h1>
        )}
      </div>

      {loading && <div className="match-room-status">Loading match context...</div>}
      {error && <div className="match-room-status error">Couldn't load this match: {error}</div>}

      {!loading && !error && (
        <>
          <MatchInfoCard
            toss={data?.toss}
            weather={data?.weather}
            dewRisk={data?.dewRisk}
            pregame={pregame}
          />
          <ChasePanel chase={data?.chase} />
          <InsightPanel insights={timelineInsights} />
        </>
      )}

      <style>{`
        .match-room { max-width: 1050px; margin: 0 auto; padding: 24px 0; }
        .match-room-header { margin-bottom: 24px; }
        .back-link {
          display: inline-block;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          color: rgba(240,242,245,0.5);
          text-decoration: none;
          margin-bottom: 16px;
          letter-spacing: 0.04em;
        }
        .back-link:hover { color: var(--bail-amber); }
        .match-room-title {
          font-family: 'Bebas Neue', sans-serif;
          font-size: 32px;
          color: #fff;
          letter-spacing: 0.01em;
        }
        .match-room-title .vs {
          color: var(--blood-red);
          font-size: 20px;
          margin: 0 8px;
        }
        .match-room-status {
          font-family: 'JetBrains Mono', monospace;
          font-size: 12px;
          color: rgba(240,242,245,0.5);
          text-align: center;
          padding: 40px 0;
        }
        .match-room-status.error { color: var(--blood-red); }
        .chase-panel { margin: 16px 0; padding: 18px; border-left: 3px solid var(--bail-amber); background: rgba(245,166,35,.06); font: 11px 'JetBrains Mono', monospace; color: rgba(240,242,245,.65); }
        .chase-panel span { display:block; color: var(--bail-amber); letter-spacing:.08em; }
        .chase-panel strong { display:block; margin:7px 0; font: 26px 'Bebas Neue', sans-serif; color:#fff; }
        .chase-panel p { margin:0 0 8px; font: 13px Inter, sans-serif; }
      `}</style>
    </div>
  );
}

function ChasePanel({ chase }) {
  const state = chase?.state;
  const cohort = chase?.cohort;
  if (!state) return null;
  if (chase.status !== 'qualified') return <div className="chase-panel">CHASE CONTEXT: AWAITING QUALIFIED HISTORICAL COHORT</div>;
  const pace = cohort.pace_gap_runs >= 0 ? 'AHEAD OF HISTORICAL PACE' : 'BEHIND HISTORICAL PACE';
  return <section className="chase-panel"><span>CHASE EVIDENCE</span><strong>{pace}</strong><p>{state.runs}/{state.wickets} · need {state.runs_required} from {state.legal_balls_remaining} balls · RRR {state.required_run_rate.toFixed(2)}</p><small>RECOVERY {Math.round(cohort.recovery_rate * 100)}% · {cohort.wins}/{cohort.sample_size} comparable chases · WICKET PAR {cohort.average_successful_wickets?.toFixed(1) || '—'}</small></section>;
}
