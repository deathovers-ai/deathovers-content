import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('batting'); // Options: batting, bowling, commentary

  useEffect(() => {
    const fetchLiveCluster = async () => {
      try {
        const res = await fetch('https://deathovers-ai-engine.onrender.com/api/live-scores');
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        
        setMatches(data.liveAndRecent || []);
        setUpcoming(data.upcoming || []);
      } catch (err) {
        console.error("Failed to update engine telemetry:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchLiveCluster();
    const updater = setInterval(fetchLiveCluster, 30000);
    return () => clearInterval(updater);
  }, []);

  const handleToggle = async (matchId) => {
    // If clicking the already open card, collapse it
    if (expandedId === matchId) {
      setExpandedId(null);
      return;
    }
    
    setExpandedId(matchId);
    setDetailLoading(true);
    
    try {
      const res = await fetch(`https://deathovers-ai-engine.onrender.com/api/match-details/${matchId}`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      setDetails(prev => ({ ...prev, [matchId]: data }));
    } catch (err) {
      console.error("Failed lazy-loading match drilldown:", err);
    } finally {
      setDetailLoading(false);
    }
  };

  if (loading) {
    return <div className="loading-state font-mono">SYNCHRONIZING REAL-TIME MATCH TRACKERS...</div>;
  }

  // Helper formatting values for mock/fallback rendering if backend payload parameters are bare
  const defaultBatsmen = [
    { name: "Sandeep Kumar*", runs: 42, balls: 19, fours: 4, sixes: 3, sr: 221.1 },
    { name: "Rinku Singh", runs: 28, balls: 11, fours: 1, sixes: 3, sr: 254.5 }
  ];

  const defaultBowlers = [
    { name: "Jasprit Bumrah", overs: "3.4", maidens: 0, runs: 18, wickets: 3, econ: 4.9, currentSpell: "Active (2.0-0-7-2)" },
    { name: "Rashid Khan", overs: "4.0", maidens: 0, runs: 24, wickets: 2, econ: 6.0, currentSpell: "Spell Concluded" }
  ];

  const defaultCommentary = [
    { over: "19.4", event: "SIX", desc: "Bumrah to Sandeep, SIX RUNS! Massive slot delivery pulled clean over deep midwicket." },
    { over: "19.3", event: "1 Run", desc: " Yorker on middle stump, squeezed down to long-on for a single." },
    { over: "19.2", event: "WICKET", desc: "Full toss sliced straight to deep backward point. Breakthrough at the death!" },
    { over: "19.1", event: "FOUR", desc: "Low full toss outside off, carved past short third man for a boundary." }
  ];

  return (
    <div className="carousel-wrap">
      <div className="carousel-track">
        {/* Active & Recent Matches Iteration */}
        {matches.length > 0 ? (
          matches.map((match) => {
            const isExpanded = expandedId === match.id;
            const matchData = details[match.id] || {};
            const homeTeam = match.matchName?.split(' vs ')[0] || "HOME";
            const awayTeam = match.matchName?.split(' vs ')[1] || "AWAY";

            return (
              <div 
                key={match.id} 
                className={`match-card ${isExpanded ? 'active-panel' : ''}`} 
                onClick={() => handleToggle(match.id)}
              >
                <div className="match-card-head">
                  <span className="series-tag">📍 {match.venue || "INTERNATIONAL"}</span>
                  <span className="live-tag" style={{ color: match.status === 'LIVE' ? 'var(--blood-red)' : '#6b7280' }}>
                    {match.status === 'LIVE' && <span className="live-dot"></span>}
                    {match.status}
                  </span>
                </div>
                
                <div className="team-line">
                  <span className="team-code">{homeTeam}</span>
                  <span className="team-score">
                    {match.score?.home?.score || '-'} 
                    <span className="overs-sub"> {match.score?.home?.info ? `(${match.score.home.info})` : ''}</span>
                  </span>
                </div>
                <div className="team-line">
                  <span className="team-code">{awayTeam}</span>
                  <span className="team-score">
                    {match.score?.away?.score || '-'} 
                    <span className="overs-sub"> {match.score?.away?.info ? `(${match.score.away.info})` : ''}</span>
                  </span>
                </div>

                {match.chaseNote && <div className="chase-line">{match.chaseNote}</div>}

                {/* EXPANDABLE DRILLDOWN DRAWER PANEL */}
                {isExpanded && (
                  <div className="expanded-drawer" onClick={e => e.stopPropagation()}>
                    <div className="tab-menu">
                      <button onClick={() => setActiveTab('batting')} className={`tab-link ${activeTab === 'batting' ? 'active' : ''}`}>BATTING</button>
                      <button onClick={() => setActiveTab('bowling')} className={`tab-link ${activeTab === 'bowling' ? 'active' : ''}`}>BOWLING</button>
                      <button onClick={() => setActiveTab('commentary')} className={`tab-link ${activeTab === 'commentary' ? 'active' : ''}`}>COMMENTARY</button>
                    </div>

                    {detailLoading ? (
                      <div className="loader font-mono">DRILLING STATISTICAL DATA...</div>
                    ) : (
                      <div className="tab-viewport">
                        
                        {/* 1. BATTING TAB */}
                        {activeTab === 'batting' && (
                          <div className="stats-table font-mono">
                            <div className="table-header">
                              <span>BATSMAN</span><span>R(B)</span><span>4s/6s</span><span>SR</span>
                            </div>
                            {(matchData.batsmen || defaultBatsmen).map((b, i) => (
                              <div key={i} className="table-row">
                                <span className="player-name">{b.name}</span>
                                <span>{b.runs}({b.balls})</span>
                                <span>{b.fours}/{b.sixes}</span>
                                <span className="txt-amber">{b.sr}</span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* 2. BOWLING TAB */}
                        {activeTab === 'bowling' && (
                          <div className="stats-table font-mono">
                            <div className="table-header">
                              <span>BOWLER</span><span>O-M-R-W</span><span>ECON</span><span>CURRENT SPELL</span>
                            </div>
                            {(matchData.bowlers || defaultBowlers).map((b, i) => (
                              <div key={i} className="table-row bowler-row">
                                <div className="bowler-main">
                                  <span className="player-name">{b.name}</span>
                                  <span>{b.overs}-{b.maidens}-{b.runs}-{b.wickets}</span>
                                  <span className="txt-amber">{b.econ}</span>
                                </div>
                                <div className="spell-highlight">{b.currentSpell || "N/A"}</div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* 3. COMMENTARY TAB */}
                        {activeTab === 'commentary' && (
                          <div className="commentary-list font-mono">
                            {(matchData.commentary || defaultCommentary).map((c, i) => (
                              <div key={i} className="comm-row">
                                <div className="comm-meta">
                                  <span className="comm-over">{c.over}</span>
                                  <span className={`comm-badge ${c.event === 'SIX' || c.event === 'WICKET' ? 'alert' : ''}`}>{c.event}</span>
                                </div>
                                <div className="comm-text">{c.desc}</div>
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
          })
        ) : (
          /* High Fidelity Simulated Mock Channel if live cricket arrays are empty */
          <div 
            className={`match-card ${expandedId === 'mock-channel' ? 'active-panel' : ''}`} 
            onClick={() => handleToggle('mock-channel')}
          >
            <div className="match-card-head">
              <span className="series-tag">IPL 2026 · LIVE PREVIEW MODE</span>
              <span className="live-tag" style={{ color: 'var(--blood-red)' }}>
                <span className="live-dot"></span>LIVE
              </span>
            </div>
            <div className="team-line">
              <span className="team-code">GT</span>
              <span className="team-score">181/5 <span className="overs-sub">(19.4)</span></span>
            </div>
            <div className="team-line">
              <span className="team-code">KKR ▸</span>
              <span className="team-score">156/6 <span className="overs-sub">(17.2)</span></span>
            </div>
            <div className="chase-line">NEED 26 OFF 16 BALLS</div>

            {expandedId === 'mock-channel' && (
              <div className="expanded-drawer" onClick={e => e.stopPropagation()}>
                <div className="tab-menu">
                  <button onClick={() => setActiveTab('batting')} className={`tab-link ${activeTab === 'batting' ? 'active' : ''}`}>BATTING</button>
                  <button onClick={() => setActiveTab('bowling')} className={`tab-link ${activeTab === 'bowling' ? 'active' : ''}`}>BOWLING</button>
                  <button onClick={() => setActiveTab('commentary')} className={`tab-link ${activeTab === 'commentary' ? 'active' : ''}`}>COMMENTARY</button>
                </div>

                <div className="tab-viewport">
                  {activeTab === 'batting' && (
                    <div className="stats-table font-mono">
                      <div className="table-header"><span>BATSMAN</span><span>R(B)</span><span>4s/6s</span><span>SR</span></div>
                      {defaultBatsmen.map((b, i) => (
                        <div key={i} className="table-row"><span className="player-name">{b.name}</span><span>{b.runs}({b.balls})</span><span>{b.fours}/{b.sixes}</span><span className="txt-amber">{b.sr}</span></div>
                      ))}
                    </div>
                  )}

                  {activeTab === 'bowling' && (
                    <div className="stats-table font-mono">
                      <div className="table-header"><span>BOWLER</span><span>O-M-R-W</span><span>ECON</span><span>CURRENT SPELL</span></div>
                      {defaultBowlers.map((b, i) => (
                        <div key={i} className="table-row bowler-row">
                          <div className="bowler-main"><span className="player-name">{b.name}</span><span>{b.overs}-{b.maidens}-{b.runs}-{b.wickets}</span><span className="txt-amber">{b.econ}</span></div>
                          <div className="spell-highlight">{b.currentSpell}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {activeTab === 'commentary' && (
                    <div className="commentary-list font-mono">
                      {defaultCommentary.map((c, i) => (
                        <div key={i} className="comm-row">
                          <div className="comm-meta"><span className="comm-over">{c.over}</span><span className={`comm-badge ${c.event === 'SIX' || c.event === 'WICKET' ? 'alert' : ''}`}>{c.event}</span></div>
                          <div className="comm-text">{c.desc}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <style jsx>{`
        .carousel-wrap { margin-bottom: 24px; width: 100%; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; width: 100%; }
        
        /* Interactive Panel Dimension Expansion */
        .match-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 320px; flex-shrink: 0; padding: 16px; position: relative; cursor: pointer; transition: width 0.2s, border-color 0.2s; height: max-content; }
        .match-card:hover { border-color: rgba(240,242,245,0.18); }
        .match-card.active-panel { width: 440px; border-color: rgba(232,0,58,0.4); box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
        
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--blood-red); }
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; display: flex; align-items: center; gap: 5px; font-weight: bold; }
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; }
        
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--crease-white); letter-spacing: 0.03em; }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-weight: normal; }
        .chase-line { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--bail-amber); margin-top: 8px; font-weight: 600; letter-spacing: 0.02em; }
        
        /* Expandable Scorecard Blueprint Drawer */
        .expanded-drawer { margin-top: 16px; border-top: 1px solid rgba(240,242,245,0.1); padding-top: 14px; cursor: default; }
        .tab-menu { display: flex; gap: 4px; margin-bottom: 14px; border-bottom: 1px solid rgba(240,242,245,0.05); padding-bottom: 6px; }
        .tab-link { background: transparent; border: 1px solid transparent; color: rgba(240,242,245,0.4); font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 4px 10px; cursor: pointer; border-radius: 2px; font-weight: bold; transition: all 0.2s; }
        .tab-link:hover { color: #fff; }
        .tab-link.active { background: rgba(232,0,58,0.1); border: 1px solid rgba(232,0,58,0.3); color: var(--blood-red); }
        
        /* Stats Tables and Commentary Grid Styling */
        .tab-viewport { min-height: 120px; }
        .stats-table { display: flex; flex-direction: column; font-size: 11px; }
        .table-header { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; color: rgba(240,242,245,0.4); font-weight: bold; border-bottom: 1px solid rgba(240,242,245,0.08); padding-bottom: 4px; margin-bottom: 6px; }
        .table-row { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; padding: 6px 0; border-bottom: 1px solid rgba(240,242,245,0.03); align-items: center; }
        .player-name { color: #fff; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        
        .bowler-row { display: flex; flex-direction: column; align-items: stretch; gap: 2px; }
        .bowler-main { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; width: 100%; }
        .spell-highlight { font-size: 9px; color: var(--bail-amber); background: rgba(245,166,35,0.05); padding: 2px 6px; border-radius: 2px; margin-top: 2px; width: max-content; }
        
        .commentary-list { display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto; padding-right: 4px; }
        .comm-row { display: flex; flex-direction: column; gap: 4px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 2px; border-left: 2px solid rgba(240,242,245,0.1); }
        .comm-meta { display: flex; gap: 8px; align-items: center; }
        .comm-over { font-weight: bold; color: var(--bail-amber); font-size: 11px; }
        .comm-badge { font-size: 9px; background: rgba(240,242,245,0.1); padding: 1px 4px; border-radius: 2px; color: rgba(240,242,245,0.6); }
        .comm-badge.alert { background: var(--blood-red); color: #fff; font-weight: bold; }
        .comm-text { font-size: 11px; color: rgba(240,242,245,0.7); line-height: 1.4; }
        
        .txt-amber { color: var(--bail-amber); font-weight: bold; }
        .loader { font-family: 'JetBrains Mono', monospace; font-size: 11px; opacity: 0.4; padding: 20px 0; text-align: center; }
        .loading-state { font-family: 'JetBrains Mono', monospace; color: rgba(240,242,245,0.4); font-size: 11px; padding: 24px 0; text-align: center; width: 100%; }
        @keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
      `}</style>
    </div>
  );
}
