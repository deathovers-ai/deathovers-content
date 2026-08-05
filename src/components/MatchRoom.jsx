import React, { useEffect, useMemo, useState } from 'react';

const MATCH_API = 'https://deathovers-ai-engine.onrender.com/api/match-details';

export default function MatchRoom() {
  const [matchId, setMatchId] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [venueOpen, setVenueOpen] = useState(false);
  const [feedOpen, setFeedOpen] = useState(false);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id');
    if (!id) {
      setError('No match selected. Open a match from Live.');
      setLoading(false);
      return;
    }
    setMatchId(id);
  }, []);

  useEffect(() => {
    if (!matchId) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(`${MATCH_API}/${matchId}`);
        if (!response.ok) throw new Error(`Server returned ${response.status}`);
        const payload = await response.json();
        if (!cancelled) {
          setData(payload);
          setError(null);
          setLoading(false);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError.message || 'Unable to load match data');
          setLoading(false);
        }
      }
    };
    load();
    const timer = window.setInterval(load, 60000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [matchId]);

  const view = useMemo(() => buildView(data), [data]);

  return (
    <main className="match-room">
      <a className="back-link" href="/">â† LIVE CENTRE</a>
      {loading && <LoadState label="Opening the Match Room" />}
      {error && <LoadState label={`Match Room unavailable: ${error}`} error />}
      {!loading && !error && (
        <div className="command-board">
          <DashboardHeader view={view} />
          <section className="dashboard-grid dashboard-grid-top">
            <LiveMatchPanel view={view} />
            <EnginePanel view={view} />
          </section>
          {view.momentum && <MomentumSlider momentum={view.momentum} />}
          {view.matchup && <MatchupCard matchup={view.matchup} />}
          <section className="dashboard-grid dashboard-grid-bottom">
            <VenuePanel view={view} open={venueOpen} onToggle={() => setVenueOpen((open) => !open)} />
            <TacticalFeed view={view} open={feedOpen} onToggle={() => setFeedOpen((open) => !open)} />
          </section>
        </div>
      )}
      <style>{styles}</style>
    </main>
  );
}

function DashboardHeader({ view }) {
  return (
    <header className="board-header board-enter">
      <div>
        <p className="live-kicker"><i /> LIVE MATCH ROOM <span>•</span> DECISION DESK</p>
        <h1>{view.teamOne} <em>vs</em> {view.teamTwo}</h1>
        <p className="board-subtitle">A single match workspace: score, conditions, venue evidence and chase decisions.</p>
      </div>
      <div className="header-status">
        <div className="watch-status"><i /><span>WATCHING LIVE</span><small>refreshes every 60 sec</small></div>
        <FreshnessChip freshness={view.freshness} />
      </div>
    </header>
  );
}

function FreshnessChip({ freshness }) {
  if (!freshness) return null;
  if (!freshness.known) {
    return <div className="freshness-chip unknown" title="Context build time not available"><span>DATA</span><strong>FRESHNESS UNKNOWN</strong></div>;
  }
  if (freshness.stale) {
    return <div className="freshness-chip stale" title={`Built ${freshness.generated_at || 'unknown'}`}><span>REFRESH PENDING</span><strong>DATA THRU {formatFreshDate(freshness.corpus_through || freshness.generated_at)}</strong></div>;
  }
  return <div className="freshness-chip" title={`Built ${freshness.generated_at || 'unknown'}`}><span>DATA THRU</span><strong>{formatFreshDate(freshness.corpus_through || freshness.generated_at)}</strong></div>;
}

function formatFreshDate(value) {
  if (!value) return '—';
  return String(value).slice(0, 10);
}

function LiveMatchPanel({ view }) {
  const score = view.liveInnings;
  return (
    <section className="panel live-panel board-enter">
      <PanelTitle eyebrow="MATCH CONTROL" title="Live match state" tag={score?.phase || 'IN PLAY'} />
      <div className="score-hero">
        <div>
          <p className="team-name">{score?.team || 'LIVE MATCH'}</p>
          <p className="score-value">{score?.runs ?? 'â€”'}<span>/{score?.wickets ?? 'â€”'}</span></p>
          <p className="over-line">{formatOvers(score)} <span>â€¢</span> {score?.phase ? `${score.phase} phase` : 'score updating'}</p>
        </div>
        <div className="innings-pill"><span>INNINGS</span><strong>{view.inningsLabel}</strong></div>
      </div>
      <div className="context-rail">
        <ContextCell label="Toss" value={view.tossText} />
        <ContextCell label="Conditions" value={view.weatherText} />
        <ContextCell label="Dew" value={view.dewText} accent={view.dewRisk?.risk === 'HIGH' ? 'danger' : view.dewRisk ? 'amber' : ''} />
      </div>
      <p className="source-note">Live context is retained for this match only. Historical data remains in the engine index.</p>
    </section>
  );
}

