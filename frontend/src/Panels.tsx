import { useState } from 'react'
import { POSTURE_LABEL, POSTURE_ORDER, fmtTime, type AlertProps, type Facility, type NotificationPackage, type Posture, type Recommendation, type Signal, type ThresholdHit } from './api'

export function PostureBadge({ p, big }: { p: Posture; big?: boolean }) {
  return big ? <div className={`posture ${p}`}>{POSTURE_LABEL[p]}</div> : <span className={`ptag ${p}`}>{POSTURE_LABEL[p]}</span>
}

export function Ladder({ p }: { p: Posture }) {
  const idx = POSTURE_ORDER.indexOf(p)
  return <div className="ladder">{POSTURE_ORDER.map((q, i) => <div key={q} className={i <= idx ? `on ${p}` : ''} title={POSTURE_LABEL[q]} />)}</div>
}

export function FacilityList({ facilities, selectedId, onSelect }: { facilities: Facility[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="section">
      <h3>Facilities</h3>
      {facilities.map(f => (
        <div key={f.id} className={`fac ${selectedId === f.id ? 'active' : ''}`} onClick={() => onSelect(f.id)}>
          <div className="name">{f.name}</div>
          <div className="meta">{f.type} · {f.agency} · {f.roster.total} staff ({f.roster.essential} essential)</div>
        </div>
      ))}
    </div>
  )
}

export function FacilityDetail({ f }: { f: Facility }) {
  return (
    <div className="section">
      <h3>Facility profile</h3>
      <dl className="kv">
        <dt>Address</dt><dd>{f.address}</dd>
        <dt>Hours</dt><dd>{f.hours.open}-{f.hours.close} {f.hours.days.join('/')} ({f.timezone.split('/')[1]?.replace('_', ' ')})</dd>
        <dt>Local time</dt><dd>{f.local_time ? fmtTime(f.local_time) : '-'} · <span className="chip">{f.phase === 'in_hours' ? 'in hours' : 'pre-opening decision'}</span></dd>
        <dt>Hazards</dt><dd>{f.hazard_profile.join(', ')}</dd>
        <dt>Gauges</dt><dd className="mono">{f.river_gauges.join(', ') || 'none'}</dd>
        <dt>Roster</dt><dd>{f.roster.onsite_today} onsite · {f.roster.telework_today} telework · {f.roster.on_detail} on detail · {f.roster.leave} leave · {f.roster.accessibility_needs} accessibility</dd>
        <dt>Notes</dt><dd className="muted">{f.notes}</dd>
      </dl>
    </div>
  )
}

export function AlertFeed({ alerts, onPick, busy }: { alerts: any | null; onPick: (a: AlertProps) => void; busy: boolean }) {
  const [filter, setFilter] = useState<'warnings' | 'all'>('warnings')
  if (!alerts) return <div className="section"><h3>Live NWS alerts</h3><div className="muted small">Loading national feed…</div></div>
  let feats: AlertProps[] = alerts.features.map((f: any) => f.properties)
  if (filter === 'warnings') feats = feats.filter(a => a.severity_rank >= 3 || /Warning/.test(a.event))
  feats = feats.filter(a => !/Small Craft|Rip Current|Beach Hazards|Gale|Marine|Surf|Lake Wind|Hazardous Seas/.test(a.event))
  feats.sort((a, b) => b.severity_rank - a.severity_rank || a.event.localeCompare(b.event))
  const counts: Record<string, number> = {}
  feats.forEach(a => { counts[a.event] = (counts[a.event] || 0) + 1 })
  return (
    <div className="section">
      <h3>Live NWS alerts <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}>· {alerts.count} active nationally · {fmtTime(alerts.fetched_at)}</span></h3>
      <div className="row small" style={{ marginBottom: 8 }}>
        <button className={`btn sm ${filter === 'warnings' ? 'primary' : 'ghost'}`} onClick={() => setFilter('warnings')}>Warnings</button>
        <button className={`btn sm ${filter === 'all' ? 'primary' : 'ghost'}`} onClick={() => setFilter('all')}>All land</button>
        <span className="muted">Click one to run an exercise there.</span>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        {Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, v]) => <span key={k} className="chip">{k} <b>{v}</b></span>)}
      </div>
      <div style={{ maxHeight: 420, overflow: 'auto' }}>
        {feats.slice(0, 80).map(a => (
          <div key={a.id} className={`alert-item sev-${a.severity}`} onClick={() => !busy && onPick(a)} title={a.headline}>
            <div className="ev">{a.event} <span className="muted" style={{ fontWeight: 400 }}>· {a.severity}/{a.certainty}/{a.urgency}</span></div>
            <div className="area">{a.area}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function AgentTrace({ tools, text, status, running }: { tools: string[]; text: string; status: string[]; running: boolean }) {
  return (
    <div className="trace">
      {status.map((s, i) => <div key={'s' + i} className="status">» {s}</div>)}
      {tools.map((t, i) => <div key={'t' + i} className="tool">⚙ tool: {t}()</div>)}
      {text && <div style={{ marginTop: 6 }} className={running ? 'blink' : ''}>{text}</div>}
      {running && !text && <div className="status blink">thinking</div>}
    </div>
  )
}

function Hit({ h, near }: { h: ThresholdHit; near?: boolean }) {
  return (
    <div className={`hit ${near ? 'near' : ''}`}>
      <div className="row" style={{ justifyContent: 'space-between' }}><span className="d">{h.description}</span><PostureBadge p={h.posture} /></div>
      <div className="m">{h.signal_key} {h.operator} {String(h.threshold)} · observed {typeof h.observed === 'number' ? h.observed.toFixed(1) : String(h.observed)} · {h.margin_text}</div>
      <div className="a">Anchor: {h.anchor_url ? <a href={h.anchor_url} target="_blank" rel="noreferrer">{h.anchor}</a> : h.anchor}</div>
    </div>
  )
}

export function Inputs({ inputs }: { inputs: Signal[] }) {
  return (
    <table className="t">
      <thead><tr><th>Input</th><th>Source</th><th>Observed</th></tr></thead>
      <tbody>
        {inputs.map(s => (
          <tr key={s.key + s.display}>
            <td>{s.display}</td>
            <td className="muted">{s.source_url ? <a href={s.source_url} target="_blank" rel="noreferrer">{s.source}</a> : s.source}</td>
            <td className="muted mono">{fmtTime(s.observed_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function RecommendationView({ rec }: { rec: Recommendation }) {
  const [copied, setCopied] = useState(false)
  const [showInputs, setShowInputs] = useState(false)
  const risks = rec.agent_trace.find((t: any) => t.type === 'key_risks')?.items as string[] | undefined
  const checklist = rec.agent_trace.find((t: any) => t.type === 'manager_checklist')?.items as string[] | undefined
  const disagreement = rec.agent_trace.find((t: any) => t.type === 'disagreement')
  return (
    <>
      <div className="section">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <PostureBadge p={rec.posture} big />
          <div className="small muted" style={{ textAlign: 'right' }}>evaluated {fmtTime(rec.evaluated_at)}<br />{rec.drill ? <span className="chip warn">exercise</span> : <span className="chip ok">live facility</span>}</div>
        </div>
        <Ladder p={rec.posture} />
        <div className="row small muted" style={{ justifyContent: 'space-between' }}>
          <span>hazards: {rec.hazards.length ? rec.hazards.join(', ') : 'none active'}</span>
          <span>confidence {Math.round(rec.confidence * 100)}%</span>
        </div>
        <div className="conf" style={{ marginTop: 4 }}><div style={{ width: `${rec.confidence * 100}%` }} /></div>
        <ul className="list small muted" style={{ marginTop: 6 }}>{rec.confidence_reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
      </div>

      <div className="section">
        <h3>Rationale <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}>· {rec.rationale_source === 'agent' ? 'Strands agent on Akamai inference' : 'deterministic engine'}</span></h3>
        <div className="rationale">
          <button className="btn sm ghost copy" onClick={() => { navigator.clipboard.writeText(rec.rationale); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? 'copied' : 'copy'}</button>
          {rec.rationale}
        </div>
        {disagreement && <div className="small" style={{ marginTop: 8, color: 'var(--warn)' }}>Agent disagrees with engine: suggests <b>{POSTURE_LABEL[disagreement.agent_posture as Posture]}</b>. {disagreement.reason}</div>}
      </div>

      <div className="section">
        <h3>Thresholds crossed ({rec.triggered.length})</h3>
        {rec.triggered.length === 0 && <div className="muted small">No warning-tier product or measured condition crosses a threshold.</div>}
        {rec.triggered.map((h, i) => <Hit key={i} h={h} />)}
        {rec.near_misses.length > 0 && <>
          <h3 style={{ marginTop: 12 }}>Watching ({rec.near_misses.length})</h3>
          {rec.near_misses.map((h, i) => <Hit key={i} h={h} near />)}
        </>}
      </div>

      <div className="section">
        <h3>What would change this</h3>
        <ul className="list">{rec.what_would_change.map((w, i) => <li key={i}>{w}</li>)}</ul>
      </div>

      {(risks || checklist) && (
        <div className="section grid2">
          {risks && <div><h3>Key risks</h3><ul className="list">{risks.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
          {checklist && <div><h3>Manager checklist (next hour)</h3><ul className="list">{checklist.map((r, i) => <li key={i}>{r}</li>)}</ul></div>}
        </div>
      )}

      <div className="section">
        <h3 style={{ cursor: 'pointer' }} onClick={() => setShowInputs(!showInputs)}>Every input ({rec.inputs.length}) {showInputs ? '▾' : '▸'}</h3>
        {showInputs && <Inputs inputs={rec.inputs} />}
      </div>
    </>
  )
}

export function NotificationView({ pkg }: { pkg: NotificationPackage }) {
  const [tab, setTab] = useState<'recipients' | 'message'>('recipients')
  const [showExcluded, setShowExcluded] = useState(true)
  const list = pkg.recipients.filter(r => showExcluded || r.included)
  return (
    <div className="section">
      <h3>Notification package</h3>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="chip ok">{pkg.included_count} notified</span>
        <span className="chip">{pkg.excluded_count} excluded</span>
        {Object.entries(pkg.channel_summary).map(([c, n]) => <span key={c} className="chip">{c} <b>{n}</b></span>)}
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <button className={`btn sm ${tab === 'recipients' ? 'primary' : 'ghost'}`} onClick={() => setTab('recipients')}>Recipients & logic</button>
        <button className={`btn sm ${tab === 'message' ? 'primary' : 'ghost'}`} onClick={() => setTab('message')}>Message</button>
        {tab === 'recipients' && <label className="small muted" style={{ marginLeft: 'auto' }}><input type="checkbox" style={{ width: 'auto' }} checked={showExcluded} onChange={e => setShowExcluded(e.target.checked)} /> show excluded</label>}
      </div>
      {tab === 'recipients' ? (
        <table className="t">
          <thead><tr><th></th><th>Employee</th><th>Channels</th><th>Why</th></tr></thead>
          <tbody>
            {list.map(r => (
              <tr key={r.employee_id} className={r.included ? '' : 'excluded'}>
                <td>{r.included ? '✓' : '–'}</td>
                <td><b>{r.name}</b><br /><span className="muted">{r.role}</span></td>
                <td className="mono">{r.channels.join(', ') || '-'}</td>
                <td>{r.reason}{r.included && <div className="muted" style={{ marginTop: 2 }}>→ {r.instruction}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <div className="small muted">Subject</div><div className="pre" style={{ marginBottom: 8 }}>{pkg.subject}</div>
          <div className="small muted">SMS ({pkg.sms.length}/160)</div><div className="pre" style={{ marginBottom: 8 }}>{pkg.sms}</div>
          <div className="small muted">Email / Teams</div><div className="pre">{pkg.message}</div>
        </>
      )}
    </div>
  )
}
