import React, { useState, useEffect } from 'react';
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
      {!loading && !error && <InsightPanel insights={insights} />}

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
      `}</style>
    </div>
  );
}
