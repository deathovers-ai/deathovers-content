import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = 'https://deathovers-ai-engine.onrender.com/api';

const insightType = {
  venue_pregame_summary: { label: 'VENUE BRIEF', accent: 'blue' },
  venue_score_comparison: { label: 'SCORING PACE', accent: 'amber' },
  venue_phase_comparison: { label: 'PHASE READ', accent: 'violet' },
  player_form_comparison: { label: 'BATTER FORM', accent: 'red' },
};

const matchName = (match) => match?.teams?.filter(Boolean).join(' v ') || match?.matchName || 'Live match';

function insightCopy(insight) {
  if (insight.text) return insight.text;
  const pointers = (insight.pointers || [])
    .map((pointer) => `${pointer.label}: ${pointer.value}${pointer.unit || ''}`)
    .join(' · ');
  return [insight.headline, pointers].filter(Boolean).join(' — ');
}

function ChaseBrief({ chase, matchId }) {
  const state = chase?.state;
  if (!state) return null;

  const qualified = chase.status === 'qualified';
  const ahead = qualified && (chase.cohort?.pace_gap_runs || 0) >= 0;
  const recovery = qualified ? `${Math.round(chase.cohort.recovery_rate * 100)}%` : 'WAITING';
  const label = qualified
    ? (ahead ? 'AHEAD OF HISTORICAL PACE' : 'BEHIND HISTORICAL PACE')
    : 'HISTORICAL READ PENDING';

  return (
    <aside className={`tactical-chase-brief ${qualified ? (ahead ? 'is-ahead' : 'is-behind') : ''}`}>
      <div>
        <span className="tactical-chase-kicker"><i /> CHASE ENGINE</span>
        <strong>{label}</strong>
        <p>{state.runs}/{state.wickets} · need {state.runs_required} from {state.legal_balls_remaining} balls · RRR {state.required_run_rate.toFixed(2)}</p>
      </div>
      <div className="tactical-recovery"><b>{recovery}</b><span>RECOVERY</span></div>
      <a href={`/match-room/?id=${matchId}`}>OPEN MATCH ROOM -&gt;</a>
    </aside>
  );
}

