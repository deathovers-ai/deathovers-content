import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // State for the Full-Page Takeover
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  
  // State for the internal tabs of the Match Page
  const [activeTab, setActiveTab] = useState('inn2');

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

  const openMatch = async (matchId) => {
    setActiveMatchId(matchId);
    setDetailLoading(true);
    // Default to the current innings tab when opening
    setActiveTab('inn2');

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

  const closeMatch = () => {
    setActiveMatchId(null);
  };

  if (loading) {
    return <div className="loading-state font-mono">ESTABLISHING SECURE UPLINK TO DATA CLUSTER...</div>;
  }

  const displayMatches = matches.length > 0 ? matches : [{
    id: "mock-channel", venue: "IPL 2026 · Q2", status: "LIVE", matchName: "GT vs KKR",
    score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
    chaseNote: "Need 26 off 16"
  }];

  // Detailed Data Mock for the Dashboard
  const activeData = activeMatchId ? (matchDetails[activeMatchId] || {
    toss: "GT won the toss and elected to bat first.",
    venue: "Narendra Modi Stadium, Ahmedabad",
    pitch: "Flat, favors batters early, slows down later.",
    recentBalls: [{b: '1', c: 'latest'}, {b: '6', c: 'boundary'}, {b: '4', c: 'boundary'}, {b: 'W', c: 'wicket'}, {b: '0', c: ''}, {b: '1', c: ''}],
    currentBowler: "M. Starc (3.2-0-24-1)",
    innings1: { 
      team: "GT", score: "181/5", overs: "20.0", 
      batters: [
        {name: "S. Gill*", r: 72, b: 45, sr: "160.0"}, 
        {name: "B. Sai Sudharsan", r: 58, b: 39, sr: "148.7"},
        {name: "D. Miller", r: 24, b: 14, sr: "171.4"},
        {name: "R. Tewatia", r: 11, b: 9, sr: "122.2", dim: true}
      ],
      bowlers: [
        {name: "S. Narine", o: "4.0", r: "28", w: "1", eco: "7.00"},
        {name: "A. Russell", o: "4.0", r: "41", w: "2", eco: "10.25"}
      ]
    },
    innings2: { 
      team: "KKR", score: "156/6", overs: "17.2", 
      batters: [
        {name: "V. Iyer*", r: 62, b: 34, sr: "182.3"}, 
        {name: "R. Singh", r: 19, b: 11, sr: "172.7"},
        {name: "S. Rana", r: 28, b: 16, sr: "175.0", dim: true}
      ],
      bowlers: [
        {name: "M. Starc*", o: "3.2", r: "24", w: "1", eco: "7.20"},
        {name: "R. Sai Kishore", o: "4.0", r: "22", w: "2", eco: "5.50"}
      ]
    },
    commentary: [
      { over: "17.2", type: "four", tag: "FOUR", text: "FOUR! Punched through covers, races away." },
      { over: "17.1", type: "six", tag: "SIX", text: "SIX! Pulled into the crowd over midwicket!" },
      { over: "16.6", type: "wicket", tag: "WICKET", text: "STARC STRIKES! Yorker, castled! Big wicket." },
      { over: "16.5", type: "dot", tag: "", text: "Starc to Rana, dot ball, beaten outside off." },
      { over: "16.4", type: "run", tag: "", text: "Driven down the ground for a single." }
    ]
  }) : null;
  
  const activeMatchMeta = displayMatches.find(m => m.id === activeMatchId);

  return (
    <div className="live-engine-wrapper">
      
      {/* ================= VIEW 1: THE CAROUSEL ================= */}
      {!activeMatchId && (
        <div className="carousel-wrap">
          <div className="section-label">LIVE NOW</div>
          <div className="carousel-track">
            
            {displayMatches.map((match) => (
              <div key={match.id} className="match-card" onClick={() => openMatch(match.id)}>
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
                  <div className="chase-line">{match.chaseNote || "IN PROGRESS"}</div>
                )}
                <div className="tap-hint">TAP FOR FULL SCORECARD ▾</div>
              </div>
            ))}

            <div className="peek-card">
              <div className="peek-label">NEXT ▸</div>
              <div className="peek-teams">ESSEX W v SOM W</div>
            </div>

          </div>
        </div>
      )}


      {/* ================= VIEW 2: THE MATCH DASHBOARD ================= */}
      {activeMatchId && activeData && activeMatchMeta && (
        <div className="matchpage">
          <button className="back-btn" onClick={closeMatch}>← BACK TO LIVE MATCHES</button>

          <div className="mp-header">
            <div className="match-card-head">
              <span className="series-tag">{activeMatchMeta.venue}</span>
              <span className="live-tag"><span className="live-dot"></span>LIVE</span>
            </div>
            <div className="mp-team-line">
              <span className="mp-team-code">{activeMatchMeta.matchName.split(' vs ')[0]}</span>
              <span className="mp-team-score">{activeMatchMeta.score.home.score} <span className="overs-sub">({activeMatchMeta.score.home.info})</span></span>
            </div>
            <div className="mp-team-line">
              <span className="mp-team-code">{activeMatchMeta.matchName.split(' vs ')[1]}</span>
              <span className="mp-team-score">{activeMatchMeta.score.away.score} <span className="overs-sub">({activeMatchMeta.score.away.info})</span></span>
            </div>
            <div className="mp-chase">{activeMatchMeta.chaseNote}</div>
          </div>

          <div className="mp-body">
            
            {/* Dot Ball Tracker */}
            <div className="over-block">
              <div className="over-label">CURRENT OVER · {activeData.currentBowler}</div>
              <div className="over-dots">
                {activeData.recentBalls.map((ball, idx) => (
                  <div key={idx} className={`over-dot ${ball.c}`}>{ball.b}</div>
                ))}
              </div>
            </div>

            {/* Internal Tabs */}
            <div className="tab-bar">
              <button className={`tab-btn ${activeTab === 'toss' ? 'active' : ''}`} onClick={() => setActiveTab('toss')}>TOSS</button>
              <button className={`tab-btn ${activeTab === 'inn1' ? 'active' : ''}`} onClick={() => setActiveTab('inn1')}>1ST INNINGS</button>
              <button className={`tab-btn ${activeTab === 'inn2' ? 'active' : ''}`} onClick={() => setActiveTab('inn2')}>2ND INNINGS</button>
            </div>

            <div className="mp-content-row">
              
              {/* LEFT SIDE: Data Panes */}
              <div className="mp-tabpanes">
                {detailLoading ? (
                  <div className="loading-state font-mono">PULLING LIVE TELEMETRY...</div>
                ) : (
                  <>
                    {activeTab === 'toss' && (
                      <div className="tab-pane active">
                        <div className="pane-kicker">TOSS</div>
                        <div className="pane-body">{activeData.toss}</div>
                        <div className="pane-sub">Venue: {activeData.venue}</div>
                        <div className="pane-sub" style={{marginTop: '4px'}}>Pitch: {activeData.pitch}</div>
                      </div>
                    )}

                    {activeTab === 'inn1' && (
                      <div className="tab-pane active">
                        <div className="inn-heading">1ST INNINGS: {activeData.innings1.team} · {activeData.innings1.score} ({activeData.innings1.overs})</div>
                        
                        <div className="stat-kicker">BATTING</div>
                        <table className="stat-table">
                          <thead><tr><th>BATTER</th><th>R</th><th>B</th><th>SR</th></tr></thead>
                          <tbody>
                            {activeData.innings1.batters.map((b, i) => (
                              <tr key={i} className={b.dim ? 'dim' : ''}>
                                <td>{b.name}</td><td>{b.r}</td><td>{b.b}</td><td>{b.sr}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        
                        <div className="stat-kicker">BOWLING</div>
                        <table className="stat-table">
                          <thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECO</th></tr></thead>
                          <tbody>
                            {activeData.innings1.bowlers.map((bw, i) => (
                              <tr key={i}>
                                <td>{bw.name}</td><td>{bw.o}</td><td>{bw.r}</td><td style={{color: 'var(--bail-amber)', fontWeight: 'bold'}}>{bw.w}</td><td>{bw.eco}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {activeTab === 'inn2' && (
                      <div className="tab-pane active">
                        <div className="inn-heading">2ND INNINGS: {activeData.innings2.team} · {activeData.innings2.score} ({activeData.innings2.overs})</div>
                        
                        <div className="stat-kicker">BATTING</div>
                        <table className="stat-table">
                          <thead><tr><th>BATTER</th><th>R</th><th>B</th><th>SR</th></tr></thead>
                          <tbody>
                            {activeData.innings2.batters.map((b, i) => (
                              <tr key={i} className={b.dim ? 'dim' : ''}>
                                <td>{b.name}</td><td>{b.r}</td><td>{b.b}</td><td>{b.sr}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        
                        <div className="stat-kicker">BOWLING</div>
                        <table className="stat-table">
                          <thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECO</th></tr></thead>
                          <tbody>
                            {activeData.innings2.bowlers.map((bw, i) => (
                              <tr key={i}>
                                <td>{bw.name}</td><td>{bw.o}</td><td>{bw.r}</td><td style={{color: 'var(--bail-amber)', fontWeight: 'bold'}}>{bw.w}</td><td>{bw.eco}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
              </div>

              {/* RIGHT SIDE: ESPN-Style Commentary Rail */}
              <div className="mp-commentary-rail">
                <div className="rail-label"><span className="live-dot"></span>LIVE COMMENTARY</div>
                <div className="feed">
                  {activeData.commentary.map((c, i) => {
                    const isWicket = c.type === 'wicket';
                    const isBoundary = c.type === 'six' || c.type === 'four';
                    
                    let bg = 'transparent';
                    let border = 'rgba(240,242,245,0.08)';
                    let tagColor = '';
                    
                    if (isWicket) { bg = 'rgba(232,0,58,0.12)'; border = '#E8003A'; tagColor = '#E8003A'; }
                    if (c.type === 'six') { bg = 'rgba(245,166,35,0.12)'; border = '#F5A623'; tagColor = '#F5A623'; }
                    if (c.type === 'four') { bg = 'rgba(245,166,35,0.08)'; border = '#F5A623'; tagColor = '#F5A623'; }

                    return (
                      <div key={i} className="feed-row ball-new" style={{ background: bg, borderLeftColor: border }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '5px', marginBottom: '2px' }}>
                          <span className="feed-over-tag">{c.over}</span>
                          {c.tag && <span className="feed-event-tag" style={{ color: tagColor }}>{c.tag}</span>}
                        </div>
                        <div className="feed-text" style={{ fontWeight: isWicket || c.type === 'six' ? '700' : '400' }}>
                          {c.text}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .live-engine-wrapper { width: 100%; }
        
        @keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes ballIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
        
        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; display: inline-block; }
        .ball-new { animation: ballIn 0.4s ease-out; }

        /* CAROUSEL STYLES */
        .section-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); letter-spacing: 0.05em; margin-bottom: 10px; padding: 0 24px; }
        .carousel-wrap { padding: 20px 0; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding: 0 24px 12px; }
        .match-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 280px; flex-shrink: 0; padding: 16px; position: relative; cursor: pointer; transition: border-color 0.15s ease, transform 0.2s ease; }
        .match-card:hover { border-color: rgba(232,0,58,0.4); transform: translateY(-2px); }
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--blood-red); }
        .match-card-head { display: flex; justify-content: space-between; margin-bottom: 10px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); }
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--blood-red); display: flex; alignItems: center; gap: 5px; font-weight: bold; }
        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 19px; color: var(--crease-white); }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 700; color: var(--crease-white); }
        .overs-sub { font-size: 12px; color: rgba(240,242,245,0.4); font-family: 'Inter', sans-serif; font-weight: 400; }
        .chase-line { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--bail-amber); margin-top: 8px; }
        .tap-hint { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); margin-top: 10px; text-align: center; letter-spacing: 0.05em; transition: color 0.2s; }
        .match-card:hover .tap-hint { color: var(--blood-red); }

        .peek-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px; width: 140px; flex-shrink: 0; padding: 14px; opacity: 0.4; display: flex; flex-direction: column; justify-content: center; }
        .peek-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 6px; }
        .peek-teams { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--crease-white); }

        /* MATCH PAGE FULL TAKEOVER STYLES */
        .matchpage { padding: 0 24px 20px; animation: ballIn 0.3s ease-out; }
        .back-btn { background: none; border: none; color: rgba(240,242,245,0.5); font-size: 11px; font-family: 'JetBrains Mono', monospace; margin-bottom: 14px; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 0; transition: color 0.2s; }
        .back-btn:hover { color: var(--crease-white); }

        .mp-header { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px 4px 0 0; padding: 16px; position: relative; }
        .mp-header::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--blood-red); }
        .mp-team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
        .mp-team-code { font-family: 'Bebas Neue', sans-serif; font-size: 22px; color: var(--crease-white); letter-spacing: 0.02em; }
        .mp-team-score { font-family: 'JetBrains Mono', monospace; font-size: 19px; font-weight: 700; color: var(--crease-white); }
        .mp-chase { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--bail-amber); margin-top: 8px; font-weight: bold; }

        .mp-body { background: var(--pitch-black); border: 1px solid rgba(232,0,58,0.2); border-top: none; border-radius: 0 0 4px 4px; overflow: hidden; }

        .over-block { padding: 12px 16px; border-bottom: 1px solid rgba(240,242,245,0.08); }
        .over-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); margin-bottom: 6px; text-transform: uppercase; }
        .over-dots { display: flex; gap: 5px; }
        .over-dot { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: bold; background: #1c1c1f; color: var(--crease-white); }
        .over-dot.wicket { background: var(--blood-red); color: #fff; box-shadow: 0 0 6px rgba(232,0,58,0.5); }
        .over-dot.boundary { background: var(--bail-amber); color: #1a1206; }
        .over-dot.latest { border: 1px solid rgba(232,0,58,0.6); }

        .tab-bar { display: flex; border-bottom: 1px solid rgba(240,242,245,0.08); }
        .tab-btn { flex: 1; padding: 10px 0; font-size: 10px; letter-spacing: 0.05em; font-family: 'JetBrains Mono', monospace; font-weight: bold; background: none; border: none; border-bottom: 2px solid transparent; color: rgba(240,242,245,0.45); cursor: pointer; transition: all 0.2s; }
        .tab-btn:hover { color: #fff; }
        .tab-btn.active { border-bottom-color: var(--blood-red); color: var(--blood-red); }

        .mp-content-row { display: flex; align-items: stretch; }
        .mp-tabpanes { flex: 1 1 0; min-width: 0; padding: 16px; max-height: 340px; overflow-y: auto; }
        .mp-tabpanes::-webkit-scrollbar { width: 4px; }
        .mp-tabpanes::-webkit-scrollbar-thumb { background: rgba(240,242,245,0.2); border-radius: 4px; }

        .pane-kicker { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); letter-spacing: 0.05em; margin-bottom: 8px; font-weight: bold; }
        .pane-body { font-size: 12px; color: var(--crease-white); margin-bottom: 6px; line-height: 1.5; }
        .pane-sub { font-size: 11px; color: rgba(240,242,245,0.45); }

        .inn-heading { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--bail-amber); letter-spacing: 0.05em; margin-bottom: 12px; font-weight: bold; }
        .stat-kicker { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); margin-bottom: 4px; font-weight: bold; }
        .stat-table { width: 100%; font-size: 11px; border-collapse: collapse; margin-bottom: 16px; color: var(--crease-white); }
        .stat-table th { font-family: 'JetBrains Mono', monospace; color: rgba(240,242,245,0.35); font-size: 9px; font-weight: 400; text-align: right; padding: 4px 0; border-bottom: 1px solid rgba(240,242,245,0.05); }
        .stat-table th:first-child { text-align: left; }
        .stat-table td { padding: 6px 0; text-align: right; border-bottom: 1px solid rgba(240,242,245,0.03); }
        .stat-table td:first-child { text-align: left; font-weight: 500; font-family: 'Inter', sans-serif; }
        .stat-table td { font-family: 'JetBrains Mono', monospace; }
        .stat-table .dim td { color: rgba(240,242,245,0.4); font-weight: 400; }

        .mp-commentary-rail { width: 220px; flex-shrink: 0; border-left: 1px solid rgba(240,242,245,0.08); background: #0e1015; padding: 14px 16px; display: flex; flex-direction: column; }
        .rail-label { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--blood-red); letter-spacing: 0.08em; font-weight: 700; }
        
        .feed { max-height: 300px; overflow-y: auto; display: flex; flex-direction: column; padding-right: 4px; }
        .feed::-webkit-scrollbar { width: 3px; }
        .feed::-webkit-scrollbar-thumb { background: rgba(240,242,245,0.15); border-radius: 4px; }
        .feed-row { padding: 8px; margin-bottom: 8px; border-left: 2px solid rgba(240,242,245,0.08); border-radius: 0 4px 4px 0; }
        .feed-over-tag { font-family: 'JetBrains Mono', monospace; color: var(--bail-amber); font-size: 9px; font-weight: 700; }
        .feed-event-tag { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 9px; letter-spacing: 0.04em; }
        .feed-text { font-size: 11px; color: var(--crease-white); line-height: 1.4; margin-top: 4px; }

        .loading-state { color: rgba(240,242,245,0.4); font-size: 11px; padding: 24px 0; text-align: center; width: 100%; }

        @media (max-width: 640px) {
          .mp-content-row { flex-direction: column; }
          .mp-commentary-rail { width: auto; border-left: none; border-top: 1px solid rgba(240,242,245,0.08); }
          .feed { max-height: 200px; }
        }
      `}</style>
    </div>
  );
}
