import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('scorecard');

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
    return <div className="loading-state font-mono">ESTABLISHING SECURE UPLINK TO DATA CLUSTER...</div>;
  }

  const displayMatches = matches.length > 0 ? matches : [{
    id: "mock-channel", venue: "IPL 2026 · Q2", status: "LIVE", matchName: "GT vs KKR",
    score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
    chaseNote: "Need 26 off 16"
  }];

  return (
    <div className="carousel-wrap">
      <div className="section-label">LIVE MATCH TERMINALS</div>
      <div className="carousel-track">
        
        {displayMatches.map((match) => {
          const isExpanded = expandedId === match.id;
          
          const detailedData = matchDetails[match.id] || {
            recentBalls: ['1', '0', 'W', '4', '6', '1'],
            currentBowler: "M. Starc",
            currentBowlerStats: "3.2-0-24-1",
            innings1: { 
              team: "GT", score: "181/5", overs: "20.0", 
              batters: [
                {name: "S. Sudharsan", r: 74, b: 47, sr: "157.4"}, 
                {name: "D. Miller", r: 44, b: 22, sr: "200.0"}
              ],
              bowlers: [
                {name: "M. Starc", o: "4.0", r: "35", w: "2", eco: "8.75"},
                {name: "S. Narine", o: "4.0", r: "24", w: "1", eco: "6.00"}
              ]
            },
            innings2: { 
              team: "KKR", score: "156/6", overs: "17.2", 
              batters: [
                {name: "V. Iyer*", r: 62, b: 34, sr: "182.3"}, 
                {name: "R. Singh", r: 19, b: 11, sr: "172.7"}
              ],
              bowlers: [
                {name: "M. Shami", o: "3.2", r: "28", w: "3", eco: "8.40"},
                {name: "R. Khan", o: "4.0", r: "22", w: "2", eco: "5.50"}
              ]
            },
            commentary: [
              { over: "17.2", event: "WICKET", text: "OUT! Shami strikes. Starc holes out to long on." },
              { over: "17.1", event: "FOUR", text: "Thumped over mid-off for a boundary by Iyer." },
              { over: "17.0", event: "1 RUN", text: "Pushed to deep cover for a single to retain the strike." },
              { over: "16.5", event: "SIX", text: "Massive! Dispatched into the stands over deep mid-wicket." }
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
                
                <div className="expand-indicator">
                  {isExpanded ? 'CLOSE TERMINAL ▲' : 'OPEN TERMINAL ▼'}
                </div>
              </div>

              {isExpanded && (
                <div className="drawer-panel">
                  
                  <div className="hud-rail">
                    <div className="hud-label">CURRENT OVER: <span className="hud-highlight">{detailedData.currentBowler}</span> ({detailedData.currentBowlerStats})</div>
                    <div className="ball-tracker">
                      {detailedData.recentBalls.map((ball, idx) => {
                        let bClass = "ball-normal";
                        if (ball === 'W') bClass = "ball-wicket";
                        if (ball === '4' || ball === '6') bClass = "ball-boundary";
                        if (ball === '0') bClass = "ball-dot";
                        return <span key={idx} className={`ball-pip ${bClass}`}>{ball}</span>;
                      })}
                    </div>
                  </div>

                  <div className="tab-menu">
                    <button className={`tab-btn ${activeTab === 'scorecard' ? 'active' : ''}`} onClick={() => setActiveTab('scorecard')}>SCORECARD</button>
                    <button className={`tab-btn ${activeTab === 'commentary' ? 'active' : ''}`} onClick={() => setActiveTab('commentary')}>COMMENTARY</button>
                  </div>

                  {detailLoading ? (
                    <div className="drawer-loading">PROCESSING TELEMETRY...</div>
                  ) : (
                    <div className="tab-viewport">
                      
                      {activeTab === 'scorecard' && (
                        <div className="scorecard-stack">
                          
                          {/* INNINGS 2 (Current) */}
                          <div className="innings-block active-innings">
                            <div className="innings-header">2ND INNING: {detailedData.innings2.team} <span>{detailedData.innings2.score} ({detailedData.innings2.overs})</span></div>
                            
                            <div className="grid-labels"><span>BATTER</span><span>R</span><span>B</span><span>SR</span></div>
                            {detailedData.innings2.batters.map((b, i) => (
                              <div key={i} className="grid-row">
                                <span className="player-name">{b.name}</span>
                                <span className="mono">{b.r}</span>
                                <span className="mono dim">{b.b}</span>
                                <span className="mono dim">{b.sr}</span>
                              </div>
                            ))}
                            
                            <div className="grid-labels mt-12"><span>BOWLER</span><span>O</span><span>R</span><span>W</span><span>ECO</span></div>
                            {detailedData.innings2.bowlers.map((bw, i) => (
                              <div key={i} className="grid-row">
                                <span className="player-name">{bw.name}</span>
                                <span className="mono dim">{bw.o}</span>
                                <span className="mono dim">{bw.r}</span>
                                <span className="mono highlight">{bw.w}</span>
                                <span className="mono dim">{bw.eco}</span>
                              </div>
                            ))}
                          </div>
                          
                          {/* INNINGS 1 (Completed) */}
                          <div className="innings-block mt-16">
                            <div className="innings-header dim-header">1ST INNING: {detailedData.innings1.team} <span>{detailedData.innings1.score} ({detailedData.innings1.overs})</span></div>
                            
                            <div className="grid-labels"><span>BATTER</span><span>R</span><span>B</span><span>SR</span></div>
                            {detailedData.innings1.batters.map((b, i) => (
                              <div key={i} className="grid-row dim-row">
                                <span className="player-name">{b.name}</span>
                                <span className="mono">{b.r}</span>
                                <span className="mono dim">{b.b}</span>
                                <span className="mono dim">{b.sr}</span>
                              </div>
                            ))}
                            
                            <div className="grid-labels mt-12"><span>BOWLER</span><span>O</span><span>R</span><span>W</span><span>ECO</span></div>
                            {detailedData.innings1.bowlers.map((bw, i) => (
                              <div key={i} className="grid-row dim-row">
                                <span className="player-name">{bw.name}</span>
                                <span className="mono dim">{bw.o}</span>
                                <span className="mono dim">{bw.r}</span>
                                <span className="mono highlight">{bw.w}</span>
                                <span className="mono dim">{bw.eco}</span>
                              </div>
                            ))}
                          </div>

                        </div>
                      )}

                      {activeTab === 'commentary' && (
                        <div className="commentary-stream">
                          <div className="innings-header comm-header">LIVE COMMENTARY FEED</div>
                          {detailedData.commentary.map((c, i) => (
                            <div key={i} className="comm-row">
                              <div className="comm-meta">
                                <span className="comm-over">{c.over}</span>
                                <span className={`comm-badge ${c.event.toLowerCase()}`}>{c.event}</span>
                              </div>
                              <p className="comm-text">{c.text}</p>
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
        .carousel-track { display: flex; gap: 16px; overflow-x: auto; padding-bottom: 24px; align-items: flex-start; scroll-behavior: smooth; }
        
        .match-container { display: flex; flex-direction: column; width: 340px; flex-shrink: 0; background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 6px; transition: border-color 0.2s ease, box-shadow 0.2s ease; overflow: hidden; }
        .match-container.is-open { border-color: var(--blood-red); box-shadow: 0 8px 30px rgba(0,0,0,0.5), 0 0 0 1px var(--blood-red); } 
        
        .match-card { padding: 18px; position: relative; cursor: pointer; background: linear-gradient(180deg, rgba(22,25,31,1) 0%, rgba(12,14,18,1) 100%); }
        .match-container:not(.is-open) .match-card:hover { border-color: var(--blood-red); box-shadow: 0 4px 20px var(--hover-glow); }
        .match-container::before { content: ""; display: block; width: 100%; height: 3px; background: var(--blood-red); }
        
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 14px; max-width: 310px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--blood-red); display: flex; align-items: center; gap: 5px; font-weight: bold; letter-spacing: 0.05em; }
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; }
        
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; max-width: 310px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--crease-white); letter-spacing: 0.02em; }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-weight: normal; margin-left: 4px; }
        
        .chase-line { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding-top: 14px; border-top: 1px dashed rgba(240,242,245,0.1); max-width: 310px; }
        .chase-text { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--bail-amber); text-transform: uppercase; font-weight: bold; }
        .wp-badge { background: rgba(232, 0, 58, 0.15); color: var(--blood-red); font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 4px 8px; border-radius: 2px; font-weight: bold; border: 1px solid rgba(232,0,58,0.3); }

        .expand-indicator { font-family: 'JetBrains Mono', monospace; font-size: 9px; text-align: center; color: rgba(240,242,245,0.3); margin-top: 16px; font-weight: bold; letter-spacing: 0.1em; transition: color 0.2s; }
        .match-card:hover .expand-indicator { color: var(--blood-red); }

        .drawer-panel { background: #0D1117; border-top: 1px solid rgba(232,0,58,0.3); display: flex; flex-direction: column; }
        
        .hud-rail { background: rgba(0,0,0,0.4); padding: 12px 18px; border-bottom: 1px solid rgba(240,242,245,0.05); }
        .hud-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.5); margin-bottom: 8px; }
        .hud-highlight { color: #fff; font-weight: bold; }
        .ball-tracker { display: flex; gap: 6px; }
        .ball-pip { display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: bold; }
        .ball-normal { background: rgba(240,242,245,0.1); color: #fff; }
        .ball-dot { background: transparent; border: 1px solid rgba(240,242,245,0.2); color: rgba(240,242,245,0.5); }
        .ball-boundary { background: rgba(245, 166, 35, 0.2); color: var(--bail-amber); border: 1px solid rgba(245, 166, 35, 0.5); }
        .ball-wicket { background: var(--blood-red); color: #fff; box-shadow: 0 0 8px rgba(232,0,58,0.6); }

        .tab-menu { display: flex; padding: 0 18px; margin-top: 12px; border-bottom: 1px solid rgba(240,242,245,0.08); }
        .tab-btn { background: none; border: none; border-bottom: 2px solid transparent; color: rgba(240,242,245,0.5); padding: 8px 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: bold; cursor: pointer; transition: all 0.2s ease; letter-spacing: 0.05em; flex: 1; text-align: center; }
        .tab-btn:hover { color: #fff; }
        .tab-btn.active { color: var(--blood-red); border-bottom: 2px solid var(--blood-red); }
        
        .tab-viewport { padding: 18px; max-height: 380px; overflow-y: auto; }
        .tab-viewport::-webkit-scrollbar { width: 4px; }
        .tab-viewport::-webkit-scrollbar-thumb { background: rgba(240,242,245,0.2); border-radius: 4px; }

        .scorecard-stack { display: flex; flex-direction: column; }
        .innings-block { display: flex; flex-direction: column; gap: 4px; }
        .innings-header { font-family: 'Bebas Neue', sans-serif; font-size: 18px; color: var(--bail-amber); letter-spacing: 0.05em; margin-bottom: 6px; display: flex; justify-content: space-between; border-bottom: 1px solid rgba(245, 166, 35, 0.2); padding-bottom: 4px; }
        .innings-header span { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #fff; }
        .dim-header { color: rgba(240,242,245,0.5); border-bottom-color: rgba(240,242,245,0.1); }
        .comm-header { color: #fff; border-bottom-color: rgba(240,242,245,0.1); font-size: 16px; margin-bottom: 12px; border-bottom: none; }
        
        .grid-labels { display: flex; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 4px; padding: 0 4px; }
        .grid-labels span:first-child { flex: 2; }
        .grid-labels span:not(:first-child) { flex: 1; text-align: right; }
        
        .grid-row { display: flex; font-size: 12px; padding: 6px 4px; background: rgba(240,242,245,0.02); border-radius: 4px; align-items: center; margin-bottom: 2px; }
        .grid-row span:first-child { flex: 2; }
        .grid-row span:not(:first-child) { flex: 1; text-align: right; }
        
        .player-name { font-weight: 500; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 8px; }
        .mono { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
        .dim { color: rgba(240,242,245,0.5); }
        .highlight { color: var(--bail-amber); font-weight: bold; }
        .dim-row .player-name { color: rgba(240,242,245,0.6); }
        
        .mt-12 { margin-top: 12px; }
        .mt-16 { margin-top: 24px; }

        .commentary-stream { display: flex; flex-direction: column; gap: 10px; }
        .comm-row { display: flex; flex-direction: column; gap: 6px; font-size: 12px; line-height: 1.5; background: rgba(240,242,245,0.02); padding: 12px; border-radius: 4px; border-left: 2px solid rgba(240,242,245,0.1); }
        .comm-meta { display: flex; align-items: center; gap: 8px; }
        .comm-over { font-family: 'JetBrains Mono', monospace; color: var(--bail-amber); font-weight: bold; font-size: 11px; }
        .comm-badge { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 2px 6px; border-radius: 2px; font-weight: bold; background: rgba(240,242,245,0.1); }
        .comm-badge.wicket { background: var(--blood-red); color: #fff; }
        .comm-badge.four, .comm-badge.six { background: var(--bail-amber); color: #000; }
        .comm-text { color: rgba(240,242,245,0.8); }

        .drawer-loading { text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); padding: 40px 0; }

        .peek-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 6px; width: 140px; flex-shrink: 0; padding: 14px; opacity: 0.5; display: flex; flex-direction: column; justify-content: center; cursor: pointer; transition: opacity 0.2s ease; }
        .peek-card:hover { opacity: 0.8; }
        .peek-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 6px; }
        .peek-teams { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--crease-white); }
      `}</style>
    </div>
  );
}
