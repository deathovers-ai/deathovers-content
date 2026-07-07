import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('batting');

  useEffect(() => {
    const fetchLiveCluster = async () => {
      try {
        // Aligned to query the core api live-scores route
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
    if (expandedId === matchId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(matchId);
    setDetailLoading(true);
    try {
      const res = await fetch(`https://deathovers-ai-engine.onrender.com/api/match-details/${matchId}`);
      const data = await res.json();
      setDetails(prev => ({ ...prev, [matchId]: data }));
    } catch (err) {
      console.error("Failed lazy-loading match drilldown:", err);
    } finally {
      setDetailLoading(false);
    }
  };

  if (loading) {
    return <div className="loading-state font-mono">SYNCHRONIZING REALT-TIME MATCH TRACKERS...</div>;
  }

  return (
    <div className="carousel-wrap">
      <div className="carousel-track">
        {/* Render Active/Recent Matches from live stream feed */}
        {matches.length > 0 && matches.map((match) => {
          const isExpanded = expandedId === match.id;
          const matchData = details[match.id] || {};
          
          return (
            <div key={match.id} className={`match-card ${isExpanded ? 'active-panel' : ''}`} onClick={() => handleToggle(match.id)}>
              <div className="match-card-head">
                <span className="series-tag">📍 {match.venue || "INTERNATIONAL"}</span>
                <span className="live-tag" style={{ color: match.status === 'LIVE' ? 'var(--blood-red)' : '#6b7280' }}>
                  {match.status === 'LIVE' && <span className="live-dot"></span>}
                  {match.status}
                </span>
              </div>
              
              <div className="team-line">
                <span className="team-code">{match.matchName?.split(' vs ')[0] || "HOME"}</span>
                <span className="team-score">{match.score?.home?.score || '-'} <span className="overs-sub">({match.score?.home?.info || '0 ov'})</span></span>
              </div>
              <div className="team-line">
                <span className="team-code">{match.matchName?.split(' vs ')[1] || "AWAY"}</span>
                <span className="team-score">{match.score?.away?.score || '-'} <span className="overs-sub">({match.score?.away?.info || '0 ov'})</span></span>
              </div>

              {isExpanded && (
                <div className="expanded-drawer" onClick={e => e.stopPropagation()}>
                  <div className="tab-menu">
                    {['batting', 'bowling', 'commentary'].map(t => (
                      <button key={t} onClick={() => setActiveTab(t)} className={`tab-link ${activeTab === t ? 'active' : ''}`}>{t}</button>
                    ))}
                  </div>

                  {detailLoading ? (
                    <div className="loader">DRILLING STATISTICS...</div>
                  ) : (
                    <div className="tab-viewport">
                      {activeTab === 'batting' && (
                        <div className="stats-grid font-mono">
                          {(matchData.batsmen || [{name:"Batsman Active", runs:44, balls:22, boundaries:"5/2"}]).map((b, i) => (
                            <div key={i} className="grid-row"><span>{b.name}</span><span>{b.runs}({b.balls})</span><span>{b.boundaries}</span></div>
                          ))}
                        </div>
                      )}

                      {activeTab === 'bowling' && (
                        <div className="stats-grid font-mono">
                          {(matchData.bowlers || [{name:"Bowler Active", overs:3.2, runs:19, wickets:2}]).map((b, i) => (
                            <div key={i} className="grid-row"><span>{b.name}</span><span>{b.overs} ov</span><span>{b.wickets}W</span></div>
                          ))}
                        </div>
                      )}

                      {activeTab === 'commentary' && (
                        <div className="commentary-list font-mono">
                          {(matchData.commentary || [{over:"19.4", event:"SIX", desc:"Clean pull over deep square boundary."}]).map((c, i) => (
                            <div key={i} className="comm-row"><strong>{c.over}</strong> <span>[{c.event}] {c.desc}</span></div>
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

        {/* Fallback Scheduling & Mock Engine if active stream arrays are quiet */}
        {matches.length === 0 && (
          <>
            {upcoming.length > 0 ? (
              upcoming.map((match, idx) => (
                <div key={match.id || idx} className="match-card scheduled">
                  <div className="match-card-head">
                    <span className="series-tag">📍 {match.venue || "TBD VENUE"}</span>
                    <span className="upcoming-tag">UPCOMING</span>
                  </div>
                  <div className="team-line" style={{margin: '12px 0'}}>
                    <span className="team-code" style={{fontSize: '15px'}}>{match.matchName}</span>
                  </div>
                  <div className="chase-line font-mono">{match.startTime || "SCHEDULED MATCH"}</div>
                </div>
              ))
            ) : (
              /* High Fidelity Mock Core keeps layout structured when API streams have 0 matches scheduled */
              <div className="match-card">
                <div className="match-card-head">
                  <span className="series-tag">IPL 2026 · DEMO CHANNELS</span>
                  <span className="live-tag"><span className="live-dot"></span>LIVE</span>
                </div>
                <div className="team-line">
                  <span className="team-code">GT</span>
                  <span className="team-score">181/5 <span className="overs-sub">(19.4)</span></span>
                </div>
                <div className="team-line">
                  <span className="team-code">KKR ▸</span>
                  <span className="team-score">156/6 <span className="overs-sub">(17.2)</span></span>
                </div>
                <div className="chase-line">need 26 off 16</div>
              </div>
            )}
          </>
        )}
      </div>

      <style jsx>{`
        .carousel-wrap { margin-bottom: 24px; width: 100%; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; width: 100%; }
        .match-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 320px; flex-shrink: 0; padding: 16px; position: relative; cursor: pointer; }
        .match-card:hover { border-color: rgba(240,242,245,0.2); }
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--blood-red); }
        .match-card.scheduled::before { background: var(--bail-amber); }
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; display: flex; align-items: center; gap: 5px; font-weight: bold; }
        .upcoming-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--bail-amber); font-weight: bold; }
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; }
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--crease-white); letter-spacing: 0.03em; }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-weight: normal; }
        .chase-line { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--bail-amber); margin-top: 8px; text-transform: uppercase; }
        .loading-state { font-family: 'JetBrains Mono', monospace; color: rgba(240,242,245,0.4); font-size: 12px; padding: 20px 0; text-align: center; width: 100%; }
        .expanded-drawer { margin-top: 16px; border-top: 1px solid rgba(240,242,245,0.1); padding-top: 12px; cursor: default; }
        .tab-menu { display: flex; gap: 6px; margin-bottom: 12px; }
        .tab-link { background: transparent; border: 1px solid rgba(240,242,245,0.2); color: var(--crease-white); font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 4px 8px; cursor: pointer; border-radius: 2px; text-transform: uppercase; }
        .tab-link.active { background: var(--blood-red); border-color: var(--blood-red); }
        .stats-grid { display: flex; flex-direction: column; gap: 6px; font-size: 12px; }
        .grid-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid rgba(240,242,245,0.02); }
        .commentary-list { display: flex; flex-direction: column; gap: 8px; font-size: 11px; max-height: 150px; overflow-y: auto; }
        .comm-row { display: flex; gap: 8px; background: rgba(0,0,0,0.2); padding: 6px; border-radius: 2px; }
        .comm-row strong { color: var(--bail-amber); }
        .loader { font-family: 'JetBrains Mono', monospace; font-size: 11px; opacity: 0.5; padding: 10px 0; text-align: center; }
        @keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
      `}</style>
    </div>
  );
}
