import React, { useMemo, useState } from 'react';

const API_BASE = 'https://deathovers-ai-engine.onrender.com/api';

const PRESETS = [
  {
    id: 'tight',
    label: 'Tight T20 chase',
    baseline: { format: 'T20', target: 170, runs: 98, wickets: 4, overs: '12.0' },
    fork: { wickets: 2 },
    note: 'What if two wickets fewer at the same score?',
  },
  {
    id: 'death',
    label: 'Death overs ask',
    baseline: { format: 'T20', target: 185, runs: 140, wickets: 5, overs: '16.0' },
    fork: { wickets: 7 },
    note: 'What if two more wickets had fallen before the death?',
  },
  {
    id: 'odi',
    label: 'ODI middle squeeze',
    baseline: { format: 'ODI', target: 280, runs: 150, wickets: 3, overs: '30.0' },
    fork: { overs: '35.0', runs: 150, wickets: 3 },
    note: 'What if five more overs had been used for the same runs?',
  },
];

const emptyForm = {
  format: 'T20',
  target: 170,
  runs: 100,
  wickets: 4,
  overs: '12.0',
  forkWickets: '2',
  forkOvers: '',
  venue: '',
  xi: '',
  battingOrder: '',
};

export default function WhatIfSimulator() {
  const [form, setForm] = useState(emptyForm);
  const [presetId, setPresetId] = useState('tight');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const applyPreset = (preset) => {
    setPresetId(preset.id);
    setForm({
      ...emptyForm,
      format: preset.baseline.format,
      target: preset.baseline.target,
      runs: preset.baseline.runs,
      wickets: preset.baseline.wickets,
      overs: String(preset.baseline.overs),
      forkWickets: preset.fork.wickets != null ? String(preset.fork.wickets) : '',
      forkOvers: preset.fork.overs != null ? String(preset.fork.overs) : '',
      venue: '',
      xi: '',
      battingOrder: '',
    });
    setResult(null);
    setError(null);
  };

  const body = useMemo(() => {
    const fork = {};
    if (form.forkWickets !== '') fork.wickets = Number(form.forkWickets);
    if (form.forkOvers.trim()) fork.overs = form.forkOvers.trim();
    const xi = form.xi.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    const batting_order = form.battingOrder.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    return {
      baseline: {
        format: form.format,
        target: Number(form.target),
        runs: Number(form.runs),
        wickets: Number(form.wickets),
        overs: form.overs,
      },
      fork,
      venue: form.venue.trim() || undefined,
      xi: xi.length ? xi : undefined,
      batting_order: batting_order.length ? batting_order : undefined,
      n_sims: 1500,
      seed: 42,
    };
  }, [form]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/what-if`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `Server returned ${response.status}`);
      setResult(payload);
    } catch (err) {
      setResult(null);
      setError(err.message || 'What-If unavailable');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="what-if">
      <header className="sim-header">
        <div>
          <p className="sim-kicker"><i /> SIMULATIONS <span>•</span> WHAT-IF DESK</p>
          <h1>WHAT-IF</h1>
          <p className="sim-sub">Fork a chase, resimulate with venue/format phase rates, compare actual baseline WP to the simulated fork.</p>
        </div>
      </header>

      <section className="preset-rail" aria-label="Scenario presets">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={presetId === preset.id ? 'preset active' : 'preset'}
            onClick={() => applyPreset(preset)}
          >
            <span>PRESET</span>
            <strong>{preset.label}</strong>
            <small>{preset.note}</small>
          </button>
        ))}
      </section>

      <section className="sim-grid">
        <form
          className="sim-panel"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="panel-head">
            <div>
              <span>BASELINE</span>
              <h2>Chase state</h2>
            </div>
            <small>Scoreboard facts only — not shot type or field.</small>
          </div>

          <div className="field-grid">
            <label>
              <span>Format</span>
              <select value={form.format} onChange={(e) => setField('format', e.target.value)}>
                <option value="T20">T20</option>
                <option value="IPL">IPL</option>
                <option value="ODI">ODI</option>
              </select>
            </label>
            <label>
              <span>Target</span>
              <input type="number" min="1" value={form.target} onChange={(e) => setField('target', e.target.value)} />
            </label>
            <label>
              <span>Runs</span>
              <input type="number" min="0" value={form.runs} onChange={(e) => setField('runs', e.target.value)} />
            </label>
            <label>
              <span>Wickets</span>
              <input type="number" min="0" max="10" value={form.wickets} onChange={(e) => setField('wickets', e.target.value)} />
            </label>
            <label>
              <span>Overs bowled</span>
              <input type="text" value={form.overs} onChange={(e) => setField('overs', e.target.value)} placeholder="12.0" />
            </label>
            <label>
              <span>Venue (optional)</span>
              <input type="text" value={form.venue} onChange={(e) => setField('venue', e.target.value)} placeholder="Wankhede Stadium" />
            </label>
          </div>

          <div className="panel-head fork-head">
            <div>
              <span>FORK</span>
              <h2>What if…</h2>
            </div>
            <small>Leave a fork field blank to keep the baseline value.</small>
          </div>
          <div className="field-grid">
            <label>
              <span>Fork wickets</span>
              <input type="number" min="0" max="10" value={form.forkWickets} onChange={(e) => setField('forkWickets', e.target.value)} />
            </label>
            <label>
              <span>Fork overs bowled</span>
              <input type="text" value={form.forkOvers} onChange={(e) => setField('forkOvers', e.target.value)} placeholder="same as baseline" />
            </label>
          </div>

          <div className="panel-head fork-head">
            <div>
              <span>XI GUARD</span>
              <h2>Playing XI</h2>
            </div>
            <small>Optional. Batting order may only use XI names (max 11).</small>
          </div>
          <div className="field-grid xi-grid">
            <label>
              <span>XI (comma or newline)</span>
              <textarea rows={3} value={form.xi} onChange={(e) => setField('xi', e.target.value)} placeholder="V Kohli, RG Sharma, …" />
            </label>
            <label>
              <span>Batting order</span>
              <textarea rows={3} value={form.battingOrder} onChange={(e) => setField('battingOrder', e.target.value)} placeholder="Must be subset of XI" />
            </label>
          </div>

          <button type="submit" className="run-btn" disabled={loading}>
            {loading ? 'SIMULATING…' : 'RUN WHAT-IF'}
          </button>
        </form>

        <section className="sim-panel result-panel" aria-live="polite">
          <div className="panel-head">
            <div>
              <span>COMPARISON</span>
              <h2>Actual vs simulated</h2>
            </div>
            <small>Baseline WP vs forked WP</small>
          </div>

          {error && <p className="sim-error">{error}</p>}
          {!error && !result && <p className="sim-empty">Set a chase, fork one fact, then run. Results land here.</p>}
          {result && <ResultView result={result} />}
        </section>
      </section>

      <p className="disclaimer">{result?.disclaimer || 'Simulation only — phase-rate Monte Carlo beside Chase Engine. Not for betting.'}</p>
      <style>{styles}</style>
    </main>
  );
}

function ResultView({ result }) {
  const base = result.baseline?.win_probability;
  const sim = result.simulated?.win_probability;
  const cmp = result.comparison || {};
  const baseState = result.baseline?.state || {};
  const simState = result.simulated?.state || {};
  const delta = cmp.batting_wp_delta_pp;

  return (
    <div className="result-body">
      <p className="result-headline">{cmp.headline}</p>
      <div className="wp-pair">
        <WpCard title="Baseline" pct={pct(base)} label={base?.label} state={baseState} />
        <div className={`delta-pill ${delta > 0 ? 'up' : delta < 0 ? 'down' : ''}`}>
          <span>DELTA</span>
          <strong>{delta > 0 ? '+' : ''}{delta ?? '—'} pp</strong>
        </div>
        <WpCard title="Simulated fork" pct={pct(sim)} label={sim?.label} state={simState} />
      </div>
      {result.actual && (
        <div className="actual-block">
          <span>HISTORICAL ACTUAL</span>
          <strong>
            {result.actual.batting_team || 'Chase'} finished {result.actual.final_runs}/{result.actual.final_wickets}
            {result.actual.chase_won ? ' — chase won' : ' — chase lost'}
          </strong>
        </div>
      )}
      {!!result.batting_order?.length && (
        <p className="order-line">Order: {result.batting_order.join(' → ')}</p>
      )}
    </div>
  );
}

function WpCard({ title, pct: percent, label, state }) {
  return (
    <div className="wp-card">
      <span>{title}</span>
      <strong>{percent}<em>%</em></strong>
      <small>{label || 'WP'}</small>
      <p>{state.runs}/{state.wickets} · need {state.runs_required} off {state.legal_balls_remaining} balls</p>
    </div>
  );
}

function pct(wp) {
  if (!wp || wp.batting_wp == null) return '—';
  return Math.round(Number(wp.batting_wp) * 100);
}

const styles = `
  .what-if { margin-top: 18px; color: var(--crease-white); }
  .sim-header { padding: 26px 28px 22px; border: 1px solid rgba(240,242,245,.1); border-radius: 8px; background: radial-gradient(circle at 88% 0%, rgba(232,0,58,.2), transparent 36%), linear-gradient(110deg, #171018, #0d0f14 70%); }
  .sim-kicker { margin: 0; color: #ff547c; font: 700 10px 'JetBrains Mono', monospace; letter-spacing: .11em; }
  .sim-kicker i { display: inline-block; width: 7px; height: 7px; margin-right: 7px; border-radius: 50%; background: var(--blood-red); box-shadow: 0 0 10px rgba(232,0,58,.7); animation: livePulse 1.8s ease-in-out infinite; }
  .sim-kicker span { color: rgba(240,242,245,.35); padding: 0 6px; }
  .sim-header h1 { margin: 8px 0 6px; color: #fff; font: 48px/1 'Bebas Neue', sans-serif; letter-spacing: .04em; }
  .sim-sub { max-width: 560px; margin: 0; color: rgba(240,242,245,.62); font-size: 13px; line-height: 1.5; }

  .preset-rail { display: flex; gap: 10px; overflow-x: auto; margin-top: 14px; }
  .preset { min-width: 200px; flex: 1; padding: 13px; text-align: left; border: 1px solid rgba(240,242,245,.11); border-radius: 5px; background: #15151b; color: #fff; cursor: pointer; }
  .preset.active { border-color: rgba(232,0,58,.7); background: linear-gradient(135deg, rgba(232,0,58,.15), #15151b); box-shadow: inset 3px 0 var(--blood-red); }
  .preset span { display: block; color: #ff6689; font: 700 9px 'JetBrains Mono', monospace; letter-spacing: .08em; }
  .preset strong { display: block; margin: 8px 0 4px; font-size: 13px; }
  .preset small { color: rgba(240,242,245,.43); font: 10px/1.35 'Inter', sans-serif; }

  .sim-grid { display: grid; grid-template-columns: 1.05fr .95fr; gap: 12px; margin-top: 14px; }
  .sim-panel { padding: 22px 22px 20px; border: 1px solid rgba(240,242,245,.1); border-radius: 8px; background: #101116; }
  .panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: end; margin-bottom: 14px; }
  .fork-head { margin-top: 18px; }
  .panel-head span { color: var(--bail-amber); font: 700 10px 'JetBrains Mono', monospace; letter-spacing: .1em; }
  .panel-head h2 { margin: 4px 0 0; color: #fff; font: 26px/1 'Bebas Neue', sans-serif; letter-spacing: .035em; }
  .panel-head small { max-width: 200px; color: rgba(240,242,245,.4); font: 10px 'Inter', sans-serif; text-align: right; }

  .field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .xi-grid { grid-template-columns: 1fr; }
  label { display: grid; gap: 6px; }
  label span { color: rgba(240,242,245,.45); font: 700 9px 'JetBrains Mono', monospace; letter-spacing: .06em; }
  input, select, textarea { width: 100%; padding: 10px 11px; border: 1px solid rgba(240,242,245,.12); border-radius: 4px; background: rgba(0,0,0,.28); color: #fff; font: 13px 'Inter', sans-serif; }
  textarea { resize: vertical; font: 12px 'JetBrains Mono', monospace; }
  .run-btn { width: 100%; margin-top: 18px; padding: 14px; border: 0; border-radius: 4px; background: var(--blood-red); color: #fff; cursor: pointer; font: 700 12px 'JetBrains Mono', monospace; letter-spacing: .08em; }
  .run-btn:disabled { opacity: .55; cursor: wait; }
  .run-btn:hover:not(:disabled) { filter: brightness(1.08); }

  .sim-empty, .sim-error { margin: 8px 0 0; color: rgba(240,242,245,.5); font-size: 13px; line-height: 1.45; }
  .sim-error { color: #ff94a7; }
  .result-headline { margin: 0 0 14px; color: #fff; font: 600 15px/1.35 'Inter', sans-serif; }
  .wp-pair { display: grid; grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: center; }
  .wp-card { padding: 14px; border: 1px solid rgba(240,242,245,.08); border-radius: 5px; background: rgba(0,0,0,.2); }
  .wp-card span { color: rgba(240,242,245,.45); font: 700 9px 'JetBrains Mono', monospace; letter-spacing: .08em; }
  .wp-card strong { display: block; margin-top: 6px; color: #fff; font: 42px/1 'Bebas Neue', sans-serif; }
  .wp-card strong em { font-style: normal; color: rgba(240,242,245,.45); font-size: 22px; margin-left: 2px; }
  .wp-card small { color: var(--bail-amber); font: 700 10px 'JetBrains Mono', monospace; }
  .wp-card p { margin: 8px 0 0; color: rgba(240,242,245,.5); font: 11px 'JetBrains Mono', monospace; }
  .delta-pill { display: grid; place-items: center; min-width: 78px; padding: 10px 8px; border: 1px solid rgba(240,242,245,.12); border-radius: 5px; background: rgba(0,0,0,.25); text-align: center; }
  .delta-pill span { color: rgba(240,242,245,.4); font: 700 8px 'JetBrains Mono', monospace; }
  .delta-pill strong { margin-top: 4px; color: #fff; font: 700 14px 'JetBrains Mono', monospace; }
  .delta-pill.up strong { color: #6cdaa0; }
  .delta-pill.down strong { color: #ff94a7; }
  .actual-block { margin-top: 14px; padding: 12px; border: 1px solid rgba(245,166,35,.28); border-radius: 5px; background: rgba(245,166,35,.06); }
  .actual-block span { display: block; color: var(--bail-amber); font: 700 9px 'JetBrains Mono', monospace; letter-spacing: .08em; }
  .actual-block strong { display: block; margin-top: 5px; color: #fff; font: 600 13px 'Inter', sans-serif; }
  .order-line { margin: 12px 0 0; color: rgba(240,242,245,.5); font: 11px 'JetBrains Mono', monospace; }
  .disclaimer { margin: 16px 2px 8px; color: rgba(240,242,245,.38); font: 11px/1.45 'Inter', sans-serif; }

  @media (max-width: 820px) {
    .sim-grid, .wp-pair, .field-grid { grid-template-columns: 1fr; }
    .delta-pill { justify-self: stretch; }
    .panel-head small { display: none; }
    .sim-header h1 { font-size: 40px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .sim-kicker i { animation: none; box-shadow: none; }
  }
`;
