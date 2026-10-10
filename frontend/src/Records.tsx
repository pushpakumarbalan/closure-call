import { useEffect, useState } from 'react'
import { api, fmtTime, POSTURE_LABEL, type DecisionRecord, type DecisionRecordSummary } from './api'
import { Inputs, NotificationView, PostureBadge, RecommendationView } from './Panels'

export default function Records() {
  const [list, setList] = useState<DecisionRecordSummary[]>([])
  const [sel, setSel] = useState<DecisionRecord | null>(null)
  const [verify, setVerify] = useState<any>(null)
  const [tab, setTab] = useState<'known' | 'decided' | 'notified'>('known')

  useEffect(() => { api.records().then(setList); api.verify().then(setVerify) }, [])
  useEffect(() => { if (list.length && !sel) api.record(list[0].id).then(setSel) }, [list])

  return (
    <div className="layout records">
      <div className="col">
        <div className="section">
          <h3>Decision record · append-only</h3>
          {verify && <div className={`chip ${verify.ok ? 'ok' : 'warn'}`}>{verify.ok ? `hash chain intact · ${verify.count} records` : `CHAIN BROKEN at seq ${verify.first_break_seq}`}</div>}
          {verify?.head && <div className="hash" style={{ marginTop: 6 }}>head {verify.head}</div>}
        </div>
        <div className="section">
          {list.length === 0 && <div className="empty">No decisions recorded yet.</div>}
          {list.map(r => (
            <div key={r.id} className={`fac ${sel?.id === r.id ? 'active' : ''}`} onClick={() => api.record(r.id).then(setSel)}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="mono muted">#{r.seq} · {fmtTime(r.created_at)}</span>
                {r.override ? <span className="chip warn">override</span> : <span className="chip ok">as recommended</span>}
              </div>
              <div className="name" style={{ marginTop: 4 }}>{r.facility_name}</div>
              <div className="meta">decided <PostureBadge p={r.decided_posture} /> by {r.decided_by}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="col">
        {!sel ? <div className="empty">Select a record to replay it.</div> : (
          <>
            <div className="section">
              <h2>Replay: {sel.facility_name}</h2>
              <div className="row small muted">
                <span>record <code>{sel.id}</code></span><span>· created {fmtTime(sel.created_at)}</span><span>· seq #{sel.seq}</span>
              </div>
              <div className="hash" style={{ marginTop: 6 }}>hash {sel.hash}<br />prev {sel.prev_hash || '(genesis)'}</div>
              <div className="steps" style={{ marginTop: 12 }}>
                <div className={tab === 'known' ? 'on' : ''} onClick={() => setTab('known')} style={{ cursor: 'pointer' }}>1 · What was known</div>
                <div className={tab === 'decided' ? 'on' : ''} onClick={() => setTab('decided')} style={{ cursor: 'pointer' }}>2 · What was recommended & decided</div>
                <div className={tab === 'notified' ? 'on' : ''} onClick={() => setTab('notified')} style={{ cursor: 'pointer' }}>3 · Who was told</div>
              </div>
            </div>
            {tab === 'known' && (
              <div className="section">
                <h3>Inputs available at {fmtTime(sel.recommendation.evaluated_at)} ({sel.recommendation.inputs.length})</h3>
                <Inputs inputs={sel.recommendation.inputs} />
              </div>
            )}
            {tab === 'decided' && (
              <>
                <div className="section">
                  <div className="grid2">
                    <div className="card"><div className="small muted">System recommended</div><div style={{ marginTop: 6 }}><PostureBadge p={sel.recommended_posture} big /></div></div>
                    <div className="card"><div className="small muted">{sel.decided_by} decided</div><div style={{ marginTop: 6 }}><PostureBadge p={sel.decided_posture} big /></div>
                      {sel.override && <div className="small" style={{ marginTop: 8, color: 'var(--warn)' }}>Override reason: {sel.override_reason}</div>}</div>
                  </div>
                </div>
                <RecommendationView rec={sel.recommendation} />
              </>
            )}
            {tab === 'notified' && (sel.notification ? <NotificationView pkg={sel.notification} /> : <div className="empty">No notification stored with this record.</div>)}
          </>
        )}
      </div>
    </div>
  )
}

export function Thresholds() {
  const [t, setT] = useState<any>(null)
  useEffect(() => { api.thresholds().then(setT) }, [])
  if (!t) return <div className="empty">Loading…</div>
  return (
    <div className="page">
      <h2>Show your work: where every cutoff came from</h2>
      <p className="muted">The engine is rule-based and reproducible. Each rule cites its anchor: NWS product criteria and CAP fields, NOAA NWPS flood categories, EPA AQI breakpoints, and the OPM operating-status ladder. The agent may argue with the engine, but the record always keeps both.</p>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>OPM operating-status ladder</h3>
        <table className="t"><tbody>{t.opm_ladder.map((l: any) => <tr key={l.posture}><td><PostureBadge p={l.posture} /></td><td><b>{l.label}</b></td><td className="muted">{l.meaning}</td></tr>)}</tbody></table>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>NWS alert products → posture</h3>
        <table className="t">
          <thead><tr><th>Product</th><th>Hazard</th><th>Pre-opening</th><th>In hours</th><th>Anchor</th></tr></thead>
          <tbody>{t.alert_rules.map((r: any) => <tr key={r.event}><td><b>{r.event}</b></td><td className="muted">{r.hazard}</td><td><PostureBadge p={r.pre_open} /></td><td><PostureBadge p={r.in_hours} /></td><td className="muted small">{r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.anchor}</a> : r.anchor}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Measured conditions → posture</h3>
        <table className="t">
          <thead><tr><th>Rule</th><th>Signal</th><th>Threshold</th><th>Pre-opening</th><th>In hours</th><th>Anchor</th></tr></thead>
          <tbody>{t.numeric_rules.map((r: any) => <tr key={r.id}><td><b>{r.desc}</b></td><td className="mono">{r.signal}{r.value_path ? `.${r.value_path}` : ''}</td><td className="mono">{r.op} {r.threshold}</td><td><PostureBadge p={r.pre_open} /></td><td><PostureBadge p={r.in_hours} /></td><td className="muted small">{r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.anchor}</a> : r.anchor}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="muted small" style={{ marginTop: 16 }}>Posture labels: {Object.entries(POSTURE_LABEL).map(([k, v]) => `${k} = ${v}`).join(' · ')}</p>
    </div>
  )
}
