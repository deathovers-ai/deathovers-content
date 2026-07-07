import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    const fetchLiveCluster = async () => {
      try {
        const res = await fetch('https://deathovers-ai-engine.onrender.com/api/live-scores');
        if (!res.ok) throw new Error("HTTP Error");
        const data = await res.json();
        setMatches(data.liveAndRecent || []);
      } catch (err) {
        console.error("Telemetry failed:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchLiveCluster();
    const updater = setInterval(fetchLiveCluster, 30000);
    return () => clearInterval(updater);
  }, []);

  const handleToggle = (matchId) => {
    setExpandedId(expandedId === matchId ? null : matchId);
  };

  if (loading) {
    return <div className="loading-state font-mono">SYNCHRONIZING REAL-TIME MATCH TRACKERS...</div>;
  }

  // Fallback if API is offline
  const displayMatches = matches.length > 0 ? matches : [{
    id: "mock-channel", venue: "IPL 2026 · Q2", status: "LIVE", matchName: "GT vs KKR",
    score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
    chaseNote: "Need 26 off 16"
  }];

  return (
    <div className="carousel-wrap">
      <div className="section-label">LIVE DATA FEED</div>
      <div className="carousel-track">
        
        {displayMatches.map((match) => (
          <div key={match.id} className="match-card" onClick={() => handleToggle(match.id)}>
            <div className="match-card-head">
              <span className="series-tag">{match.venue || "INTERNATIONAL"}</span>
              <span className="live-tag" style={{ color: match.status === 'LIVE' ? 'var(--blood-red)' : '#6b7280' }}>
                {match.status === 'LIVE' && <span className="live-dot"></span>}
                {match.status}
              </span>
            </div>
            
            <div className="team-line">
              <span className="team-code">{match.matchName?.split(' vs ')[0] || "HOME"}</span>
              <span className="team-score">{match.score?.home?.score || '-'} <span className="overs-sub">({match.score?.home?.info || ''})</span></span>
            </div>
            <div className="team-line">
              <span className="team-code">{match.matchName?.split(' vs ')[1] || "AWAY"}</span>
              <span className="team-score">{match.score?.away?.score || '-'} <span className="overs-sub">({match.score?.away?.info || ''})</span></span>
            </div>

            {match.status === 'LIVE' && (
              <div className="chase-line">
                <span className="chase-text">{match.chaseNote || "IN PROGRESS"}</span>
                <span className="wp-badge">WP: {match.matchName?.split(' vs ')[1] || "CHASING"} 68%</span>
              </div>
            )}
          </div>
        ))}

        {/* Peek Card for Upcoming Matches */}
        <div className="peek-card">
          <div className="peek-label">NEXT ▸</div>
          <div className="peek-teams">ESSEX W <br/><br/> SOM W</div>
        </div>

      </div>

      <style jsx>{`
        .carousel-wrap { padding: 20px 24px 0; }
        .section-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); letter-spacing: 0.05em; margin-bottom: 10px; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 16px; }
        
        .match-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 320px; flex-shrink: 0; padding: 16px; position: relative; cursor: pointer; transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease; }
        .match-card:hover { transform: translateY(-2px); border-color: var(--blood-red); box-shadow: 0 4px 20px var(--hover-glow); }
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--blood-red); }
        
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 12px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; display: flex; align-items: center; gap: 5px; font-weight: bold; }
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; }
        
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 19px; color: var(--crease-white); }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-weight: normal; }
        
        .chase-line { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px dashed rgba(240,242,245,0.1); }
        .chase-text { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--bail-amber); text-transform: uppercase; }
        .wp-badge { background: rgba(232, 0, 58, 0.1); color: var(--blood-red); font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 3px 6px; border-radius: 2px; font-weight: bold; }

        .peek-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 140px; flex-shrink: 0; padding: 14px; opacity: 0.5; display: flex; flex-direction: column; justify-content: center; cursor: pointer; transition: opacity 0.2s ease; }
        .peek-card:hover { opacity: 0.8; }
        .peek-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 6px; }
        .peek-teams { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--crease-white); }
        .loading-state { color: rgba(240,242,245,0.4); font-size: 11px; padding: 24px 0; text-align: center; width: 100%; }
      `}</style>
    </div>
  );
}