export default function TacticalSheetLive() {
  const [matches, setMatches] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadingMatches, setLoadingMatches] = useState(true);
  const [loadingSheet, setLoadingSheet] = useState(false);
  const [error, setError] = useState(null);

  const liveMatches = useMemo(
    () => matches.filter((match) => match.status === 'LIVE'),
    [matches],
  );
  const selectedMatch = liveMatches.find((match) => match.id === selectedId) || null;
  const insights = detail?.intelligence?.insights || [];

  useEffect(() => {
    let cancelled = false;
    const loadMatches = async () => {
      try {
        const response = await fetch(`${API_BASE}/live-scores`);
        if (!response.ok) throw new Error('Live match feed unavailable');
        const payload = await response.json();
        if (cancelled) return;
        const nextMatches = payload.liveAndRecent || [];
        const nextLive = nextMatches.filter((match) => match.status === 'LIVE');
        setMatches(nextMatches);
        setSelectedId((current) => nextLive.some((match) => match.id === current) ? current : (nextLive[0]?.id || null));
        setError(null);
      } catch (err) {
        if (!cancelled) setError('Live match data is temporarily unavailable.');
      } finally {
        if (!cancelled) setLoadingMatches(false);
      }
    };

    loadMatches();
    const interval = window.setInterval(loadMatches, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }

    let cancelled = false;
    const loadSheet = async () => {
      setLoadingSheet(true);
      try {
        const response = await fetch(`${API_BASE}/match-details/${selectedId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Tactical data unavailable');
        if (!cancelled) {
          setDetail(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError('This match is live, but its tactical feed is not ready yet.');
      } finally {
        if (!cancelled) setLoadingSheet(false);
      }
    };

    loadSheet();
    const interval = window.setInterval(loadSheet, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [selectedId]);

  return (
    <section className="tactical-live" aria-label="Live tactical sheets">
      <header className="tactical-live-header">
        <div>
          <div className="tactical-live-kicker"><span className="tactical-live-dot" /> LIVE MATCH INTELLIGENCE</div>
          <h2>TACTICAL SHEETS</h2>
          <p>Venue context, scoring pace and player form — refreshed as each live match develops.</p>
        </div>
        <div className="tactical-live-count">{liveMatches.length} LIVE</div>
      </header>

      {loadingMatches ? (
        <div className="tactical-loading">LOADING LIVE FIXTURES…</div>
      ) : liveMatches.length === 0 ? (
        <div className="tactical-empty"><strong>NO LIVE MATCHES</strong><span>New Tactical Sheets appear automatically when play begins.</span></div>
      ) : (
        <>
          <div className="tactical-match-rail" role="tablist" aria-label="Live matches">
            {liveMatches.map((match) => {
              const selected = match.id === selectedId;
              return (
                <button
                  className={`tactical-match-tab ${selected ? 'is-selected' : ''}`}
                  key={match.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setSelectedId(match.id)}
                >
                  <span className="tactical-match-state"><span /> LIVE</span>
                  <strong>{matchName(match)}</strong>
                  <small>{match.venue || 'Match centre'}</small>
                </button>
              );
            })}
          </div>

          <div className="tactical-sheet" role="tabpanel">
            <div className="tactical-sheet-topline">
              <div>
                <span className="tactical-sheet-label">ACTIVE TACTICAL SHEET</span>
                <h3>{matchName(selectedMatch)}</h3>
              </div>
              <span className="tactical-sheet-status">{loadingSheet ? 'REFRESHING' : 'LIVE DATA'}</span>
            </div>

            {error ? <div className="tactical-error">{error}</div> : null}

            {!error ? <ChaseBrief chase={detail?.chase} matchId={selectedId} /> : null}

            {!error && insights.length === 0 ? (
              <div className="tactical-empty-sheet">
                <span>//</span>
                <div><strong>AWAITING A QUALIFIED SIGNAL</strong><p>The model will publish an insight once there is enough reliable match context.</p></div>
              </div>
            ) : null}

            {insights.length > 0 ? (
              <ol className="tactical-insight-log">
                {insights.map((insight, index) => {
                  const meta = insightType[insight.type] || { label: 'MATCH READ', accent: 'blue' };
                  return (
                    <li className="tactical-insight" key={`${insight.type || 'insight'}-${index}`}>
                      <span className={`tactical-insight-number ${meta.accent}`}>{String(index + 1).padStart(2, '0')}</span>
                      <div>
                        <div className="tactical-insight-meta">
                          <span className={meta.accent}>{meta.label}</span>
                          {insight.sample_size ? <em>HISTORICAL SAMPLE: {insight.sample_size}</em> : null}
                        </div>
                        <p>{insightCopy(insight)}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            ) : null}
          </div>
        </>
      )}

      <style>{`
        .tactical-live { margin: 24px 0 48px; border: 1px solid rgba(91,151,230,.24); border-radius: 8px; overflow: hidden; background: #0d0f14; animation:tacticalRise .45s cubic-bezier(.16,1,.3,1) both; }
        .tactical-live-header { display:flex; justify-content:space-between; gap:24px; padding:24px; background:linear-gradient(110deg,rgba(35,75,128,.32),rgba(13,15,20,0) 65%); border-bottom:1px solid rgba(91,151,230,.18); }
        .tactical-live-kicker,.tactical-sheet-label,.tactical-match-state,.tactical-insight-meta { font:700 10px 'JetBrains Mono',monospace; letter-spacing:.1em; }
        .tactical-live-kicker { display:flex; align-items:center; gap:7px; color:#86b9ff; }
        .tactical-live-dot,.tactical-match-state span { width:7px; height:7px; border-radius:50%; background:#5ca8ff; box-shadow:0 0 12px #5ca8ff; animation:tacticalPulse 1.4s infinite; }
        .tactical-live h2 { margin:7px 0 4px; color:#fff; font-size:28px; letter-spacing:.04em; }
        .tactical-live-header p { margin:0; max-width:580px; color:rgba(240,242,245,.58); font-size:13px; line-height:1.55; }
        .tactical-live-count,.tactical-sheet-status { align-self:flex-start; padding:6px 8px; border:1px solid rgba(110,180,255,.3); border-radius:3px; color:#9bc7ff; background:rgba(63,129,209,.12); font:700 10px 'JetBrains Mono',monospace; letter-spacing:.08em; white-space:nowrap; }
        .tactical-match-rail { display:flex; gap:10px; overflow-x:auto; padding:14px; border-bottom:1px solid rgba(240,242,245,.07); background:#10131a; }
        .tactical-match-tab { min-width:210px; flex:1; padding:13px; text-align:left; border:1px solid rgba(240,242,245,.12); border-radius:5px; background:#131722; color:#fff; cursor:pointer; transition:.18s ease; }
        .tactical-match-tab:hover { border-color:rgba(105,170,255,.55); transform:translateY(-1px); }
        .tactical-match-tab.is-selected { border-color:#65aaff; background:linear-gradient(135deg,rgba(57,112,191,.28),#131722); box-shadow:inset 3px 0 #65aaff; }
        .tactical-match-state { display:flex; align-items:center; gap:6px; color:#7eb7ff; font-size:9px; }
        .tactical-match-tab strong { display:block; margin:8px 0 4px; font-size:13px; line-height:1.3; }
        .tactical-match-tab small { color:rgba(240,242,245,.44); font:10px 'JetBrains Mono',monospace; }
        .tactical-sheet { padding:20px 24px 6px; }
        .tactical-sheet-topline { display:flex; justify-content:space-between; gap:16px; padding-bottom:17px; border-bottom:1px solid rgba(240,242,245,.08); }
        .tactical-sheet-label { color:#6faeff; }
        .tactical-sheet h3 { margin:6px 0 0; color:#fff; font-size:19px; }
        .tactical-chase-brief { display:grid; grid-template-columns:1fr auto; gap:12px 22px; align-items:center; margin:16px 0 2px; padding:14px 15px; border:1px solid rgba(245,166,35,.25); border-left:3px solid #f5a623; border-radius:5px; background:linear-gradient(105deg,rgba(245,166,35,.09),rgba(245,166,35,.025)); }
        .tactical-chase-brief.is-behind { border-color:rgba(232,0,58,.3); border-left-color:#e8003a; background:linear-gradient(105deg,rgba(232,0,58,.1),rgba(232,0,58,.02)); }
        .tactical-chase-kicker { display:block; color:#f5a623; font:700 9px 'JetBrains Mono',monospace; letter-spacing:.09em; }
        .tactical-chase-kicker i { display:inline-block; width:6px; height:6px; margin-right:5px; border-radius:50%; background:#66da9a; animation:tacticalPulse 1.4s infinite; }
        .tactical-chase-brief.is-behind .tactical-chase-kicker { color:#ff8ca6; }
        .tactical-chase-brief strong { display:block; margin-top:5px; color:#fff; font:22px/1 'Bebas Neue',sans-serif; letter-spacing:.03em; }
        .tactical-chase-brief.is-ahead strong { color:#79dfa4; } .tactical-chase-brief.is-behind strong { color:#ff8ca6; }
        .tactical-chase-brief p { margin:6px 0 0; color:rgba(240,242,245,.58); font:11px/1.4 'JetBrains Mono',monospace; }
        .tactical-recovery { min-width:63px; display:grid; place-content:center; width:63px; height:63px; text-align:center; border:1px solid rgba(245,166,35,.4); border-radius:50%; background:rgba(0,0,0,.13); }
        .tactical-chase-brief.is-behind .tactical-recovery { border-color:rgba(232,0,58,.45); }
        .tactical-recovery b { color:#fff; font:700 16px 'JetBrains Mono',monospace; letter-spacing:-.06em; } .tactical-recovery span { margin-top:3px; color:rgba(240,242,245,.42); font:700 7px 'JetBrains Mono',monospace; letter-spacing:.08em; }
        .tactical-chase-brief a { grid-column:1 / -1; padding-top:10px; border-top:1px solid rgba(240,242,245,.08); color:rgba(240,242,245,.62); font:700 9px 'JetBrains Mono',monospace; letter-spacing:.08em; text-decoration:none; transition:color .18s ease; }
        .tactical-chase-brief a:hover { color:#f5a623; }
        .tactical-insight-log { list-style:none; margin:0; padding:0; }
        .tactical-insight { display:grid; grid-template-columns:38px 1fr; gap:13px; padding:18px 0; border-bottom:1px solid rgba(240,242,245,.07); }
        .tactical-insight-number { display:flex; width:30px; height:30px; align-items:center; justify-content:center; border:1px solid rgba(111,174,255,.32); border-radius:3px; color:#94c2ff; background:rgba(63,129,209,.12); font:700 10px 'JetBrains Mono',monospace; }
        .tactical-insight-meta { display:flex; gap:10px; align-items:center; color:#93c2ff; }
        .tactical-insight-meta .amber,.tactical-insight-number.amber { color:#f5a623; border-color:rgba(245,166,35,.33); }
        .tactical-insight-meta .violet,.tactical-insight-number.violet { color:#c595ff; border-color:rgba(197,149,255,.33); }
        .tactical-insight-meta .red,.tactical-insight-number.red { color:#ff668c; border-color:rgba(255,102,140,.33); }
        .tactical-insight-meta em { color:rgba(240,242,245,.36); font-style:normal; font-size:9px; }
        .tactical-insight p { margin:7px 0 0; color:rgba(240,242,245,.76); font-size:13px; line-height:1.6; }
        .tactical-empty,.tactical-loading,.tactical-empty-sheet,.tactical-error { padding:34px 24px; color:rgba(240,242,245,.48); font:11px 'JetBrains Mono',monospace; }
        .tactical-empty { display:grid; gap:8px; text-align:center; }
        .tactical-empty strong { color:#fff; letter-spacing:.08em; }
        .tactical-empty-sheet { display:flex; gap:13px; align-items:center; min-height:94px; }
        .tactical-empty-sheet > span { color:#78b4ff; font-size:20px; }
        .tactical-empty-sheet strong { color:#d7e8ff; font-size:10px; letter-spacing:.08em; }
        .tactical-empty-sheet p { margin:5px 0 0; color:rgba(240,242,245,.38); font:12px/1.5 Inter,sans-serif; }
        .tactical-error { margin-top:18px; border-left:3px solid #e8003a; background:rgba(232,0,58,.08); color:#ff9ab4; }
        @keyframes tacticalPulse { 50% { opacity:.35; } }
        @keyframes tacticalRise { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        @media(max-width:640px) { .tactical-live-header,.tactical-sheet-topline { padding:18px; } .tactical-live-header { gap:12px; } .tactical-live-header p { display:none; } .tactical-sheet { padding:16px; } .tactical-live h2 { font-size:23px; } .tactical-match-tab { min-width:180px; } .tactical-chase-brief { grid-template-columns:1fr auto; gap:10px; } }
        @media(prefers-reduced-motion:reduce) { .tactical-live,.tactical-live-dot,.tactical-match-state span,.tactical-chase-kicker i { animation:none; } .tactical-match-tab { transition:none; } }
      `}</style>
    </section>
  );
}