function MomentumSlider({ momentum }) {
  const index = Number(momentum.index);
  const pct = ((Math.max(-1, Math.min(1, index)) + 1) / 2) * 100;
  const tone = index >= 0.2 ? 'good' : index <= -0.2 ? 'bad' : '';
  return (
    <section className="panel momentum-panel board-enter">
      <PanelTitle eyebrow="MOMENTUM" title="Live momentum index" tag={momentum.label || 'EVEN'} />
      <p className="panel-intro">{momentum.headline || 'Continuous −1 to +1 reading from the last three overs.'}</p>
      <div className="momentum-track">
        <span>−1</span>
        <div className="momentum-bar">
          <i style={{ left: `${pct}%` }} />
          <em style={{ width: `${pct}%` }} className={tone} />
        </div>
        <span>+1</span>
      </div>
      <div className="momentum-metrics">
        <Metric label="Index" value={Number.isFinite(index) ? `${index >= 0 ? '+' : ''}${index.toFixed(2)}` : '—'} tone={tone} />
        <Metric label="Reading" value={momentum.label || 'EVEN'} />
        <Metric
          label="Phase pct"
          value={momentum.percentile == null ? '—' : `${Math.round(momentum.percentile)}th`}
          detail={momentum.phase ? `${momentum.phase} baseline` : 'awaiting phase'}
        />
        <Metric label="Window" value={`${momentum.window_balls || 18} balls`} detail="rolling" />
      </div>
    </section>
  );
}

