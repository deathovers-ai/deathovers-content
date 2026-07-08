import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // State for Full-Page Takeover
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  
  // Tab State
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
    setActiveTab('inn2'); // Default to current chase

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
    window.scrollTo(0, 0);
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
    chaseNote: "need 26 off 16"
  }];

  const activeData = activeMatchId ? (matchDetails[activeMatchId] || {
    toss: "GT won, elected to bat",
    venue: "Narendra Modi Stadium, Ahmedabad",
    recentBalls: [{b: '1', c: ''}, {b: '0', c: ''}, {b: 'W', c: 'wicket'}, {b: '4', c: 'boundary'}, {b: '6', c: 'boundary'}, {b: '1', c: 'latest'}],
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
        {name: "S. Narine", o: "4.0", r: "28", w: "1", eco: "7.0"},
        {name: "A. Russell", o: "4.0", r: "41", w: "2", eco: "10.2"}
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
        {name: "M. Starc*", o: "3.2", r: "24", w: "1", eco: "7.2"},
        {name: "R. Sai Kishore", o: "4.0", r: "22", w: "2", eco: "5.5"}
      ]
    },
    commentary: [
      { over: "17.3", type: "run", text: "Driven for 1, good running." },
      { over: "17.2", type: "four", text: "FOUR! Punched through covers, races away." },
      { over: "17.1", type: "six", text: "SIX! Pulled into the crowd over midwicket!" },
      { over: "16.6", type: "wicket", text: "STARC STRIKES! Yorker, castled! Big wicket." },
      { over: "16.5", type: "dot", text: "Starc to Rana, dot ball, beaten outside off." },
      { over: "16.4", type: "run", text: "Pushed to cover for a quick single." },
      { over: "16.3", type: "run", text: "Tucked away off the pads for one." },
      { over: "16.2", type: "four", text: "FOUR! Brilliant timing, beats the diving fielder." },
      { over: "16.1", type: "dot", text: "Play and a miss, excellent delivery." }
    ]
  }) : null;
  
  const activeMatchMeta = displayMatches.find(m => m.id === activeMatchId);

  // Dynamic Commentary Styling Engine
  const styleFor = {
    wicket: { bg: 'rgba(232,0,58,0.12)',  border: '#E8003A', label: '#E8003A', labelText: 'WICKET', size: '11px', weight: '700' },
    six:    { bg: 'rgba(245,166,35,0.12)', border: '#F5A623', label: '#F5A623', labelText: 'SIX',    size: '11px', weight: '700' },
    four:   { bg: 'rgba(245,166,35,0.08)', border: '#F5A623', label: '#F5A623', labelText: 'FOUR',   size: '11px', weight: '500' },
    run:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.4)', labelText: '', size: '11px', weight: '400' },
    dot:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.3)', labelText: '', size: '11px', weight: '400' }
  };

  return (
    <div className="live-engine-wrapper">
      
      {/* ================= VIEW 1: CAROUSEL ================= */}
      {!activeMatchId && (
        <div className="carousel-wrap">
          <div className="section-label">LIVE NOW</div>
          <div className="carousel-track">
            
            {displayMatches.map((match) => (
              <div key={match.id} className="match-card" onClick={() => openMatch(match.id)}>
                <div className="match-card-head">
                  <span className="series-tag">{match.venue || "INTERNATIONAL"}</span>
                  <span className="live-tag">
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

                <div className="chase-line">{match.chaseNote || "IN PROGRESS"}</div>
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

      {/* ================= VIEW 2: FULL WIDTH MATCH PAGE ================= */}
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
            
            {/* HUD / Toss Block */}
            <div className="over-block">
              <div className="over-toss-row">
                <div>
                  <div className="over-label">CURRENT OVER · {activeData.currentBowler}</div>
                  <div className="over-dots">
                    {activeData.recentBalls.map((ball, idx) => (
                      <div key={idx} className={`over-dot ${ball.c}`}>{ball.b}</div>
                    ))}
                  </div>
                </div>
                <div className="toss-strip">
                  <div className="toss-kicker">TOSS</div>
                  <div className="toss-line">{activeData.toss}</div>
                  <div className="toss-sub">{activeData.venue}</div>
                </div>
              </div>
            </div>

            <div className="mp-content-panoramic">
              {detailLoading ? (
                <div className="loading-state font-mono">PULLING LIVE TELEMETRY...</div>
              ) : (
                <>
                  {/* COLUMN 1: 1ST INNINGS (TARGET) */}
                  <div className="innings-col">
                    <div className="inn-heading highlight-inn1">
                      1ST INNINGS: {activeData.innings1.team} · {activeData.innings1.score} ({activeData.innings1.overs})
                    </div>
                    
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
                    
                    <div className="stat-kicker" style={{marginTop: '16px'}}>BOWLING</div>
                    <table className="stat-table">
                      <thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECO</th></tr></thead>
                      <tbody>
                        {activeData.innings1.bowlers.map((bw, i) => (
                          <tr key={i}>
                            <td>{bw.name}</td><td>{bw.o}</td><td>{bw.r}</td><td>{bw.w}</td><td>{bw.eco}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* COLUMN 2: 2ND INNINGS (CHASE) */}
                  <div className="innings-col border-left">
                    <div className="inn-heading highlight-inn2">
                      2ND INNINGS: {activeData.innings2.team} · {activeData.innings2.score} ({activeData.innings2.overs})
                    </div>
                    
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
                    
                    <div className="stat-kicker" style={{marginTop: '16px'}}>BOWLING</div>
                    <table className="stat-table">
                      <thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECO</th></tr></thead>
                      <tbody>
                        {activeData.innings2.bowlers.map((bw, i) => (
                          <tr key={i}>
                            <td>{bw.name}</td><td>{bw.o}</td><td>{bw.r}</td><td style={{color: 'var(--blood-red)', fontWeight: 'bold'}}>{bw.w}</td><td>{bw.eco}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* COLUMN 3: LIVE COMMENTARY */}
                  <div className="mp-commentary-rail border-left">
                    <div className="rail-label"><span className="live-dot"></span>LIVE COMMENTARY</div>
                    <div id="feed">
                      {activeData.commentary.map((c, i) => {
                        const s = styleFor[c.type] || styleFor.dot;
                        return (
                          <div key={i} className="feed-row ball-new" style={{ background: s.bg, borderLeftColor: s.border }}>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '5px', marginBottom: '2px' }}>
                              <span className="feed-over-tag">{c.over}</span>
                              {s.labelText && <span className="feed-event-tag" style={{ color: s.label }}>{s.labelText}</span>}
                            </div>
                            <div className="feed-text" style={{ fontSize: s.size, fontWeight: s.weight }}>
                              {c.text}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .live-engine-wrapper { width: 100%; max-width: 1050px; margin: 0 auto; }
        
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
        .live-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--blood-red); display: flex; align-items: center; gap: 5px; font-weight: bold; }
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

        /* MATCH PAGE TAKEOVER */
        .matchpage { padding: 0 24px 20px; animation: ballIn 0.3s ease-out; }
        .back-btn { background: none; border: none; color: rgba(240,242,245,0.5); font-size: 11px; font-family: 'JetBrains Mono', monospace; margin-bottom: 14px; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 0; transition: color 0.2s; }
        .back-btn:hover { color: var(--crease-white); }

        .mp-header { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 4px 4px 0 0; padding:
