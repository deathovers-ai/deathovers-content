import React, { useState, useEffect, useRef } from 'react';

export default function LiveCarousel() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);

  // State for Full-Page Takeover
  const [activeMatchId, setActiveMatchId] = useState(null);
  const [matchDetails, setMatchDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null); // NEW: surfaces quota-exhausted / fetch errors

  // Reference for manual scrolling
  const scrollRef = useRef(null);

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
    setDetailError(null);

    try {
      const res = await fetch(`https://deathovers-ai-engine.onrender.com/api/match-details/${matchId}`);
      const data = await res.json();
      if (!res.ok) {
        // NEW: backend now returns a structured error (e.g. quotaExhausted) instead
        // of just failing silently — surface it instead of showing a blank page.
        setDetailError(data.error || "Could not load match details.");
      } else {
        setMatchDetails(prev => ({ ...prev, [matchId]: data }));
      }
    } catch (err) {
      console.error("Failed to load match drilldown data:", err);
      setDetailError("Could not reach the live-data server. Please try again shortly.");
    } finally {
      setDetailLoading(false);
    }
    window.scrollTo(0, 0);
  };

  const closeMatch = () => {
    setActiveMatchId(null);
    setDetailError(null);
  };

  const scrollByCard = (direction) => {
    if (!scrollRef.current) return;
    const cardWidth = 288; // 272px card + 16px gap
    scrollRef.current.scrollBy({ left: direction * cardWidth, behavior: 'smooth' });
  };

  let displayMatches = [];
  if (matches.length > 0) {
    // 1. Matches that are LIVE and have an active score block (In-Play)
    const liveInPlay = matches.filter(m => m.status === 'LIVE' && (m.score?.home || m.score?.away));
    // 2. Matches that are LIVE but haven't started playing yet (Toss done, no score)
    const liveNotInPlay = matches.filter(m => m.status === 'LIVE' && !m.score?.home && !m.score?.away);
    // 3. Upcoming matches
    const upcoming = matches.filter(m => m.status === 'UPCOMING');
    // 4. Completed matches
    const completed = matches.filter(m => m.status === 'COMPLETED').slice(0, 3);

    displayMatches = [...liveInPlay, ...liveNotInPlay, ...upcoming, ...completed];
  } else {
    displayMatches = [{
      id: "mock-channel", venue: "IPL 2026 . Q2", status: "LIVE", matchName: "GT vs KKR",
      score: { home: { score: "181/5", info: "20.0" }, away: { score: "156/6", info: "17.2" } },
      chaseNote: "need 26 off 16"
    }];
  }

  if (loading) {
    return <div className="loading-state font-mono">ESTABLISHING SECURE UPLINK TO DATA CLUSTER...</div>;
  }

  const activeData = activeMatchId ? (matchDetails[activeMatchId] || null) : null;
  const activeMatchMeta = displayMatches.find(m => m.id === activeMatchId);

  const inn1 = activeData?.innings1 || null;
  const inn2 = activeData?.innings2 || null;
  const hasCommentary = (activeData?.commentary?.length || 0) > 0;
  const ballTracker = activeData?.ballTracker || [];

  const liveScore = activeData?.liveScore || null;
  const displayHomeScore = liveScore?.home || activeMatchMeta?.score?.home;
  const displayAwayScore = liveScore?.away || activeMatchMeta?.score?.away;

  const safeTeamName = (raw, fallback) => {
    if (!raw) return fallback;
    if (raw.includes(',') || raw.length > 24) return fallback;
    return raw;
  };

  const crestUrl = (imageId) =>
    imageId ? `https://static.cricbuzz.com/a/img/v1/50x50/i1/c${imageId}/x.jpg` : null;

  const TeamCrest = ({ imageId, code }) => {
    const [failed, setFailed] = useState(false);
    const src = crestUrl(imageId);
    if (!src || failed) {
      return <span className="team-crest team-crest-fallback">{(code || '?').slice(0, 2)}</span>;
    }
    return (
      <img
        className="team-crest"
        src={src}
        alt={code || ''}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  };

  return (
    <div className="live-engine-wrapper">

      {/* ================= VIEW 1: CAROUSEL ================= */}
      {!activeMatchId && (
        <div className="carousel-wrap">
          <div className="carousel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 24px', marginBottom: '10px' }}>
            <div className="section-label" style={{ margin: 0, padding: 0 }}>LIVE NOW</div>
            <div className="carousel-controls" style={{ display: 'flex', gap: '8px' }}>
              <button onClick={() => scrollByCard(-1)} className="carousel-btn">‹</button>
              <button onClick={() => scrollByCard(1)} className="carousel-btn">›</button>
            </div>
          </div>

          <div
            className="carousel-track"
            ref={scrollRef}
            style={{ scrollSnapType: 'x mandatory', scrollBehavior: 'smooth' }}
          >
            {displayMatches.map((match) => {
              const isLive = match.status === 'LIVE';
              const awayIsPending = !match.score?.away || match.score.away.score === 'yet to bat';
              {/* FIX: use the clean teams[] array from the backend instead of splitting
                  matchName on " vs " — matchName often has a trailing ", 3rd Match" etc.
                  clause on the away side, which safeTeamName was rejecting (comma check)
                  and silently falling back to the literal word "AWAY". */}
              const homeTeam = safeTeamName(match.teams?.[0] || match.matchName?.split(' vs ')[0], "HOME");
              const awayTeam = safeTeamName(match.teams?.[1] || match.matchName?.split(' vs ')[1], "AWAY");
              return (
                <div
                  key={match.id}
                  className={`match-card ${isLive ? 'is-live' : ''}`}
                  onClick={() => openMatch(match.id)}
                  style={{ scrollSnapAlign: 'start' }}
                >
                  <div className="match-card-head">
                    <span className="series-tag">{match.venue || "INTERNATIONAL"}</span>
                    <div className="tag-cluster">
                      {match.matchFormat && match.matchFormat !== 'UNKNOWN' && (
                        <span className={`format-badge format-${match.matchFormat.toLowerCase()}`}>
                          {match.matchFormat}
                        </span>
                      )}
                      <span className={`status-tag ${isLive ? 'status-live' : 'status-done'}`}>
                        {isLive && <span className="live-dot"></span>}
                        {match.status}
                      </span>
                    </div>
                  </div>

                  <div className="team-line">
                    <span className="team-code">
                      <TeamCrest imageId={match.homeImageId} code={homeTeam} />
                      {homeTeam}
                    </span>
                    <span className="team-score">
                      {match.score?.home?.score || '-'}
                      <span className="overs-sub"> ({match.score?.home?.info || ''})</span>
                    </span>
                  </div>

                  {!awayIsPending && (
                    <div className="team-line">
                      <span className="team-code">
                        <TeamCrest imageId={match.awayImageId} code={awayTeam} />
                        {awayTeam}
                      </span>
                      <span className="team-score">
                        {match.score.away.score}<span className="overs-sub"> ({match.score.away.info || ''})</span>
                      </span>
                    </div>
                  )}

                  <div className="chase-line">{match.chaseNote || "IN PROGRESS"}</div>
                  <div className="tap-hint">TAP FOR FULL SCORECARD &#9662;</div>
                </div>
              );
            })}

            <div className="peek-card" style={{ scrollSnapAlign: 'start' }}>
              <div className="peek-label">NEXT &#9656;</div>
              <div className="peek-teams">ESSEX W v SOM W</div>
            </div>

          </div>
        </div>
      )}

      {/* ================= VIEW 2: FULL WIDTH MATCH PAGE ================= */}
      {activeMatchId && activeMatchMeta && (
        <div className="matchpage">
          <button className="back-btn" onClick={closeMatch}>&larr; BACK TO LIVE MATCHES</button>

          {detailError ? (
            <div className="mp-header mp-header-loading">
              <div className="loading-state font-mono error-state">
                {detailError}
              </div>
            </div>
          ) : detailLoading || !activeData ? (
            <div className="mp-header mp-header-loading">
              <div className="loading-state font-mono">PULLING LIVE TELEMETRY...</div>
            </div>
          ) : (
            <>
              {/* GLANCE SCOREBOARD */}
              <div className="scoreboard">
                <div className="scoreboard-top">
                  <span className="series-tag">{activeMatchMeta.venue}</span>
                  <div className="tag-cluster">
                    {activeMatchMeta.matchFormat && activeMatchMeta.matchFormat !== 'UNKNOWN' && (
                      <span className={`format-badge format-${activeMatchMeta.matchFormat.toLowerCase()}`}>
                        {activeMatchMeta.matchFormat}
                      </span>
                    )}
                    <span className={`status-tag ${activeMatchMeta.status === 'LIVE' ? 'status-live' : 'status-done'}`}>
                      {activeMatchMeta.status === 'LIVE' && <span className="live-dot"></span>}
                      {activeMatchMeta.status}
                    </span>
                  </div>
                </div>

                <div className="scoreboard-grid">
                  <div className={`scoreboard-team ${!inn2 ? 'scoreboard-team-batting' : ''}`}>
                    <div className="sb-team-name">
                      {inn1?.team || safeTeamName(activeMatchMeta.teams?.[0] || activeMatchMeta.matchName?.split(' vs ')[0], "TEAM 1")}
                    </div>
                    <div className="sb-team-score">
                      {displayHomeScore?.score || '0/0'}
                      <span className="sb-overs">({displayHomeScore?.info || '0.0'})</span>
                    </div>
                  </div>

                  <div className="scoreboard-divider">
                    <span>VS</span>
                  </div>

                  <div className={`scoreboard-team scoreboard-team-right ${inn2 ? 'scoreboard-team-batting' : 'scoreboard-team-waiting'}`}>
                    <div className="sb-team-name">
                      {inn2?.team || safeTeamName(activeMatchMeta.teams?.[1] || activeMatchMeta.matchName?.split(' vs ')[1], "TEAM 2")}
                    </div>
                    <div className="sb-team-score">
                      {inn2 ? (
                        <>{displayAwayScore?.score}<span className="sb-overs">({displayAwayScore?.info || '0.0'})</span></>
                      ) : (
                        <span className="sb-pending">YET TO BAT</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* ENDPOINTS: TARGET, CRR, RRR */}
                {liveScore && (
                  <div className="scoreboard-stats" style={{
                    display: 'flex',
                    justifyContent: 'center',
                    gap: '20px',
                    marginTop: '16px',
                    paddingTop: '12px',
                    borderTop: '1px solid rgba(240,242,245,0.06)',
                    fontFamily: 'JetBrains Mono, monospace',
                    fontSize: '11px',
                    color: 'rgba(240,242,245,0.6)'
                  }}>
                    {liveScore.target > 0 && (
                      <span>TARGET: <strong style={{ color: 'var(--crease-white)' }}>{liveScore.target}</strong></span>
                    )}
                    {liveScore.crr > 0 && (
                      <span>CRR: <strong style={{ color: 'var(--crease-white)' }}>{liveScore.crr}</strong></span>
                    )}
                    {liveScore.rrr > 0 && (
                      <span>RRR: <strong style={{ color: 'var(--crease-white)' }}>{liveScore.rrr}</strong></span>
                    )}
                  </div>
                )}

                {/* MATCH STATUS / RESULT OVERRIDE */}
                {(liveScore?.customStatus || activeMatchMeta.chaseNote) && (
                  <div className="scoreboard-note" style={{ textAlign: 'center', fontSize: '13px' }}>
                    {liveScore?.customStatus || activeMatchMeta.chaseNote}
                  </div>
                )}

                {/* BALL TRACKER -- current-over strip */}
                {ballTracker.length > 0 && (
                  <div className="ball-tracker">
                    <span className="ball-tracker-label">THIS OVER</span>
                    <div className="ball-tracker-dots">
                      {ballTracker.map((b, i) => (
                        <span key={i} className={`ball-pill ball-pill-${b.type}`}>{b.label}</span>
                      ))}
                    </div>
                  </div>
                )}

                {liveScore?.lastWicket && (
                  <div className="scoreboard-lastwkt">
                    <span className="toss-kicker">LAST WKT</span>
                    <span className="toss-line">{liveScore.lastWicket}</span>
                  </div>
                )}

                {activeData.toss && (
                  <div className="scoreboard-toss">
                    <span className="toss-kicker">TOSS</span>
                    <span className="toss-line">{activeData.toss}</span>
                  </div>
                )}
              </div>

              {/* INNINGS DETAIL + LIVE COMMENTARY */}
              <div
                className="mp-body"
                style={{
                  gridTemplateColumns:
                    inn1 && inn2 ? '1fr 1fr 1.1fr' :
                      (inn1 || inn2) ? '1fr 1.4fr' :
                        '1fr'
                }}
              >
                {inn1 && <InningsPanel innings={inn1} accent="amber" label="1ST INNINGS" />}
                {inn2 && <InningsPanel innings={inn2} accent="red" label="2ND INNINGS" />}

                {/* COMMENTARY PANE (Now vertically scrollable) */}
                <div className="mp-commentary-rail">
                  <div className="rail-label"><span className="live-dot"></span>LIVE COMMENTARY</div>
                  {hasCommentary ? (
                    <div id="feed">
                      {activeData.commentary.map((c, i) => {
                        const s = styleFor[c.type] || styleFor.dot;
                        return (
                          <div key={i} className="feed-row ball-new" style={{ background: s.bg, borderLeftColor: s.border }}>
                            <div className="feed-row-head">
                              {c.over && <span className="feed-over-tag">{c.over}</span>}
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
        @keyframes cardRise { from { opacity: 0; transform: translateY(10px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }

        .live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blood-red); animation: livePulse 1.2s ease-in-out infinite; display: inline-block; }
        .ball-new { animation: ballIn 0.4s ease-out; }

        /* CAROUSEL CONTROLS */
        .carousel-btn {
            background: rgba(240,242,245,0.08);
            border: 1px solid rgba(240,242,245,0.15);
            color: rgba(240,242,245,0.7);
            border-radius: 4px;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.2s ease;
        }
        .carousel-btn:hover {
            background: rgba(232,0,58,0.2);
            border-color: var(--blood-red);
            color: var(--crease-white);
        }

        /* CAROUSEL STYLES */
        .section-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(240,242,245,0.4); letter-spacing: 0.05em; }
        .carousel-wrap { padding: 20px 0; }

        .carousel-track {
          display: flex; gap: 12px; overflow-x: auto; padding: 0 24px 12px; min-height: 152px;
          scrollbar-width: none; -ms-overflow-style: none;
        }
        .carousel-track::-webkit-scrollbar { display: none; }

        .team-crest {
          width: 18px; height: 18px; border-radius: 3px; object-fit: cover;
          margin-right: 7px; vertical-align: -4px; flex-shrink: 0;
          background: rgba(240,242,245,0.06);
        }
        .team-crest-fallback {
          display: inline-flex; align-items: center; justify-content: center;
          width: 18px; height: 18px; border-radius: 3px; margin-right: 7px;
          vertical-align: -4px; background: rgba(240,242,245,0.08);
          font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700;
          color: rgba(240,242,245,0.5); flex-shrink: 0;
        }

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
          transition: border-color 0.22s ease, transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.22s ease;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          animation: cardRise 0.4s cubic-bezier(0.16, 1, 0.3, 1) backwards;
        }
        .match-card:nth-child(1) { animation-delay: 0.02s; }
        .match-card:nth-child(2) { animation-delay: 0.06s; }
        .match-card:nth-child(3) { animation-delay: 0.1s; }
        .match-card:nth-child(4) { animation-delay: 0.14s; }

        .match-card:hover { border-color: rgba(232,0,58,0.5); transform: translateY(-4px) scale(1.015); box-shadow: 0 10px 24px rgba(0,0,0,0.4); }
        .match-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 6px 6px 0 0; background: rgba(240,242,245,0.12); }
        .match-card.is-live::before { background: var(--blood-red); }

        .match-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
        .tag-cluster { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .format-badge {
          font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 700;
          letter-spacing: 0.05em; padding: 2px 6px; border-radius: 3px;
          border: 1px solid rgba(240,242,245,0.15); color: rgba(240,242,245,0.55);
          background: rgba(240,242,245,0.04); line-height: 1.4;
        }

        .format-test { border-color: rgba(240,242,245,0.25); color: rgba(240,242,245,0.75); }
        .format-odi  { border-color: rgba(74,222,128,0.3); color: #4ADE80; }
        .format-t20  { border-color: rgba(232,0,58,0.3); color: var(--blood-red); }
        .format-t10  { border-color: rgba(232,0,58,0.3); color: var(--blood-red); }
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

        /* BALL TRACKER -- current-over strip */
        .ball-tracker { display: flex; align-items: center; gap: 10px; margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(240,242,245,0.06); }
        .ball-tracker-label { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); letter-spacing: 0.06em; flex-shrink: 0; }
        .ball-tracker-dots { display: flex; gap: 6px; flex-wrap: wrap; }
        .ball-pill {
          display: inline-flex; align-items: center; justify-content: center;
          min-width: 22px; height: 22px; padding: 0 5px; border-radius: 5px;
          font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
          background: rgba(240,242,245,0.06); color: rgba(240,242,245,0.55);
          animation: ballIn 0.3s ease-out backwards;
        }
        .ball-pill-wicket { background: var(--blood-red); color: #fff; }
        .ball-pill-six { background: var(--bail-amber); color: #1a1200; }
        .ball-pill-four { background: rgba(245,166,35,0.25); color: var(--bail-amber); }
        .ball-pill-dot { background: rgba(240,242,245,0.04); color: rgba(240,242,245,0.3); }

        .scoreboard-note { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: var(--bail-amber); margin-top: 14px; }

        .scoreboard-lastwkt, .scoreboard-toss { margin-top: 14px; padding-top: 14px; border-top: 1px solid rgba(240,242,245,0.06); display: flex; align-items: baseline; gap: 10px; }
        .toss-kicker { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(240,242,245,0.35); letter-spacing: 0.06em; flex-shrink: 0; }
        .toss-line { font-size: 12px; color: rgba(240,242,245,0.65); font-weight: 500; }

        .mp-header-loading { padding: 60px 24px; text-align: center; border-radius: 8px; }
        .error-state { color: var(--blood-red); }

        .mp-body { 
          background: var(--pitch-black); 
          border: 1px solid rgba(232,0,58,0.2); 
          border-top: none; 
          border-radius: 0 0 8px 8px; 
          overflow: hidden; 
          display: grid;
          align-items: start; /* PREVENTS COMM. PANE FROM STRETCHING TO MATCH SCORECARD HEIGHT */
        }

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
        .stat-more-btn {
          display: block; width: 100%; background: none; border: none; cursor: pointer;
          color: var(--bail-amber); opacity: 0.7; transition: opacity 0.15s;
        }
        .stat-more-btn:hover { opacity: 1; }

        /* Dismissal line under batter name */
        .batter-name-cell { display: flex; flex-direction: column; gap: 1px; }
        .batter-dismissal { font-family: 'Inter', sans-serif; font-size: 9px; font-weight: 400; color: rgba(240,242,245,0.35); line-height: 1.3; }

        /* SCROLLABLE COMMENTARY RAIL CSS */
        .mp-commentary-rail { 
          background: #0e1015; 
          padding: 18px 20px; 
          border-left: 1px solid rgba(240,242,245,0.08); 
          max-height: 650px; 
          overflow-y: auto; 
        }
        /* NATIVE CUSTOM SCROLLBAR FOR WEB-KIT */
        .mp-commentary-rail::-webkit-scrollbar { width: 4px; }
        .mp-commentary-rail::-webkit-scrollbar-track { background: transparent; }
        .mp-commentary-rail::-webkit-scrollbar-thumb { background: rgba(240,242,245,0.15); border-radius: 4px; }

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
          .mp-body { grid-template-columns: 1fr !important; }
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
  wicket: { bg: 'rgba(232,0,58,0.12)', border: '#E8003A', label: '#E8003A', labelText: 'WICKET', size: '11px', weight: '700' },
  six: { bg: 'rgba(245,166,35,0.12)', border: '#F5A623', label: '#F5A623', labelText: 'SIX', size: '11px', weight: '700' },
  four: { bg: 'rgba(245,166,35,0.08)', border: '#F5A623', label: '#F5A623', labelText: 'FOUR', size: '11px', weight: '500' },
  run: { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.4)', labelText: '', size: '11px', weight: '400' },
  dot: { bg: 'transparent', border: 'rgba(240,242,245,0.08)', label: 'rgba(240,242,245,0.3)', labelText: '', size: '11px', weight: '400' }
};

function InningsPanel({ innings, accent, label }) {
  const batters = innings.batters || [];
  const bowlers = innings.bowlers || [];
  const [battersExpanded, setBattersExpanded] = useState(false);
  const [bowlersExpanded, setBowlersExpanded] = useState(false);
  const visibleBatters = battersExpanded ? batters : batters.slice(0, 5);
  const visibleBowlers = bowlersExpanded ? bowlers : bowlers.slice(0, 4);

  return (
    <div className="innings-col border-left">
      <div className={`inn-heading accent-${accent}`}>
        {label}: {innings.team || 'TBD'} . {innings.score || '0/0'} ({innings.overs || '0.0'})
      </div>

      {visibleBatters.length > 0 && (
        <>
          <div className="stat-kicker">BATTING</div>
          <table className="stat-table">
            <thead><tr><th>BATTER</th><th>R</th><th>B</th><th>SR</th></tr></thead>
            <tbody>
              {visibleBatters.map((b, i) => (
                <tr key={i} className={b.dim ? 'dim' : ''}>
                  <td>
                    <div className="batter-name-cell">
                      <span>{b.name}</span>
                      {/* NEW: shows how the batter got out (e.g. "c Kohli b Bumrah"), or "not out" */}
                      {b.dismissal && <span className="batter-dismissal">{b.dismissal}</span>}
                    </div>
                  </td>
                  <td>{b.r}</td><td>{b.b}</td><td>{b.sr}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {batters.length > 5 && (
            <button
              type="button"
              className="stat-more stat-more-btn"
              onClick={() => setBattersExpanded(v => !v)}
            >
              {battersExpanded ? 'show less' : `+${batters.length - 5} more`}
            </button>
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
          {bowlers.length > 4 && (
            <button
              type="button"
              className="stat-more stat-more-btn"
              onClick={() => setBowlersExpanded(v => !v)}
            >
              {bowlersExpanded ? 'show less' : `+${bowlers.length - 4} more`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
