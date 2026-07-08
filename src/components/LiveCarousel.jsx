import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('scorecard'); // 'scorecard' | 'commentary'

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

  const handleToggle = async (matchId) => {
    if (expandedId === matchId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(matchId);
    setDetailLoading(true);

    try {
      // Lazy load detailed metrics when a user clicks the card
      const res = await fetch(`https://deathovers-ai-engine.onrender.com/api/match-details/${matchId}`);
      if (res.ok) {
        const data = await res.json();
        setMatchDetails(prev => ({ ...prev, [matchId]: data }));
      }
    } catch (err) {
      console.error("Failed to load match drilldown data:", err);
    } finally {
      setDetailLoading(false);
    }
  };

  if (loading) {
    return <div className="loading-state font-mono">SYNCHRONIZING REAL-TIME MATCH TRACKERS...</div>;
  }

  // Production Fallback Data for UI Presentation
  const displayMatches = matches.length > 0 ? matches : [{
    id: "mock-channel", venue: "IPL 2026 · Q2", status: "LIVE", matchName: "GT vs KKR",
    score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
    chaseNote: "Need 26 off 16"
  }];

  return (
    <div className="carousel-wrap">
      <div className="section-label">LIVE DATA FEED</div>
      <div className="carousel-track">
        
        {displayMatches.map((match) => {
          const isExpanded = expandedId === match.id;
          // Use fetched live detail data or render mock architecture matching the blueprint
          const detailedData = matchDetails[match.id] || {
            innings1: { team: "GT", score: "181/5", overs: "20.0", batters: [{name: "S. Sudharsan", r: 74, b: 47}, {name: "D. Miller", r: 44, b: 22}] },
            innings2: { team: "KKR", score: "156/6", overs: "17.2", batters: [{name: "V. Iyer*", r: 62, b: 34}, {name: "R. Singh", r: 19, b: 11}] },
            commentary: [
              { over: "17.2", event: "WICKET", text: "OUT! Shami strikes. Starc holes out to long on." },
              { over: "17.1", event: "FOUR", text: "Thumped over mid-off for a boundary by Iyer." }
            ]
          };

          return (
            <div key={match.id} className={`match-container ${isExpanded ? 'is-open' : ''}`}>
              <div className="match-card" onClick={() => handleToggle(match.id)}>
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

              {/* Advanced Expandable Analytical Viewport */}
              {isExpanded && (
                <div class="drawer-panel">
                  <div class="tab-menu">
                    <button class={`tab-btn ${activeTab === 'scorecard' ? 'active' : ''}`} onClick={() => setActiveTab('scorecard')}>Scorecard</button>
                    <button class={`tab-btn ${activeTab === 'commentary' ? 'active' : ''}`} onClick={() => setActiveTab('commentary')}>Live Commentary</button>
                  </div>

                  {detailLoading ? (
                    <div class="drawer-loading">DRILLING REALTIME MATCH METRICS...</div>
                  ) : (
                    <div class="tab-viewport">
                      {activeTab === 'scorecard' && (
                        <div class="scorecard-grid">
                          <div class="innings-block">
                            <div class="innings-header">1st Innings - {detailedData.innings1.team} <span>{detailedData.innings1.score} ({detailedData.innings1.overs})</span></div>
                            {detailedData.innings1.batters.map((b, i) => (
                              <div key={i} class="grid-row"><span>{b.name}</span><span class="mono">{b.r}({b.b})</span></div>
                            ))}
                          </div>
                          <div class="innings-block">
                            <div class="innings-header">2nd Innings - {detailedData.innings2.team} <span>{detailedData.innings2.score} ({detailedData.innings2.overs})</span></div>
                            {detailedData.innings2.batters.map((b, i) => (
                              <div key={i} class="grid-row"><span>{b.name}</span><span class="mono">{b.r}({b.b})</span></div>
                            ))}
                          </div>
                        </div>
                      )}

                      {activeTab === 'commentary' && (
                        <div class="commentary-stream">
                          {detailedData.commentary.map((c, i) => (
                            <div key={i} class="comm-row">
                              <span class="comm-over">{c.over}</span>
                              <span class={`comm-badge ${c.event.toLowerCase()}`}>{c.event}</span>
                              <p class="comm-text">{c.text}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        <div className="peek-card">
          <div className="peek-label">NEXT ▸</div>
          <div className="peek-teams">ESSEX W <br/><br/> SOM W</div>
        </div>

      </div>

      <style jsx>{`
        .carousel-wrap { padding: 20px 24px 0; }
        .section-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); letter-spacing: 0.05em; margin-bottom: 10px; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 16px; align-items: flex-start; }
        
        .match-container { display: flex; flex-direction: column; width: 320px; flex-shrink: 0; background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; transition: border-color 0.2s ease, box-shadow 0.2s ease; overflow: hidden; }
        .match-container.is-open { border-color: var(--blood-red); box-shadow: 0 4px 20px var(--hover-glow); }
        .match-card { padding: 16px; position: relative; cursor: pointer; }
        .match-container:not(.is-open) .match-card:hover { border-color: var(--blood-red); box-shadow: 0 4px 20px var(--hover-glow); }
        .match-container::before { content: ""; display: block; width: 100%; height: 2px; background: var(--blood-red); }
        
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 12px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--blood-red); display: flex; align-items: center; gap: 5px; font-weight: bold; }
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; }
        
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 19px; color: var(--crease-white); }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-weight: normal; }
        
        .chase-line { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 12px; border-top: 1px dashed rgba(240,242,245,0.1); }
        .chase-text { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--bail-amber); text-transform: uppercase; }
        .wp-badge { background: rgba(232, 0, 58, 0.1); color: var(--blood-red); font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 3px 6px; border-radius: 2px; font-weight: bold; }

        /* Drawer Styling */
        .drawer-panel { background: rgba(0, 0, 0, 0.2); border-top: 1px solid rgba(240,242,245,0.08); padding: 12px; }
        .tab-menu { display: flex; gap: 6px; margin-bottom: 12px; border-bottom: 1px solid rgba(240,242,245,0.05); padding-bottom: 8px; }
        .tab-btn { background: none; border: 1px solid rgba(240,242,245,0.15); color: rgba(240,242,245,0.6); padding: 4px 8px; font-family: 'JetBrains Mono', monospace; font-size: 10px; cursor: pointer; border-radius: 2px; transition: all 0.2s ease; }
        .tab-btn:hover { color: #fff; border-color: rgba(240,242,245,0.3); }
        .tab-btn.active { background: var(--blood-red); border-color: var(--blood-red); color: #fff; }
        
        .scorecard-grid { display: flex; flex-direction: column; gap: 14px; }
        .innings-header { font-family: 'Bebas Neue', sans-serif; font-size: 14px; color: var(--bail-amber); letter-spacing: 0.05em; margin-bottom: 6px; display: flex; justify-content: space-between; }
        .innings-header span { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #fff; }
        .grid-row { display: flex; justify-content: space-between; font-size: 11px; padding: 4px 0; border-bottom: 1px solid rgba(240,242,245,0.02); color: rgba(240,242,245,0.8); }
        
        .commentary-stream { display: flex; flex-direction: column; gap: 8px; max-height: 180px; overflow-y: auto; }
        .comm-row { display: flex; align-items: flex-start; gap: 6px; font-size: 11px; line-height: 1.4; border-bottom: 1px solid rgba(240,242,245,0.02); padding-bottom: 6px; }
        .comm-over { font-family: 'JetBrains Mono', monospace; color: var(--bail-amber); font-weight: bold; }
        .comm-badge { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 1px 4px; border-radius: 2px; font-weight: bold; background: rgba(240,242,245,0.1); }
        .comm-badge.wicket { background: rgba(232, 0, 58, 0.2); color: var(--blood-red); }
        .comm-badge.four, .comm-badge.six { background: rgba(245, 166, 35, 0.2); color: var(--bail-amber); }
        .comm-text { color: rgba(240,242,245,0.7); }
        .drawer-loading { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); padding: 20px 0; }

        .peek-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 140px; flex-shrink: 0; padding: 14px; opacity: 0.5; display: flex; flex-direction: column; justify-content: center; cursor: pointer; transition: opacity 0.2s ease; }
        .peek-card:hover { opacity: 0.8; }
        .peek-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 6px; }
        .peek-teams { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--crease-white); }
        .loading-state { color: rgba(240,242,245,0.4); font-size: 11px; padding: 24px 0; text-align: center; width: 100%; }
      `}</style>
    </div>
  );
}
