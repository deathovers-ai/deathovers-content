import React, { useState, useEffect } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);

  // State for Full-Page Takeover
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);

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

  // --- SORTING AND FILTERING LOGIC ---
  // LIVE matches always surface first (deterministic, not incidental —
  // filtered explicitly by status rather than relying on API ordering),
  // then UPCOMING, then a capped tail of recently COMPLETED matches so the
  // rail doesn't get flooded with old results.
  let displayMatches = [];
  if (matches.length > 0) {
    const live = matches.filter(m => m.status === 'LIVE');
    const upcoming = matches.filter(m => m.status === 'UPCOMING');
    const completed = matches.filter(m => m.status === 'COMPLETED').slice(0, 3);

    displayMatches = [...live, ...upcoming, ...completed];
  } else {
    displayMatches = [{
      id: "mock-channel", venue: "IPL 2026 · Q2", status: "LIVE", matchName: "GT vs KKR",
      score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
      chaseNote: "need 26 off 16"
    }];
  }

  const activeData = activeMatchId ? (matchDetails[activeMatchId] || null) : null;
  const activeMatchMeta = displayMatches.find(m => m.id === activeMatchId);

  // An innings that has not started yet comes back as `null` from the
  // backend (see app.py) rather than an empty object — that's the signal
  // to hide the column/card entirely instead of rendering a fake
  // "TBD · 0/0" placeholder, which is what made the detail view look
  // broken whenever a match was still in its first innings.
  const inn1 = activeData?.innings1 || null;
  const inn2 = activeData?.innings2 || null;
  const hasCommentary = (activeData?.commentary?.length || 0) > 0;

  return (
    <div className="live-engine-wrapper">

      {/* ================= VIEW 1: CAROUSEL ================= */}
      {!activeMatchId && (
        <div className="carousel-wrap">
          <div className="section-label">LIVE NOW</div>
          <div className="carousel-track">

            {displayMatches.map((match) => {
              const isLive = match.status === 'LIVE';
              const awayIsPending = !match.score?.away || match.score.away.score === 'yet to bat';
              return (
                <div
                  key={match.id}
                  className={`match-card ${isLive ? 'is-live' : ''}`}
                  onClick={() => openMatch(match.id)}
                >
                  <div className="match-card-head">
                    <span className="series-tag">{match.venue || "INTERNATIONAL"}</span>
                    <span className={`status-tag ${isLive ? 'status-live' : 'status-done'}`}>
                      {isLive && <span className="live-dot"></span>}
                      {match.status}
                    </span>
                  </div>

                  <div className="team-line">
                    <span className="team-code">{match.matchName?.split(' vs ')[0] || "HOME"}</span>
                    <span className="team-score">
                      {match.score?.home?.score || '-'}
                      <span className="overs-sub"> ({match.score?.home?.info || ''})</span>
                    </span>
                  </div>
                  <div className={`team-line ${awayIsPending ? 'team-line-pending' : ''}`}>
                    <span className="team-code">{match.matchName?.split(' vs ')[1] || "AWAY"}</span>
                    <span className="team-score">
                      {awayIsPending ? (
                        <span className="pending-label">yet to bat</span>
                      ) : (
                        <>{match.score.away.score}<span className="overs-sub"> ({match.score.away.info || ''})</span></>
                      )}
                    </span>
                  </div>

                  <div className="chase-line">{match.chaseNote || "IN PROGRESS"}</div>
                  <div className="tap-hint">TAP FOR FULL SCORECARD ▾</div>
                </div>
              );
            })}

            <div className="peek-card">
              <div className="peek-label">NEXT ▸</div>
              <div className="peek-teams">ESSEX W v SOM W</div>
            </div>

          </div>
        </div>
      )}

      {/* ================= VIEW 2: FULL WIDTH MATCH PAGE ================= */}
      {activeMatchId && activeMatchMeta && (
        <div className="matchpage">
          <button className="back-btn" onClick={closeMatch}>← BACK TO LIVE MATCHES</button>

          {detailLoading || !activeData ? (
            <div className="mp-header mp-header-loading">
              <div className="loading-state font-mono">PULLING LIVE TELEMETRY...</div>
            </div>
          ) : (
            <>
              {/* GLANCE SCOREBOARD — the whole match state in one look */}
              <div className="scoreboard">
                <div className="scoreboard-top">
                  <span className="series-tag">{activeMatchMeta.venue}</span>
                  <span className={`status-tag ${activeMatchMeta.status === 'LIVE' ? 'status-live' : 'status-done'}`}>
                    {activeMatchMeta.status === 'LIVE' && <span className="live-dot"></span>}
                    {activeMatchMeta.status}
                  </span>
                </div>

                <div className="scoreboard-grid">
                  <div className={`scoreboard-team ${!inn2 ? 'scoreboard-team-batting' : ''}`}>
                    <div className="sb-team-name">{inn1?.team || activeMatchMeta.matchName?.split(' vs ')[0]}</div>
                    <div className="sb-team-score">
                      {activeMatchMeta.score?.home?.score || '0/0'}
                      <span className="sb-overs">({activeMatchMeta.score?.home?.info || '0.0'})</span>
                    </div>
                  </div>

                  <div className="scoreboard-divider">
                    <span>VS</span>
                  </div>

                  <div className={`scoreboard-team scoreboard-team-right ${inn2 ? 'scoreboard-team-batting' : 'scoreboard-team-waiting'}`}>
                    <div className="sb-team-name">{inn2?.team || activeMatchMeta.matchName?.split(' vs ')[1]}</div>
                    <div className="sb-team-score">
                      {inn2 ? (
                        <>{activeMatchMeta.score?.away?.score}<span className="sb-overs">({activeMatchMeta.score?.away?.info || '0.0'})</span></>
                      ) : (
                        <span className="sb-pending">YET TO BAT</span>
                      )}
                    </div>
                  </div>
                </div>

                {activeMatchMeta.chaseNote && (
                  <div className="scoreboard-note">{activeMatchMeta.chaseNote}</div>
                )}

                <div className="scoreboard-toss">
                  <span className="toss-kicker">TOSS</span>
                  <span className="toss-line">{activeData.toss || 'Toss result unavailable'}</span>
                </div>
              </div>

              {/* INNINGS DETAIL + LIVE COMMENTARY — commentary rail is
                  always present; when no commentary source has data yet,
                  it shows a clear waiting state rather than being hidden,
                  since ball-by-ball commentary is a required feature here,
                  not an optional extra we quietly drop when a data source
                  is thin. See CRICKETDATA free tier note below — this is
                  a real gap to close with a commentary-capable source. */}
              <div className={`mp-body ${!inn2 ? 'mp-body-single' : ''}`}>
                {inn1 && <InningsPanel innings={inn1} accent="amber" label="1ST INNINGS" />}
                {inn2 && <InningsPanel innings={inn2} accent="red" label="2ND INNINGS" />}

                <div className="mp-commentary-rail">
                  <div className="rail-label"><span className="live-dot"></span>LIVE COMMENTARY</div>
                  {hasCommentary ? (
                    <div id="feed">
                      {activeData.commentary.map((c, i) => {
                        const s = styleFor[c.type] || styleFor.dot;
                        return (
                          <div key={i} className="feed-row ball-new" style={{ background: s.bg, borderLeftColor: s.border }}>
                            <div className="feed-row-head">
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
                  ) : (
                    <div className="commentary-waiting">
                      <div className="commentary-waiting-text">Ball-by-ball commentary not available for this match yet.</div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      <style>{`
        .live-engine-wrapper { width: 100%; max-width: 1050px; margin: 0 auto; }

        @keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes ballIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes cardRise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; display: inline-block; }
        .ball-new { animation: ballIn 0.4s ease-out; }

        /* CAROUSEL STYLES */
        .section-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); letter-spacing: 0.05em; margin-bottom: 10px; padding: 0 24px; }
        .carousel-wrap { padding: 20px 0; }

        .carousel-track { display: flex; gap: 12px; overflow-x: auto; padding: 0 24px 12px; min-height: 152px; }

        /* MATCH CARD — tighter, more consistent height; live cards get a
           slightly brighter border treatment to visually rank above
           completed ones without needing a badge to do all the work. */
        .match-card {
          background: var(--outfield);
          border: 1px solid rgba(240,242,245,0.08);
          border-radius: 6px;
          width: 272px;
          min-height: 148px;
          flex-shrink: 0;
          padding: 16px 18px;
          position: relative;
          cursor: pointer;
          transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          animation: cardRise 0.35s ease-out;
        }

        .match-card:hover { border-color: rgba(232,0,58,0.5); transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.35); }
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 6px 6px 0 0; background: rgba(240,242,245,0.12); }
        .match-card.is-live::before { background: var(--blood-red); }

        .match-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
        .series-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.5); line-height: 1.3; }

        .status-tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; display: flex; align-items: center; gap: 5px; font-weight: 700; letter-spacing: 0.04em; white-space: nowrap; flex-shrink: 0; }
        .status-live { color: var(--blood-red); }
        .status-done { color: rgba(240,242,245,0.35); }

        .team-line { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 7px; }
        .team-line-pending { opacity: 0.55; }
        .team-code { font-family: 'Bebas Neue', sans-serif; font-size: 18px; letter-spacing: 0.01em; color: var(--crease-white); }
        .team-score { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; color: var(--crease-white); }
        .pending-label { font-size: 11px; font-weight: 500; color: rgba(240,242,245,0.4); font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.04em; }
        .overs-sub { font-size: 11px; color: rgba(240,242,245,0.4); font-family: 'Inter', sans-serif; font-weight: 400; }
        .chase-line { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--bail-amber); margin-top: 6px; min-height: 14px; }
        .tap-hint { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.3); margin-top: 10px; text-align: center; letter-spacing: 0.05em; transition: color 0.2s; }
        .match-card:hover .tap-hint { color: var(--blood-red); }

        .peek-card { background: var(--outfield); border: 1px solid rgba(240,242,245,0.08); border-radius: 6px; width: 130px; flex-shrink: 0; padding: 14px; opacity: 0.4; display: flex; flex-direction: column; justify-content: center; }
        .peek-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.4); margin-bottom: 6px; }
        .peek-teams { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--crease-white); }

        /* MATCH PAGE TAKEOVER */
        .matchpage { padding: 0 24px 20px; animation: ballIn 0.3s ease-out; }
        .back-btn { background: none; border: none; color: rgba(240,242,245,0.5); font-size: 11px; font-family: 'JetBrains Mono', monospace; margin-bottom: 14px; cursor: pointer; display: flex; align-items: center; gap: 6px; padding: 0; transition: color 0.2s; }
        .back-btn:hover { color: var(--crease-white); }

        /* GLANCE SCOREBOARD — signature element. Both innings' key numbers
           readable in one look, stadium-board style, instead of a thin
           header line. This replaces the old cramped mp-header. */
        .scoreboard {
          background: var(--outfield);
          border: 1px solid rgba(240,242,245,0.08);
          border-radius: 8px 8px 0 0;
          padding: 20px 24px;
          position: relative;
        }
        .scoreboard::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 8px 8px 0 0; background: var(--blood-red); }

        .scoreboard-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }

        .scoreboard-grid { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 20px; }

        .scoreboard-team { display: flex; flex-direction: column; gap: 4px; opacity: 0.5; transition: opacity 0.2s; }
        .scoreboard-team-batting { opacity: 1; }
        .scoreboard-team-right { text-align: right; align-items: flex-end; }

        .sb-team-name { font-family: 'Bebas Neue', sans-serif; font-size: 22px; letter-spacing: 0.02em; color: var(--crease-white); line-height: 1; }
        .sb-team-score { font-family: 'JetBrains Mono', monospace; font-size: 30px; font-weight: 700; color: var(--crease-white); line-height: 1.15; letter-spacing: -0.01em; }
        .sb-overs { font-size: 13px; font-weight: 400; color: rgba(240,242,245,0.4); margin-left: 6px; }
        .sb-pending { font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600; color: rgba(240,242,245,0.35); letter-spacing: 0.04em; }

        .scoreboard-divider { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: rgba(240,242,245,0.25); font-weight: 700; text-align: center; }

        .scoreboard-note { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: var(--bail-amber); margin-top: 14px; }

        .scoreboard-toss { margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(240,242,245,0.06); display: flex; align-items: baseline; gap: 10px; }
        .toss-kicker { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); letter-spacing: 0.06em; flex-shrink: 0; }
        .toss-line { font-size: 12px; color: rgba(240,242,245,0.65); font-weight: 500; }

        .mp-header-loading { padding: 60px 24px; text-align: center; border-radius: 8px; }

        .mp-body { background: var(--pitch-black); border: 1px solid rgba(232,0,58,0.2); border-top: none; border-radius: 0 0 8px 8px; overflow: hidden; display: grid; grid-template-columns: 1fr 1fr 1.1fr; }
        .mp-body-single { grid-template-columns: 1fr 1.2fr; }

        /* No visible scrollbars — content is capped (see InningsPanel:
           top 5 batters / top 4 bowlers shown, rest available via
           expand) so panels size to their content instead of scrolling. */
        .innings-col { padding: 18px 20px; }
        .innings-col.border-left { border-left: 1px solid rgba(240,242,245,0.08); }

        .inn-heading { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.06em; margin-bottom: 14px; font-weight: 700; padding-bottom: 8px; border-bottom: 2px solid; }
        .inn-heading.accent-amber { color: var(--bail-amber); border-color: var(--bail-amber); }
        .inn-heading.accent-red { color: var(--blood-red); border-color: var(--blood-red); }

        .stat-kicker { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); margin-bottom: 6px; font-weight: 700; letter-spacing: 0.04em; }

        .stat-table { width: 100%; font-size: 12px; border-collapse: collapse; margin-bottom: 14px; color: var(--crease-white); }
        .stat-table th { font-family: 'JetBrains Mono', monospace; color: rgba(240,242,245,0.35); font-size: 9px; font-weight: 400; text-align: right; padding: 4px 0; border-bottom: 1px solid rgba(240,242,245,0.06); }
        .stat-table th:first-child { text-align: left; }
        .stat-table td { padding: 7px 0; text-align: right; border-bottom: 1px solid rgba(240,242,245,0.03); font-family: 'JetBrains Mono', monospace; }
        .stat-table td:first-child { text-align: left; font-weight: 500; font-family: 'Inter', sans-serif; }
        .stat-table .dim td { color: rgba(240,242,245,0.4); font-weight: 400; }
        .stat-more { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.3); text-align: center; padding-top: 2px; }

        .mp-commentary-rail { background: #0e1015; padding: 18px 20px; border-left: 1px solid rgba(240,242,245,0.08); }
        .rail-label { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--blood-red); letter-spacing: 0.08em; font-weight: 700; }

        #feed { display: flex; flex-direction: column; }

        .commentary-waiting { padding: 24px 0; }
        .commentary-waiting-text { font-family: 'Inter', sans-serif; font-size: 12px; color: rgba(240,242,245,0.35); line-height: 1.5; }

        .feed-row { padding: 10px 12px; margin-bottom: 8px; border-left: 2px solid rgba(240,242,245,0.08); border-radius: 0 4px 4px 0; }
        .feed-row-head { display: flex; align-items: baseline; gap: 5px; margin-bottom: 2px; }
        .feed-over-tag { font-family: 'JetBrains Mono', monospace; color: var(--bail-amber); font-size: 9px; font-weight: 700; }
        .feed-event-tag { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 9px; letter-spacing: 0.04em; }
        .feed-text { font-size: 11px; color: var(--crease-white); line-height: 1.4; margin-top: 4px; }
        .loading-state { color: rgba(240,242,245,0.4); font-size: 11px; padding: 40px 0; text-align: center; width: 100%; }

        @media (max-width: 768px) {
          .mp-body, .mp-body-no-rail:not(.mp-body-single) { grid-template-columns: 1fr; }
          .innings-col.border-left, .mp-commentary-rail { border-left: none; border-top: 1px solid rgba(240,242,245,0.08); }
          .scoreboard-grid { gap: 10px; }
          .sb-team-score { font-size: 24px; }
        }
      `}</style>
    </div>
  );
}

// Dynamic Commentary Styling Engine
const styleFor = {
  wicket: { bg: 'rgba(232,0,58,0.12)',  border: '#E8003A', label: '#E8003A', labelText: 'WICKET', size: '11px', weight: '700' },
  six:    { bg: 'rgba(245,166,35,0.12)', border: '#F5A623', label: '#F5A623', labelText: 'SIX',    size: '11px', weight: '700' },
  four:   { bg: 'rgba(245,166,35,0.08)', border: '#F5A623', label: '#F5A623', labelText: 'FOUR',   size: '11px', weight: '500' },
  run:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.4)', labelText: '', size: '11px', weight: '400' },
  dot:    { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.3)', labelText: '', size: '11px', weight: '400' }
};

// Renders one innings' batting + bowling tables, capped to the top
// performers so the panel sizes to its content instead of needing a
// visible internal scrollbar. `accent` picks amber (1st innings, target)
// or red (2nd innings, chase) to match the rest of the DeathOvers palette.
function InningsPanel({ innings, accent, label }) {
  const batters = innings.batters || [];
  const bowlers = innings.bowlers || [];
  const visibleBatters = batters.slice(0, 5);
  const visibleBowlers = bowlers.slice(0, 4);

  return (
    <div className="innings-col border-left">
      <div className={`inn-heading accent-${accent}`}>
        {label}: {innings.team || 'TBD'} · {innings.score || '0/0'} ({innings.overs || '0.0'})
      </div>

      {visibleBatters.length > 0 && (
        <>
          <div className="stat-kicker">BATTING</div>
          <table className="stat-table">
            <thead><tr><th>BATTER</th><th>R</th><th>B</th><th>SR</th></tr></thead>
            <tbody>
              {visibleBatters.map((b, i) => (
                <tr key={i} className={b.dim ? 'dim' : ''}>
                  <td>{b.name}</td><td>{b.r}</td><td>{b.b}</td><td>{b.sr}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {batters.length > visibleBatters.length && (
            <div className="stat-more">+{batters.length - visibleBatters.length} more</div>
          )}
        </>
      )}

      {visibleBowlers.length > 0 && (
        <>
          <div className="stat-kicker" style={{ marginTop: '16px' }}>BOWLING</div>
          <table className="stat-table">
            <thead><tr><th>BOWLER</th><th>O</th><th>R</th><th>W</th><th>ECO</th></tr></thead>
            <tbody>
              {visibleBowlers.map((bw, i) => (
                <tr key={i}>
                  <td>{bw.name}</td><td>{bw.o}</td><td>{bw.r}</td>
                  <td style={bw.w && bw.w !== '0' ? { color: 'var(--blood-red)', fontWeight: 'bold' } : undefined}>{bw.w}</td>
                  <td>{bw.eco}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {bowlers.length > visibleBowlers.length && (
            <div className="stat-more">+{bowlers.length - visibleBowlers.length} more</div>
          )}
        </>
      )}
    </div>
  );
}
