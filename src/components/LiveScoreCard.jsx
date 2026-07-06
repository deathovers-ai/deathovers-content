import React, { useState, useEffect } from 'react';
import './LiveScoreCard.css';

export default function LiveScoreCard() {
  const [apiResponse, setApiResponse] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;

    const fetchLiveScores = async () => {
      try {
        const response = await fetch('https://deathovers-ai-engine.onrender.com/api/live-scores', { signal });
        const json = await response.json();
        setApiResponse(json);
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Pipeline Error:', error);
        }
      } finally {
        setLoading(false);
      }
    };

    fetchLiveScores();
    const interval = setInterval(fetchLiveScores, 30000);

    return () => {
      clearInterval(interval);
      controller.abort();
    };
  }, []);

  if (loading) return <div className="do-card-wrapper text-white text-center py-10 font-mono">INITIALIZING PIPELINE...</div>;
  if (!apiResponse || apiResponse.mode === 'empty') return <div className="do-card-wrapper text-white text-center py-10 font-mono">NO SCHEDULED MATCHES TODAY</div>;

  // --- STATE 1: LIVE MATCH DISPLAY ---
  if (apiResponse.mode === 'live') {
    const matchData = apiResponse.data;
    const matchName = matchData.match || "Match";
    const homeScoreData = matchData.score?.home?.score || "-";
    const homeOversData = matchData.score?.home?.info || "";
    const awayScoreData = matchData.score?.away?.score || "-";
    const awayOversData = matchData.score?.away?.info || "";
    
    const teams = matchName.split(' vs ');
    const homeCode = teams[0] ? teams[0].substring(0, 3).toUpperCase() : "TBD";
    const awayCode = teams[1] ? teams[1].substring(0, 3).toUpperCase() : "TBD";

    return (
      <div className="do-card-wrapper">
        <div className="card">
          <div className="accent-bar"></div>
          <div className="header">
            <div className="header-top">
              <span className="series">{matchName}</span>
              <div className="live-indicator">
                <div className="live-dot"></div>
                <span className="live-label">LIVE</span>
              </div>
            </div>
            <div className="venue">DeathOvers Live Feed</div>
          </div>
          <div className="score-block">
            <div className="team-row dim">
              <div className="team-left"><span className="team-code">{homeCode}</span></div>
              <div className="team-score dim">{homeScoreData} <span className="overs">({homeOversData})</span></div>
            </div>
            <div className="team-row">
              <div className="team-left">
                <span className="team-code">{awayCode}</span>
                <span className="bat-arrow">▸</span>
              </div>
              <div className="team-score">{awayScoreData} <span className="overs">({awayOversData})</span></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // --- STATE 2: SCHEDULED FIXTURES DISPLAY ---
  if (apiResponse.mode === 'scheduled') {
    const upcomingMatches = apiResponse.data?.upcoming || [];
    
    return (
      <div className="do-card-wrapper">
        <div className="card">
          <div className="accent-bar"></div>
          <div className="header">
            <div className="header-top">
              <span className="series">Upcoming Fixtures</span>
              <span className="live-label" style={{ color: 'var(--bail-amber)' }}>SCHEDULED</span>
            </div>
            <div className="venue">No matches currently in-play</div>
          </div>
          <div className="score-block">
            {upcomingMatches.length === 0 ? (
              <div className="text-sm font-mono text-center opacity-50">No matches left for today</div>
            ) : (
              upcomingMatches.map((match, idx) => (
                <div key={match.id || idx} style={{ padding: '12px 0', borderBottom: idx !== upcomingMatches.length - 1 ? '1px solid rgba(240,242,245,0.05)' : 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'between', alignItems: 'center' }}>
                    <span className="team-code" style={{ fontSize: '18px' }}>{match.matchName}</span>
                  </div>
                  <div className="venue" style={{ marginTop: '4px', display: 'flex', justifyContent: 'space-between' }}>
                    <span>📍 {match.venue}</span>
                    <span style={{ color: 'var(--bail-amber)', fontFamily: 'JetBrains Mono' }}>{match.startTime || "Today"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