function MatchupCard({ matchup }) {
  const metrics = (matchup.pointers || []).filter((p) =>
    ['Matchup SR', 'Balls', 'Dismissals', 'Matchup Avg'].includes(p.label)
  );
  const meta = (matchup.pointers || []).filter((p) =>
    ['Years', 'Venues'].includes(p.label)
  );
  return (
    <section className="panel matchup-panel board-enter">
      <PanelTitle eyebrow="MATCHUP" title={`${matchup.batter} vs ${matchup.bowler}`} tag={`${matchup.balls || '—'} BALLS`} />
      <p className="panel-intro">{matchup.headline || 'Historical head-to-head for the live pair.'}</p>
      <div className="matchup-metrics">
        {metrics.map((pointer, index) => (
          <Metric key={`${pointer.label}-${index}`} label={pointer.label} value={formatPointer(pointer)} />
        ))}
      </div>
      {meta.length > 0 && (
        <div className="matchup-meta">
          {meta.map((pointer, index) => (
            <div className="matchup-meta-row" key={`${pointer.label}-${index}`}>
              <span>{pointer.label}</span>
              <strong>{formatPointer(pointer)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function EnginePanel({ view }) {
  const { chase, winProbability: wp } = view;
  const active = chase?.state;
  const qualified = active && chase.status === 'qualified';
  const cohort = chase?.cohort;
  const ahead = (cohort?.pace_gap_runs || 0) >= 0;
  const title = qualified ? (ahead ? 'Ahead of historical pace' : 'Behind historical pace') : active ? 'Historical read building' : 'Engine on standby';
  const description = qualified
    ? `This chase is ${ahead ? 'ahead of' : 'behind'} the successful pace line at this point.`
    : active ? 'Live chase confirmed. The engine is matching the score to comparable chases.'
    : 'Watching the match. The chase comparison starts automatically in a valid second innings.';
  const wpPct = wp ? Math.round((wp.batting_wp || 0) * 100) : null;

  return (
    <section className={`panel engine-panel ${qualified ? (ahead ? 'engine-good' : 'engine-alert') : 'engine-wait'} board-enter`}>
      <PanelTitle eyebrow="CHASE ENGINE" title="Decision signal" tag={qualified ? 'QUALIFIED' : 'WATCHING'} />
      <div className="engine-main">
        <div>
          <p className="engine-state">{title}</p>
          <p className="engine-description">{description}</p>
        </div>
        <div className="signal-pair">
          <div className="signal-orb"><strong>{qualified ? `${Math.round((cohort?.recovery_rate || 0) * 100)}%` : 'LIVE'}</strong><span>{qualified ? 'RECOVERY' : 'READY'}</span></div>
          {wpPct != null && (
            <div className={`signal-orb wp-orb ${wp.uncertain ? 'wp-uncertain' : ''}`}>
              <strong>{wpPct}%</strong>
              <span>{wp.uncertain ? 'EARLY WP' : 'WIN PROB'}</span>
            </div>
          )}
        </div>
      </div>
      {wp && (
        <div className="wp-bar-wrap">
          <div className="wp-bar-labels"><span>Batting {wpPct}%</span><span>{wp.label || 'WP'}</span><span>Bowling {Math.round((wp.bowling_wp || 0) * 100)}%</span></div>
          <div className="wp-bar"><em style={{ width: `${wpPct}%` }} /></div>
        </div>
      )}
      {active ? <ChaseStrip state={active} /> : <StandbyStrip view={view} />}
      <div className="engine-metrics">
        <Metric label={qualified ? 'Pace gap' : 'Historical read'} value={qualified ? signed(cohort?.pace_gap_runs, ' runs') : 'Awaiting chase'} tone={qualified ? (ahead ? 'good' : 'bad') : ''} />
        <Metric label="Evidence" value={qualified ? `${cohort?.sample_size || 0} comparable` : 'Live score + venue'} detail={qualified ? `${cohort?.wins || 0} successful` : 'match-specific cache'} />
        <Metric label="First innings" value={view.firstInnings ? `${view.firstInnings.runs}/${view.firstInnings.wickets}` : 'Collecting'} detail={active ? `Target ${active.target}` : 'available at interval'} />
      </div>
    </section>
  );
}

function VenuePanel({ view, open, onToggle }) {
  const records = view.venueRecords;
  return (
    <section className="panel venue-panel board-enter">
      <PanelTitle eyebrow="VENUE RECORD" title="Ground intelligence" tag={view.venueSample ? `${view.venueSample} MATCHES` : 'GROUND DATA'} />
      <p className="panel-intro">Venue evidence is separate from the live score so the decision has a clear basis.</p>
      {records.length ? (
        <>
          <div className="record-summary">
            {records.slice(0, 3).map((record) => <RecordCard key={record.title} record={record} compact />)}
          </div>
          <button type="button" className="expand-button" onClick={onToggle}>{open ? 'Hide full venue record' : 'Open full venue record'} <span>{open ? 'â†‘' : 'â†“'}</span></button>
          {open && <div className="record-expanded">{records.map((record) => <RecordCard key={record.title} record={record} />)}</div>}
        </>
      ) : <EmptyCopy>Venue record will appear when this ground has verified historical coverage.</EmptyCopy>}
    </section>
  );
}

function TacticalFeed({ view, open, onToggle }) {
  const visible = open ? view.timeline : view.timeline.slice(0, 3);
  return (
    <section className="panel feed-panel board-enter">
      <PanelTitle eyebrow="MATCH ROOM" title="Tactical feed" tag={`${view.timeline.length} READ${view.timeline.length === 1 ? '' : 'S'}`} />
      {visible.length ? <div className="feed-list">{visible.map((item, index) => <FeedItem key={`${item.headline}-${index}`} item={item} />)}</div> : <EmptyCopy>No tactical reads yet. The feed fills as verified score snapshots arrive.</EmptyCopy>}
      {view.timeline.length > 3 && <button type="button" className="expand-button" onClick={onToggle}>{open ? 'Show fewer reads' : `Show ${view.timeline.length - 3} more reads`} <span>{open ? 'â†‘' : 'â†“'}</span></button>}
    </section>
  );
}

function PanelTitle({ eyebrow, title, tag }) {
  return <div className="panel-title"><div><span>{eyebrow}</span><h2>{title}</h2></div>{tag && <b>{tag}</b>}</div>;
}

function ContextCell({ label, value, accent }) {
  return <div className={`context-cell ${accent ? `context-${accent}` : ''}`}><span>{label}</span><strong>{value || 'Not available'}</strong></div>;
}

function Metric({ label, value, detail, tone }) {
  return <div className={`metric ${tone ? `metric-${tone}` : ''}`}><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function ChaseStrip({ state }) {
  return <div className="chase-strip"><Metric label="Chase score" value={`${state.runs}/${state.wickets}`} /><Metric label="To win" value={`${state.runs_required} from ${state.legal_balls_remaining}`} detail="runs â€¢ balls" /><Metric label="Required rate" value={number(state.required_run_rate)} /></div>;
}

function StandbyStrip({ view }) {
  return <div className="chase-strip"><Metric label="Current phase" value={view.liveInnings?.phase || 'In play'} /><Metric label="Engine mode" value="Match watch" detail="no API waste" /><Metric label="Next trigger" value="Second innings" /></div>;
}

function RecordCard({ record, compact = false }) {
  const pointers = compact ? record.pointers.slice(0, 2) : record.pointers;
  return <div className="record-card"><div className="record-head"><h3>{record.title}</h3>{record.basis && <small>{record.basis}</small>}</div>{pointers.map((pointer, index) => <div className="record-row" key={index}><span>{pointer.label}</span><strong>{pointer.value}</strong></div>)}</div>;
}

function FeedItem({ item }) {
  return <article className="feed-item"><div className="feed-marker" /><div><div className="feed-topline">{item.gauge?.level && <span className={`gauge gauge-${item.gauge.level.toLowerCase()}`}>{item.gauge.level}</span>}<small>{item.type?.replaceAll('_', ' ') || 'match read'}</small></div><h3>{item.headline || 'Match update'}</h3>{item.pointers?.map((pointer, index) => <div className="feed-row" key={index}><span>{pointer.label}</span><strong>{formatPointer(pointer)}</strong></div>)}</div></article>;
}

function EmptyCopy({ children }) { return <p className="empty-copy">{children}</p>; }
function LoadState({ label, error = false }) { return <div className={`load-state ${error ? 'load-error' : ''}`}><i />{label}</div>; }
function number(value) { return value == null ? 'â€”' : Number(value).toFixed(2); }
function signed(value, suffix) { if (value == null) return 'â€”'; const rounded = Math.abs(value) < 10 ? Number(value).toFixed(1) : Math.round(value); return `${value > 0 ? '+' : ''}${rounded}${suffix}`; }
function formatOvers(innings) { if (innings?.overs != null) return `${innings.overs} overs`; if (innings?.balls != null) return `${Math.floor(innings.balls / 6)}.${innings.balls % 6} overs`; return 'Live score'; }
function formatPointer(pointer) { const pct = pointer?.pct == null ? '' : ` (${pointer.pct > 0 ? '+' : ''}${pointer.pct}%)`; return `${pointer?.value ?? 'â€”'}${pointer?.unit || ''}${pct}`; }

function buildView(data) {
  const innings = data?.innings || [];
  const liveInnings = innings[innings.length - 1];
  const firstInnings = data?.chase?.first_innings || innings[0];
  const insights = data?.intelligence?.insights || [];
  const pregame = insights.find((item) => item.type === 'venue_pregame_summary');
  const matchup = insights.find((item) => item.type === 'bowler_batter_matchup') || null;
  const momentum = insights.find((item) => item.type === 'momentum_index') || null;
  const timeline = insights
    .filter((item) => item.type !== 'venue_pregame_summary'
      && item.type !== 'bowler_batter_matchup'
      && item.type !== 'momentum_index')
    .slice()
    .reverse();
  const sections = [
    ['Toss & decision', pregame?.toss_record],
    ['Scoring record', pregame?.score_record],
    ['Chase record', pregame?.chase_record],
  ].filter(([, record]) => record).map(([title, record]) => ({ title, basis: record.basis, pointers: (record.pointers || []).map((p) => ({ label: p.label, value: formatPointer(p) })) }));
  if (pregame?.score_range) sections.push({ title: 'Innings score range', basis: pregame.score_range.basis, pointers: [{ label: 'Range', value: `${pregame.score_range.low} â€” ${pregame.score_range.high}` }] });
  return {
    teamOne: innings[0]?.team || 'MATCH', teamTwo: innings[1]?.team || 'ROOM', innings, liveInnings, firstInnings,
    inningsLabel: innings.length ? `${innings.length}${innings.length === 1 ? 'ST' : 'ND'}` : 'LIVE',
    tossText: data?.toss?.winner ? `${data.toss.winner} chose to ${data.toss.decision || 'play'}` : 'Awaiting toss',
    weatherText: data?.weather?.condition ? `${data.weather.condition}${data.weather.temp_c != null ? ` â€¢ ${Math.round(data.weather.temp_c)}Â°C` : ''}` : 'Weather pending',
    dewText: data?.dewRisk?.risk ? `${data.dewRisk.risk} risk` : 'No alert', dewRisk: data?.dewRisk,
    chase: data?.chase, timeline, venueRecords: sections, venueSample: pregame?.sample_size,
    matchup,
    momentum,
    winProbability: data?.win_probability || null,
    freshness: data?.intelligence?.data_freshness || null,
  };
}

const styles = `
  .match-room { max-width: 1180px; margin: 0 auto; padding: 22px 0 42px; }
  .back-link { display:inline-block; margin-bottom:18px; color:rgba(240,242,245,.48); font:700 10px 'JetBrains Mono',monospace; letter-spacing:.1em; text-decoration:none; transition:color .18s ease,transform .18s ease; } .back-link:hover { color:#f5a623; transform:translateX(-3px); }
  .command-board { overflow:hidden; border:1px solid rgba(240,242,245,.1); border-radius:12px; background:linear-gradient(135deg,rgba(25,30,38,.96),rgba(11,13,18,.99)); box-shadow:0 25px 70px rgba(0,0,0,.3); }
  .board-header { display:flex; justify-content:space-between; gap:24px; align-items:flex-end; padding:30px 30px 25px; border-bottom:1px solid rgba(240,242,245,.09); background:radial-gradient(circle at 83% 0%,rgba(245,166,35,.13),transparent 28%); }
  .live-kicker,.panel-title span { margin:0 0 8px; color:#f5a623; font:700 10px 'JetBrains Mono',monospace; letter-spacing:.11em; } .live-kicker i,.watch-status i { display:inline-block; width:7px; height:7px; margin-right:8px; border-radius:50%; background:#64d89a; box-shadow:0 0 0 4px rgba(100,216,154,.11); animation:pulse 1.8s infinite; } .live-kicker span { color:rgba(240,242,245,.3); padding:0 5px; }
  .board-header h1 { margin:0; color:#fff; font:48px/.95 'Bebas Neue',sans-serif; letter-spacing:.03em; } .board-header h1 em { color:#e8003a; font-size:.55em; font-style:normal; vertical-align:middle; } .board-subtitle { max-width:560px; margin:10px 0 0; color:rgba(240,242,245,.52); font-size:13px; }
  .watch-status { display:grid; gap:4px; min-width:150px; text-align:right; color:#fff; font:700 10px 'JetBrains Mono',monospace; letter-spacing:.08em; } .watch-status i { margin:2px 0 0 auto; } .watch-status small { color:rgba(240,242,245,.4); font:400 9px 'JetBrains Mono',monospace; letter-spacing:0; }
  .header-status { display:grid; gap:8px; justify-items:end; } .freshness-chip { display:grid; gap:2px; padding:6px 8px; border:1px solid rgba(240,242,245,.14); border-radius:4px; background:rgba(0,0,0,.2); text-align:right; } .freshness-chip span { color:rgba(240,242,245,.42); font:700 8px 'JetBrains Mono',monospace; letter-spacing:.08em; } .freshness-chip strong { color:rgba(240,242,245,.88); font:700 10px 'JetBrains Mono',monospace; letter-spacing:.02em; } .freshness-chip.stale { border-color:rgba(245,166,35,.4); background:rgba(245,166,35,.08); } .freshness-chip.stale span { color:#f5a623; } .freshness-chip.unknown { border-color:rgba(240,242,245,.1); }
  .dashboard-grid { display:grid; } .dashboard-grid-top { grid-template-columns:1.05fr .95fr; } .dashboard-grid-bottom { grid-template-columns:1fr 1fr; border-top:1px solid rgba(240,242,245,.08); }
  .panel { min-width:0; padding:25px 30px; } .dashboard-grid > .panel + .panel { border-left:1px solid rgba(240,242,245,.08); }
  .panel-title { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:20px; } .panel-title span { display:block; margin-bottom:6px; } .panel-title h2 { margin:0; color:#fff; font:25px/1 'Bebas Neue',sans-serif; letter-spacing:.035em; } .panel-title b { padding:5px 7px; border:1px solid rgba(240,242,245,.12); border-radius:3px; color:rgba(240,242,245,.55); font:700 9px 'JetBrains Mono',monospace; letter-spacing:.07em; white-space:nowrap; }
  .score-hero { display:flex; justify-content:space-between; align-items:flex-end; padding-bottom:20px; } .team-name,.over-line { margin:0; color:rgba(240,242,245,.52); font:700 10px 'JetBrains Mono',monospace; letter-spacing:.08em; text-transform:uppercase; } .score-value { margin:5px 0; color:#fff; font:52px/.88 'Bebas Neue',sans-serif; letter-spacing:.025em; } .score-value span { color:rgba(240,242,245,.56); } .over-line span { color:#f5a623; padding:0 6px; } .innings-pill { display:grid; place-items:center; width:58px; height:58px; border:1px solid rgba(245,166,35,.35); border-radius:8px; background:rgba(245,166,35,.07); } .innings-pill span { color:rgba(240,242,245,.5); font:700 8px 'JetBrains Mono',monospace; } .innings-pill strong { color:#fff; font:24px/1 'Bebas Neue',sans-serif; }
  .context-rail { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid rgba(240,242,245,.08); border-radius:5px; background:rgba(0,0,0,.17); } .context-cell { min-width:0; padding:11px 12px; } .context-cell + .context-cell { border-left:1px solid rgba(240,242,245,.08); } .context-cell span,.metric span { display:block; color:rgba(240,242,245,.4); font:700 8px 'JetBrains Mono',monospace; letter-spacing:.08em; text-transform:uppercase; } .context-cell strong { display:block; overflow:hidden; margin-top:5px; color:rgba(240,242,245,.9); font:600 11px/1.3 'Inter',sans-serif; text-overflow:ellipsis; white-space:nowrap; } .context-danger strong { color:#ff94a7; } .context-amber strong { color:#f5c567; } .source-note { margin:12px 0 0; color:rgba(240,242,245,.34); font-size:10px; line-height:1.4; }
  .engine-panel { position:relative; background:radial-gradient(circle at 92% 12%,rgba(101,170,255,.14),transparent 33%); } .engine-good { background:radial-gradient(circle at 92% 12%,rgba(93,216,150,.12),transparent 33%); } .engine-alert { background:radial-gradient(circle at 92% 12%,rgba(232,0,58,.15),transparent 33%); } .engine-main { display:flex; justify-content:space-between; gap:18px; align-items:center; min-height:92px; } .engine-state { margin:0; color:#fff; font:32px/1 'Bebas Neue',sans-serif; letter-spacing:.025em; } .engine-alert .engine-state { color:#ff97aa; } .engine-good .engine-state { color:#76d9a1; } .engine-description { max-width:370px; margin:8px 0 0; color:rgba(240,242,245,.57); font-size:12px; line-height:1.45; } .signal-pair { display:flex; gap:10px; flex:0 0 auto; } .signal-orb { flex:0 0 75px; height:75px; display:grid; place-content:center; border:1px solid rgba(101,170,255,.45); border-radius:50%; background:rgba(58,112,190,.09); text-align:center; } .engine-good .signal-orb { border-color:rgba(93,216,150,.45); } .engine-alert .signal-orb { border-color:rgba(232,0,58,.48); } .signal-orb strong { color:#fff; font:20px/1 'JetBrains Mono',monospace; letter-spacing:-.06em; } .signal-orb span { margin-top:4px; color:rgba(240,242,245,.44); font:700 7px 'JetBrains Mono',monospace; letter-spacing:.08em; } .wp-orb { border-color:rgba(245,166,35,.45); background:rgba(245,166,35,.08); } .wp-orb.wp-uncertain { border-style:dashed; opacity:.92; } .wp-bar-wrap { margin-top:14px; } .wp-bar-labels { display:flex; justify-content:space-between; gap:8px; margin-bottom:6px; color:rgba(240,242,245,.48); font:700 8px 'JetBrains Mono',monospace; letter-spacing:.06em; text-transform:uppercase; } .wp-bar { height:8px; border-radius:999px; background:rgba(240,242,245,.08); overflow:hidden; } .wp-bar em { display:block; height:100%; background:linear-gradient(90deg,rgba(232,0,58,.55),rgba(245,166,35,.7) 45%,rgba(93,216,150,.75)); }
  .chase-strip { display:grid; grid-template-columns:repeat(3,1fr); margin-top:16px; border:1px solid rgba(240,242,245,.08); border-radius:5px; background:rgba(0,0,0,.17); } .metric { min-width:0; padding:10px 11px; } .metric + .metric { border-left:1px solid rgba(240,242,245,.08); } .metric strong { display:block; overflow:hidden; margin-top:5px; color:#fff; font:700 13px/1.2 'JetBrains Mono',monospace; letter-spacing:-.04em; text-overflow:ellipsis; white-space:nowrap; } .metric small { display:block; margin-top:3px; color:rgba(240,242,245,.36); font:9px 'Inter',sans-serif; } .metric-good strong { color:#6cdaa0; } .metric-bad strong { color:#ff94a7; }
  .engine-metrics { display:grid; grid-template-columns:repeat(3,1fr); margin-top:10px; }
  .matchup-panel { border-top:1px solid rgba(240,242,245,.08); background:radial-gradient(circle at 8% 0%,rgba(245,166,35,.1),transparent 28%); } .matchup-metrics { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid rgba(240,242,245,.08); border-radius:5px; background:rgba(0,0,0,.17); } .matchup-metrics .metric + .metric { border-left:1px solid rgba(240,242,245,.08); } .matchup-meta { margin-top:10px; border:1px solid rgba(240,242,245,.07); border-radius:5px; background:rgba(0,0,0,.12); } .matchup-meta-row { display:flex; justify-content:space-between; gap:14px; padding:8px 11px; color:rgba(240,242,245,.55); font-size:11px; } .matchup-meta-row + .matchup-meta-row { border-top:1px solid rgba(240,242,245,.06); } .matchup-meta-row strong { color:rgba(240,242,245,.9); font:600 11px/1.35 'Inter',sans-serif; text-align:right; }
  .momentum-panel { border-top:1px solid rgba(240,242,245,.08); background:radial-gradient(circle at 92% 0%,rgba(101,170,255,.12),transparent 30%); } .momentum-track { display:grid; grid-template-columns:28px 1fr 28px; gap:10px; align-items:center; margin:4px 0 14px; color:rgba(240,242,245,.4); font:700 9px 'JetBrains Mono',monospace; } .momentum-bar { position:relative; height:10px; border-radius:999px; background:linear-gradient(90deg,rgba(232,0,58,.35),rgba(240,242,245,.12) 50%,rgba(93,216,150,.35)); overflow:hidden; } .momentum-bar em { position:absolute; inset:0 auto 0 0; background:rgba(240,242,245,.08); } .momentum-bar em.good { background:rgba(93,216,150,.22); } .momentum-bar em.bad { background:rgba(232,0,58,.22); } .momentum-bar i { position:absolute; top:50%; width:14px; height:14px; border:2px solid #fff; border-radius:50%; background:#65aaff; box-shadow:0 0 0 4px rgba(101,170,255,.18); transform:translate(-50%,-50%); } .momentum-metrics { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid rgba(240,242,245,.08); border-radius:5px; background:rgba(0,0,0,.17); } .momentum-metrics .metric + .metric { border-left:1px solid rgba(240,242,245,.08); }
  .panel-intro,.empty-copy { margin:0 0 17px; color:rgba(240,242,245,.5); font-size:12px; line-height:1.5; } .empty-copy { min-height:130px; display:grid; place-items:center; text-align:center; }
  .record-summary { display:grid; gap:8px; } .record-card { padding:12px 13px; border:1px solid rgba(240,242,245,.07); border-radius:5px; background:rgba(0,0,0,.15); } .record-head { display:flex; justify-content:space-between; gap:12px; align-items:baseline; margin-bottom:7px; } .record-head h3,.feed-item h3 { margin:0; color:#fff; font:17px/1 'Bebas Neue',sans-serif; letter-spacing:.025em; } .record-head small { color:rgba(240,242,245,.37); font:9px 'Inter',sans-serif; text-align:right; } .record-row,.feed-row { display:flex; justify-content:space-between; gap:12px; padding:4px 0; color:rgba(240,242,245,.56); font-size:11px; } .record-row + .record-row,.feed-row + .feed-row { border-top:1px solid rgba(240,242,245,.05); } .record-row strong,.feed-row strong { color:rgba(240,242,245,.94); font:700 11px 'JetBrains Mono',monospace; text-align:right; } .expand-button { margin-top:13px; padding:0; border:0; background:none; color:#f5a623; cursor:pointer; font:700 10px 'JetBrains Mono',monospace; letter-spacing:.04em; } .expand-button span { padding-left:5px; } .record-expanded { display:grid; gap:8px; margin-top:14px; }
  .feed-list { display:grid; gap:0; } .feed-item { position:relative; display:grid; grid-template-columns:15px 1fr; gap:11px; padding:0 0 15px; } .feed-item + .feed-item { padding-top:15px; border-top:1px solid rgba(240,242,245,.07); } .feed-marker { width:7px; height:7px; margin-top:5px; border-radius:50%; background:#f5a623; box-shadow:0 0 0 4px rgba(245,166,35,.08); } .feed-topline { display:flex; align-items:center; gap:7px; margin-bottom:5px; } .feed-topline small { color:rgba(240,242,245,.38); font:9px 'JetBrains Mono',monospace; letter-spacing:.06em; text-transform:uppercase; } .gauge { padding:3px 5px; border-radius:3px; font:700 8px 'JetBrains Mono',monospace; letter-spacing:.06em; } .gauge-low { color:#6cdaa0; background:rgba(93,216,150,.1); } .gauge-moderate { color:#f5c567; background:rgba(245,166,35,.1); } .gauge-high,.gauge-critical { color:#ff94a7; background:rgba(232,0,58,.1); }
  .load-state { min-height:360px; display:grid; place-content:center; gap:12px; border:1px solid rgba(240,242,245,.08); border-radius:10px; color:rgba(240,242,245,.58); font:11px 'JetBrains Mono',monospace; text-align:center; } .load-state i { width:7px; height:7px; margin:auto; border-radius:50%; background:#f5a623; animation:pulse 1s infinite; } .load-error { color:#ff94a7; border-color:rgba(232,0,58,.25); } @keyframes pulse { 50% { opacity:.35; transform:scale(.8); } } .board-enter { animation:rise .45s cubic-bezier(.16,1,.3,1) both; } @keyframes rise { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:none; } }
  @media (max-width:800px) { .board-header { padding:23px 20px; } .dashboard-grid-top,.dashboard-grid-bottom { grid-template-columns:1fr; } .dashboard-grid > .panel + .panel { border-top:1px solid rgba(240,242,245,.08); border-left:0; } .panel { padding:22px 20px; } .board-header h1 { font-size:40px; } .watch-status { display:none; } .matchup-metrics,.momentum-metrics { grid-template-columns:1fr 1fr; } .matchup-metrics .metric:nth-child(3),.matchup-metrics .metric:nth-child(4),.momentum-metrics .metric:nth-child(3),.momentum-metrics .metric:nth-child(4) { border-top:1px solid rgba(240,242,245,.08); } .matchup-metrics .metric:nth-child(3),.momentum-metrics .metric:nth-child(3) { border-left:0; } }
  @media (max-width:500px) { .match-room { padding-top:14px; } .command-board { border-radius:8px; } .board-header { padding:21px 16px; } .panel { padding:20px 16px; } .score-value { font-size:46px; } .context-rail,.chase-strip,.engine-metrics { grid-template-columns:1fr 1fr; } .context-cell:nth-child(3),.chase-strip .metric:nth-child(3),.engine-metrics .metric:nth-child(3) { border-top:1px solid rgba(240,242,245,.08); } .context-cell:nth-child(3),.chase-strip .metric:nth-child(3),.engine-metrics .metric:nth-child(3) { border-left:0; } .context-cell:nth-child(3) { grid-column:1/-1; } .chase-strip .metric:nth-child(3),.engine-metrics .metric:nth-child(3) { grid-column:1/-1; } .engine-state { font-size:28px; } .signal-orb { flex-basis:58px; height:58px; } .signal-orb strong { font-size:16px; } .signal-pair { gap:8px; } }
  @media (prefers-reduced-motion:reduce) { .board-enter,.live-kicker i,.watch-status i,.load-state i { animation:none; } }
`;

