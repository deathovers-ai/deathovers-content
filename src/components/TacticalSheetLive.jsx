import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = 'https://deathovers-ai-engine.onrender.com/api';
const tabs = [
  { id: 'venue', label: 'VENUE RECORD' },
  { id: 'read', label: 'TACTICAL READ' },
  { id: 'innings', label: 'INNINGS ENGINE' },
];

const matchName = (match) => match?.teams?.filter(Boolean).join(' v ') || match?.matchName || 'Live match';
const value = (pointer) => `${pointer?.value ?? 'â€”'}${pointer?.unit || ''}${pointer?.pct == null ? '' : ` (${pointer.pct > 0 ? '+' : ''}${pointer.pct}%)`}`;
const score = (innings) => innings?.runs == null ? 'â€”' : `${innings.runs}/${innings.wickets ?? 'â€”'}`;
const overs = (innings) => innings?.overs != null ? `${innings.overs} overs` : innings?.balls != null ? `${Math.floor(innings.balls / 6)}.${innings.balls % 6} overs` : 'Overs not available';

export default function TacticalSheetLive() {
  const [matches, setMatches] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [activeTab, setActiveTab] = useState('venue');
  const [requestedId, setRequestedId] = useState(null);
  const [loadingMatches, setLoadingMatches] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setRequestedId(new URLSearchParams(window.location.search).get('id'));
  }, []);

  const liveMatches = useMemo(() => matches.filter((match) => match.status === 'LIVE'), [matches]);
  const selectedMatch = matches.find((match) => String(match.id) === String(selectedId));
  const insightData = detail?.intelligence?.insights || [];
  const venueBrief = insightData.find((insight) => insight.type === 'venue_pregame_summary');
  const tacticalInsights = insightData.filter((insight) => insight.type !== 'venue_pregame_summary');

  useEffect(() => {
    let cancelled = false;
    const loadMatches = async () => {
      try {
        const response = await fetch(`${API_BASE}/live-scores`);
        if (!response.ok) throw new Error('Live match feed unavailable');
        const payload = await response.json();
        if (cancelled) return;
        const next = payload.liveAndRecent || [];
        setMatches(next);
        setSelectedId((current) => {
          if (requestedId) return requestedId;
          if (next.some((match) => String(match.id) === String(current))) return current;
          return next.find((match) => match.status === 'LIVE')?.id || null;
        });
        setError(null);
      } catch (loadError) {
        if (!cancelled) setError('Live match data is unavailable.');
      } finally {
        if (!cancelled) setLoadingMatches(false);
      }
    };
    loadMatches();
    const timer = window.setInterval(loadMatches, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [requestedId]);

  useEffect(() => {
    if (!selectedId) return undefined;
    let cancelled = false;
    const loadDetail = async () => {
      setLoadingDetail(true);
      try {
        const response = await fetch(`${API_BASE}/match-details/${selectedId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Match data unavailable');
        if (!cancelled) { setDetail(payload); setError(null); }
      } catch (loadError) {
        if (!cancelled) setError('This match does not currently have a verified tactical data feed.');
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };
    loadDetail();
    const timer = window.setInterval(loadDetail, 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selectedId]);

  return (
    <section className="tactical-read" aria-label="Tactical Read">
      <header className="tactical-header">
        <div>
          <p className="tactical-kicker"><i /> LIVE INTELLIGENCE</p>
          <h1>TACTICAL READ</h1>
          <p>Venue evidence, live match interpretation and innings-specific analysis.</p>
        </div>
        <div className="tactical-status"><i /> {loadingDetail ? 'UPDATING' : 'LIVE DATA'}<small>60 second refresh</small></div>
      </header>

      {loadingMatches ? <StateCopy>Loading live fixtures.</StateCopy> : null}
      {!loadingMatches && liveMatches.length > 0 ? (
        <div className="match-rail" role="tablist" aria-label="Live matches">
          {liveMatches.map((match) => {
            const selected = String(match.id) === String(selectedId);
            return <button key={match.id} type="button" role="tab" aria-selected={selected} className={`match-tab ${selected ? 'selected' : ''}`} onClick={() => setSelectedId(match.id)}><span><i /> LIVE</span><strong>{matchName(match)}</strong><small>{match.venue || 'Venue unavailable'}</small></button>;
          })}
        </div>
      ) : null}
      {!loadingMatches && !selectedId ? <StateCopy>No live matches are available.</StateCopy> : null}

      {selectedId ? <>
        <section className="match-summary">
          <div><span>SELECTED MATCH</span><h2>{matchName(selectedMatch) || `${detail?.innings?.[0]?.team || 'Match'} v ${detail?.innings?.[1]?.team || 'Match'}`}</h2></div>
          <div className="summary-score"><span>LIVE SCORE</span><strong>{score(detail?.innings?.[detail?.innings?.length - 1])}</strong><small>{overs(detail?.innings?.[detail?.innings?.length - 1])}</small></div>
          <div className="summary-score"><span>INNINGS</span><strong>{detail?.innings?.length || 'â€”'}</strong><small>{detail?.innings?.[detail?.innings?.length - 1]?.phase || 'Match status unavailable'}</small></div>
        </section>

        <div className="intel-tabs" role="tablist" aria-label="Tactical Read sections">
          {tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? 'active' : ''} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
        </div>
        {error ? <StateCopy error>{error}</StateCopy> : null}
        {!error && activeTab === 'venue' ? <VenueRecord brief={venueBrief} weather={detail?.weather} toss={detail?.toss} dewRisk={detail?.dewRisk} /> : null}
        {!error && activeTab === 'read' ? <TacticalRead insights={tacticalInsights} /> : null}
        {!error && activeTab === 'innings' ? <InningsEngine detail={detail} insights={tacticalInsights} /> : null}
      </> : null}
      <style>{styles}</style>
    </section>
  );
}

function VenueRecord({ brief, toss, weather, dewRisk }) {
  const records = [
    ['Toss and decision', brief?.toss_record], ['Scoring record', brief?.score_record], ['Chase record', brief?.chase_record],
  ].filter(([, record]) => record);
  return <section className="tab-panel" role="tabpanel">
    <PanelHead title="Venue record" note={brief?.sample_size ? `${brief.sample_size} historical matches` : 'Historical ground evidence'} />
    <div className="conditions-grid">
      <Info label="Toss" value={toss?.winner ? `${toss.winner} chose to ${toss.decision || 'play'}` : 'Toss result unavailable'} />
      <Info label="Weather" value={weather?.condition ? `${weather.condition}${weather.temp_c == null ? '' : ` â€¢ ${Math.round(weather.temp_c)}Â°C`}` : 'Weather data unavailable'} />
      <Info label="Dew" value={dewRisk?.risk ? `${dewRisk.risk} risk` : 'No dew alert'} tone={dewRisk?.risk === 'HIGH' ? 'risk' : ''} />
    </div>
    {records.length ? <div className="records-grid">{records.map(([title, record]) => <Record key={title} title={title} record={record} />)}{brief?.score_range ? <Range range={brief.score_range} /> : null}</div> : <NoData>There is no verified historical record for this venue in the current dataset.</NoData>}
  </section>;
}

function TacticalRead({ insights }) {
  return <section className="tab-panel" role="tabpanel"><PanelHead title="Tactical read" note="Verified match signals" />
    {insights.length ? <div className="read-list">{insights.slice().reverse().map((insight, index) => <article className="read-item" key={`${insight.type}-${index}`}><span className="read-index">{String(index + 1).padStart(2, '0')}</span><div><div className="read-meta"><span>{(insight.type || 'match read').replaceAll('_', ' ')}</span>{insight.sample_size ? <small>{insight.sample_size} MATCH SAMPLE</small> : null}</div><h3>{insight.headline || 'Match signal'}</h3>{insight.pointers?.map((pointer, pointerIndex) => <div className="pointer" key={pointerIndex}><span>{pointer.label}</span><strong>{value(pointer)}</strong></div>)}</div></article>)}</div> : <NoData>No verified tactical signals have been generated for this match.</NoData>}
  </section>;
}

function InningsEngine({ detail, insights }) {
  const innings = detail?.innings || [];
  const first = innings[0];
  const second = innings[1];
  const chase = detail?.chase;
  const state = chase?.state;
  const qualified = chase?.status === 'qualified';
  const comparison = insights.filter((insight) => ['venue_score_comparison', 'venue_phase_comparison'].includes(insight.type));
  return <section className="tab-panel" role="tabpanel"><PanelHead title="Innings engine" note="First-innings par and second-innings chase analysis" />
    <div className="innings-grid">
      <article className="innings-card first"><div className="innings-label">FIRST INNINGS <span>HISTORICAL PAR</span></div><h3>{first?.team || 'First innings'}</h3><p className="innings-score">{score(first)}</p><p className="innings-detail">{overs(first)}{first?.phase ? ` â€¢ ${first.phase} phase` : ''}</p>{comparison.length ? <div className="comparison-list">{comparison.map((item, index) => <div key={index}><strong>{item.headline}</strong>{item.pointers?.slice(0, 2).map((pointer, pointerIndex) => <span key={pointerIndex}>{pointer.label}: {value(pointer)}</span>)}</div>)}</div> : <NoData>The historical first-innings comparison is not available for this match.</NoData>}</article>
      <article className={`innings-card second ${qualified ? 'qualified' : ''}`}><div className="innings-label">SECOND INNINGS <span>CHASE ENGINE</span></div><h3>{second?.team || 'Second innings'}</h3><p className="innings-score">{state ? `${state.runs}/${state.wickets}` : score(second)}</p><p className="innings-detail">{state ? `${state.runs_required} required from ${state.legal_balls_remaining} balls` : overs(second)}</p>{state ? <div className="chase-facts"><Fact label="Required rate" value={Number(state.required_run_rate).toFixed(2)} />{qualified ? <><Fact label="Pace gap" value={`${chase.cohort?.pace_gap_runs > 0 ? '+' : ''}${chase.cohort?.pace_gap_runs ?? 'â€”'} runs`} /><Fact label="Historical recovery" value={`${Math.round((chase.cohort?.recovery_rate || 0) * 100)}%`} /></> : <Fact label="Historical match" value="In progress" />}</div> : <NoData>The second-innings chase analysis begins when a target is set.</NoData>}</article>
    </div>
    {first && state ? <div className="innings-link"><span>FIRST-INNINGS CONTEXT</span><strong>{first.team}: {score(first)}</strong><small>Target {state.target} â€¢ retained only for this match analysis</small></div> : null}
  </section>;
}

function PanelHead({ title, note }) { return <div className="panel-head"><div><span>DEATH OVERS INTELLIGENCE</span><h2>{title}</h2></div><small>{note}</small></div>; }
function Info({ label, value, tone }) { return <div className={`info ${tone || ''}`}><span>{label}</span><strong>{value}</strong></div>; }
function Record({ title, record }) { return <article className="record"><div><h3>{title}</h3><small>{record.basis}</small></div>{record.pointers?.map((pointer, index) => <div className="pointer" key={index}><span>{pointer.label}</span><strong>{value(pointer)}</strong></div>)}</article>; }
function Range({ range }) { return <article className="record"><div><h3>Innings score range</h3><small>{range.basis}</small></div><p className="range"><strong>{range.low}</strong><i /><strong>{range.high}</strong></p></article>; }
function Fact({ label, value }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function NoData({ children }) { return <p className="no-data">{children}</p>; }
function StateCopy({ children, error = false }) { return <div className={`state-copy ${error ? 'error' : ''}`}>{children}</div>; }

const styles = `
  .tactical-read{margin:24px 0 52px;border:1px solid rgba(91,151,230,.25);border-radius:9px;overflow:hidden;background:#0d0f14;box-shadow:0 20px 55px rgba(0,0,0,.25)}
  .tactical-header{display:flex;justify-content:space-between;gap:24px;padding:27px 28px 23px;background:radial-gradient(circle at 85% 0%,rgba(57,112,191,.3),transparent 32%),linear-gradient(105deg,rgba(22,42,72,.66),#0d0f14 68%);border-bottom:1px solid rgba(91,151,230,.18)}.tactical-kicker,.panel-head>div>span{margin:0;color:#86b9ff;font:700 10px 'JetBrains Mono',monospace;letter-spacing:.11em}.tactical-kicker i,.tactical-status i,.match-tab span i{display:inline-block;width:7px;height:7px;margin-right:7px;border-radius:50%;background:#65aaff;box-shadow:0 0 10px rgba(101,170,255,.75)}.tactical-header h1{margin:7px 0 5px;color:#fff;font:34px/1 'Bebas Neue',sans-serif;letter-spacing:.04em}.tactical-header p:not(.tactical-kicker){max-width:590px;margin:0;color:rgba(240,242,245,.57);font-size:13px;line-height:1.5}.tactical-status{align-self:flex-start;display:grid;gap:4px;padding:7px 9px;border:1px solid rgba(101,170,255,.32);border-radius:4px;background:rgba(63,129,209,.11);color:#a6ccff;font:700 9px 'JetBrains Mono',monospace;letter-spacing:.08em;white-space:nowrap}.tactical-status i{width:5px;height:5px;margin:0 5px 0 0}.tactical-status small{color:rgba(240,242,245,.4);font:400 8px 'JetBrains Mono',monospace;letter-spacing:0}
  .match-rail{display:flex;gap:10px;overflow-x:auto;padding:14px;border-bottom:1px solid rgba(240,242,245,.07);background:#10131a}.match-tab{min-width:210px;flex:1;padding:13px;text-align:left;border:1px solid rgba(240,242,245,.11);border-radius:5px;background:#131722;color:#fff;cursor:pointer}.match-tab.selected{border-color:#65aaff;background:linear-gradient(135deg,rgba(57,112,191,.26),#131722);box-shadow:inset 3px 0 #65aaff}.match-tab span{display:block;color:#88bbff;font:700 9px 'JetBrains Mono',monospace;letter-spacing:.08em}.match-tab span i{width:5px;height:5px;margin-right:5px}.match-tab strong{display:block;margin:8px 0 4px;font-size:13px}.match-tab small{color:rgba(240,242,245,.43);font:10px 'JetBrains Mono',monospace}
  .match-summary{display:grid;grid-template-columns:1.5fr .55fr .55fr;gap:0;padding:18px 28px;border-bottom:1px solid rgba(240,242,245,.08)}.match-summary>div{min-width:0;padding-right:18px}.match-summary>div+div{padding-left:18px;border-left:1px solid rgba(240,242,245,.08)}.match-summary span,.info span,.chase-facts span,.innings-label,.innings-link span{display:block;color:rgba(240,242,245,.4);font:700 8px 'JetBrains Mono',monospace;letter-spacing:.08em}.match-summary h2{margin:6px 0 0;color:#fff;font:23px/1 'Bebas Neue',sans-serif;letter-spacing:.03em}.summary-score strong{display:block;margin-top:6px;color:#fff;font:19px 'JetBrains Mono',monospace;letter-spacing:-.06em}.summary-score small{display:block;overflow:hidden;margin-top:4px;color:rgba(240,242,245,.43);font:10px 'Inter',sans-serif;text-overflow:ellipsis;white-space:nowrap}
  .intel-tabs{display:flex;gap:0;padding:0 28px;border-bottom:1px solid rgba(240,242,245,.08)}.intel-tabs button{position:relative;padding:16px 15px 14px;border:0;background:transparent;color:rgba(240,242,245,.46);cursor:pointer;font:700 10px 'JetBrains Mono',monospace;letter-spacing:.07em}.intel-tabs button:first-child{padding-left:0}.intel-tabs button.active{color:#f5a623}.intel-tabs button.active:after{position:absolute;right:10px;bottom:-1px;left:0;height:2px;background:#f5a623;content:''}.intel-tabs button:hover{color:#fff}
  .tab-panel{padding:25px 28px 30px}.panel-head{display:flex;justify-content:space-between;gap:15px;align-items:end;margin-bottom:18px}.panel-head h2{margin:5px 0 0;color:#fff;font:28px/1 'Bebas Neue',sans-serif;letter-spacing:.035em}.panel-head>small{max-width:220px;color:rgba(240,242,245,.4);font:10px 'Inter',sans-serif;text-align:right}.conditions-grid{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid rgba(240,242,245,.08);border-radius:5px;background:rgba(0,0,0,.16)}.info{min-width:0;padding:12px}.info+.info{border-left:1px solid rgba(240,242,245,.08)}.info strong{display:block;overflow:hidden;margin-top:6px;color:rgba(240,242,245,.9);font:600 12px/1.35 'Inter',sans-serif;text-overflow:ellipsis;white-space:nowrap}.info.risk strong{color:#ff96aa}.records-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:12px}.record{padding:14px;border:1px solid rgba(240,242,245,.07);border-radius:5px;background:rgba(0,0,0,.15)}.record>div{display:flex;justify-content:space-between;gap:14px;align-items:baseline;margin-bottom:7px}.record h3,.read-item h3,.innings-card h3{margin:0;color:#fff;font:18px/1 'Bebas Neue',sans-serif;letter-spacing:.025em}.record small{color:rgba(240,242,245,.37);font:9px 'Inter',sans-serif;text-align:right}.pointer{display:flex;justify-content:space-between;gap:14px;padding:4px 0;color:rgba(240,242,245,.56);font-size:11px}.pointer+.pointer{border-top:1px solid rgba(240,242,245,.05)}.pointer strong{color:rgba(240,242,245,.94);font:700 11px 'JetBrains Mono',monospace;text-align:right}.range{display:flex;gap:10px;align-items:center;margin:13px 0 3px}.range strong{color:#fff;font:700 14px 'JetBrains Mono',monospace}.range i{height:5px;flex:1;border-radius:4px;background:linear-gradient(90deg,#f5a623,#e8003a)}
  .read-list{display:grid}.read-item{display:grid;grid-template-columns:36px 1fr;gap:13px;padding:16px 0;border-bottom:1px solid rgba(240,242,245,.07)}.read-index{display:grid;place-content:center;width:29px;height:29px;border:1px solid rgba(101,170,255,.34);border-radius:3px;background:rgba(63,129,209,.1);color:#9ac5ff;font:700 10px 'JetBrains Mono',monospace}.read-meta{display:flex;gap:10px;align-items:center;margin-bottom:6px;color:#8dbdff;font:700 9px 'JetBrains Mono',monospace;letter-spacing:.07em;text-transform:uppercase}.read-meta small{color:rgba(240,242,245,.36);font:9px 'JetBrains Mono',monospace}.read-item .pointer{max-width:560px}
  .innings-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.innings-card{min-height:255px;padding:18px;border:1px solid rgba(245,166,35,.23);border-radius:6px;background:linear-gradient(135deg,rgba(245,166,35,.08),rgba(0,0,0,.12))}.innings-card.second{border-color:rgba(101,170,255,.25);background:linear-gradient(135deg,rgba(57,112,191,.13),rgba(0,0,0,.12))}.innings-card.second.qualified{border-color:rgba(99,216,154,.32);background:linear-gradient(135deg,rgba(69,150,103,.13),rgba(0,0,0,.12))}.innings-label{color:#f5a623}.second .innings-label{color:#8dbdff}.innings-label span{display:inline;color:rgba(240,242,245,.38);font-size:8px}.innings-card h3{margin-top:11px}.innings-score{margin:7px 0 3px;color:#fff;font:36px/.95 'Bebas Neue',sans-serif;letter-spacing:.035em}.innings-detail{margin:0;color:rgba(240,242,245,.48);font:11px 'Inter',sans-serif}.comparison-list{display:grid;gap:9px;margin-top:18px}.comparison-list>div{padding-top:9px;border-top:1px solid rgba(240,242,245,.08)}.comparison-list strong{display:block;color:#fff;font:13px 'Inter',sans-serif}.comparison-list span{display:block;margin-top:4px;color:rgba(240,242,245,.53);font:10px 'JetBrains Mono',monospace}.chase-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:18px;border:1px solid rgba(240,242,245,.08);border-radius:4px;background:rgba(0,0,0,.14)}.chase-facts>div{min-width:0;padding:10px}.chase-facts>div+div{border-left:1px solid rgba(240,242,245,.08)}.chase-facts strong{display:block;overflow:hidden;margin-top:5px;color:#fff;font:700 11px 'JetBrains Mono',monospace;text-overflow:ellipsis;white-space:nowrap}.innings-link{display:flex;align-items:baseline;flex-wrap:wrap;gap:8px;margin-top:12px;padding:12px;border-top:1px solid rgba(240,242,245,.08)}.innings-link span{color:#f5a623}.innings-link strong{color:#fff;font:700 12px 'JetBrains Mono',monospace}.innings-link small{color:rgba(240,242,245,.38);font:10px 'Inter',sans-serif}
  .no-data{display:grid;min-height:110px;place-items:center;margin:0;color:rgba(240,242,245,.43);font:12px/1.5 'Inter',sans-serif;text-align:center}.state-copy{padding:28px;color:rgba(240,242,245,.52);font:11px 'JetBrains Mono',monospace;text-align:center}.state-copy.error{color:#ff9ab4;border-top:1px solid rgba(232,0,58,.22);background:rgba(232,0,58,.06)}
  @media(max-width:720px){.tactical-header,.tab-panel{padding-right:18px;padding-left:18px}.tactical-header{padding-top:22px}.tactical-status{display:none}.match-summary{grid-template-columns:1fr 1fr;padding:16px 18px}.match-summary>div:first-child{grid-column:1/-1;padding-bottom:13px;margin-bottom:13px;border-bottom:1px solid rgba(240,242,245,.08)}.match-summary>div+div{padding-left:12px}.intel-tabs{overflow-x:auto;padding:0 18px}.intel-tabs button{white-space:nowrap}.conditions-grid,.innings-grid{grid-template-columns:1fr}.info+.info{border-top:1px solid rgba(240,242,245,.08);border-left:0}.records-grid{grid-template-columns:1fr}.chase-facts{grid-template-columns:1fr}.chase-facts>div+div{border-top:1px solid rgba(240,242,245,.08);border-left:0}.panel-head>small{display:none}}
  @media(prefers-reduced-motion:reduce){.tactical-kicker i,.tactical-status i,.match-tab span i{box-shadow:none}}
`;

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
