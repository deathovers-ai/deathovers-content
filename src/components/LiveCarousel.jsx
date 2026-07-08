import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
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
    window.scrollTo(0, 0);
  };

  const closeMatch = () => setActiveMatchId(null);

  if (loading) return <div className="loading-state font-mono">ESTABLISHING SECURE UPLINK...</div>;

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
    innings1: { team: "GT", score: "181/5", overs: "20.0", batters: [{name: "S. Gill*", r: 72, b: 45, sr: "160.0"}], bowlers: [{name: "S. Narine", o: "4.0", r: "28", w: "1", eco: "7.0"}] },
    innings2: { team: "KKR", score: "156/6", overs: "17.2", batters: [{name: "V. Iyer*", r: 62, b: 34, sr: "182.3"}], bowlers: [{name: "M. Starc*", o: "3.2", r: "24", w: "1", eco: "7.2"}] },
    commentary: [{ over: "17.3", type: "run", text: "Driven for 1, good running." }, { over: "17.2", type: "four", text: "FOUR! Punched through covers." }]
  }) : null;
  
  const activeMatchMeta = displayMatches.find(m => m.id === activeMatchId);

  const styleFor = {
    wicket: { bg: 'rgba(232,0,58,0.12)', border: '#E8003A', label: '#E8003A', labelText: 'WICKET', size: '11px', weight: '700' },
    six:    { bg: 'rgba(245,166,35,0.12)', border: '#F5A623', label: '#F5A623', labelText: 'SIX',    size: '11px', weight: '700' },
    four:   { bg: 'rgba(245,166,35,0.08)', border: '#F5A623', label: '#F5A623', labelText: 'FOUR',   size: '11px', weight: '500' },
    run:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.4)', labelText: '', size: '11px', weight: '400' },
    dot:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.3)', labelText: '', size: '11px', weight: '400' }
  };

  return (
    <div className="live-engine-wrapper">
      {!activeMatchId ? (
        <div className="carousel-wrap">
          <div className="section-label">LIVE NOW</div>
          <div className="carousel-track">
            {displayMatches.map((match) => (
              <div key={match.id} className="match-card" onClick={() => openMatch(match.id)}>
                <div className="match-card-head"><span className="series-tag">{match.venue}</span><span className="live-tag"><span className="live-dot"></span>{match.status}</span></div>
                <div className="team-line"><span className="team-code">{match.matchName?.split(' vs ')[0]}</span><span className="team-score">{match.score?.home?.score} <span className="overs-sub">({match.score?.home?.info})</span></span></div>
                <div className="team-line"><span className="team-code">{match.matchName?.split(' vs ')[1]}</span><span className="team-score">{match.score?.away?.score} <span className="overs-sub">({match.score?.away?.info})</span></span></div>
                <div className="chase-line">{match.chaseNote}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="matchpage">
          <button className="back-btn" onClick={closeMatch}>← BACK TO LIVE MATCHES</button>
          <div className="mp-header">
            <div className="mp-team-line"><span className="mp-team-code">{activeMatchMeta.matchName.split(' vs ')[0]}</span><span className="mp-team-score">{activeMatchMeta.score.home.score}</span></div>
            <div className="mp-team-line"><span className="mp-team-code">{activeMatchMeta.matchName.split(' vs ')[1]}</span><span className="mp-team-score">{activeMatchMeta.score.away.score}</span></div>
          </div>
          <div className="mp-body">
            <div className="mp-content-panoramic">
              <div className="innings-col">
                <div className="inn-heading highlight-inn1">1ST INNING</div>
                {/* Scorecard Table implementation ... */}
              </div>
              <div className="innings-col border-left">
                <div className="inn-heading highlight-inn2">2ND INNING</div>
              </div>
              <div className="mp-commentary-rail border-left">
                <div className="rail-label">COMMENTARY</div>
                <div id="feed">
                  {activeData.commentary.map((c, i) => {
                    const s = styleFor[c.type] || styleFor.dot;
                    return (
                      <div key={i} className="feed-row" style={{ background: s.bg, borderLeftColor: s.border }}>
                        <span className="feed-over-tag">{c.over}</span>
                        <div className="feed-text">{c.text}</div>
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
        .live-engine-wrapper { width: 100%; max-width: 1050px; margin: 0 auto; }
        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding: 0 24px; }
        .match-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); padding: 16px; width: 280px; cursor: pointer; }
        .matchpage { padding: 20px 24px; }
        .mp-content-panoramic { display: grid; grid-template-columns: 1fr 1fr 1.2fr; min-height: 400px; }
        #feed { max-height: 380px; overflow-y: auto; padding-right: 4px; }
        #feed::-webkit-scrollbar { width: 3px; }
        #feed::-webkit-scrollbar-thumb { background: rgba(240,242,245,0.15); }
      `}</style>
    </div>
  );
}
