import { useCallback, useEffect, useRef, useState } from 'react'
import { api, evaluateStream, POSTURE_LABEL, POSTURE_ORDER, type AlertProps, type DecisionRecord, type Facility, type NotificationPackage, type Posture, type Recommendation, type Signal } from './api'
import MapView from './MapView'
import { AgentTrace, AlertFeed, FacilityDetail, FacilityList, NotificationView, PostureBadge, RecommendationView, placeName } from './Panels'
import Records, { Thresholds } from './Records'

type View = 'ops' | 'records' | 'thresholds'
type Drill = { lat: number; lon: number; label: string } | null

export default function App() {
  const [view, setView] = useState<View>('ops')
  const [pane, setPane] = useState<'map' | 'site' | 'decision'>('map')
  const [health, setHealth] = useState<any>(null)
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [facility, setFacility] = useState<Facility | null>(null)
  const [alerts, setAlerts] = useState<any | null>(null)
  const [showWms, setShowWms] = useState(true)
  const [focus, setFocus] = useState<[number, number] | null>(null)
  const [focusZoom, setFocusZoom] = useState(4)
  const [drill, setDrill] = useState<Drill>(null)

  // evaluation run state
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<string[]>([])
  const [tools, setTools] = useState<string[]>([])
  const [text, setText] = useState('')
  const [evidence, setEvidence] = useState<{ inputs: Signal[]; engine_posture: Posture; phase: string } | null>(null)
  const [rec, setRec] = useState<Recommendation | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // notify / decide
  const [pkg, setPkg] = useState<NotificationPackage | null>(null)
  const [decided, setDecided] = useState<Posture | null>(null)
  const [decidedBy, setDecidedBy] = useState('Facility Manager')
  const [overrideReason, setOverrideReason] = useState('')
  const [record, setRecord] = useState<DecisionRecord | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }))
    api.facilities().then(fs => { setFacilities(fs); const p = fs.find(f => f.primary) || fs[0]; if (p) setSelectedId(p.id) })
    const load = () => api.nationalAlerts().then(setAlerts).catch(() => {})
    load(); const t = setInterval(load, 120_000); return () => clearInterval(t)
  }, [])
  useEffect(() => { if (selectedId) api.facility(selectedId).then(setFacility) }, [selectedId])

  const resetRun = () => { setStatus([]); setTools([]); setText(''); setEvidence(null); setRec(null); setPkg(null); setDecided(null); setOverrideReason(''); setRecord(null); setErr(null) }
  const resetRef = useRef(resetRun)
  resetRef.current = resetRun
  const facilitiesRef = useRef(facilities)
  facilitiesRef.current = facilities

  const selectFacility = useCallback((id: string) => {
    setSelectedId(id); setDrill(null); resetRef.current()
    const f = facilitiesRef.current.find(x => x.id === id); if (f) { setFocus([f.lat, f.lon]); setFocusZoom(9) }
  }, [])

  const runEvaluation = useCallback(async (d: Drill) => {
    if (!selectedId) return
    resetRun(); setRunning(true); setPane('decision')
    const ac = new AbortController(); abortRef.current = ac
    try {
      await evaluateStream(
        { facility_id: selectedId, lat: d?.lat, lon: d?.lon, drill_note: d ? `Tabletop exercise: ${facility?.name ?? 'facility'} profile and roster evaluated against live conditions at ${d.label}.` : undefined },
        e => {
          if (ac.signal.aborted) return
          if (e.type === 'evidence') setEvidence({ inputs: e.inputs, engine_posture: e.engine_posture, phase: e.phase })
          else if (e.type === 'status') setStatus(s => [...s, e.message])
          else if (e.type === 'tool') setTools(t => [...t, e.name])
          else if (e.type === 'text') setText(t => t + e.delta)
          else if (e.type === 'result') setRec(e.recommendation)
        }, ac.signal)
    } catch (ex: any) {
      if (ex?.name === 'AbortError') { resetRef.current(); setDrill(null) }
      else setErr(String(ex.message || ex))
    }
    finally { setRunning(false) }
  }, [selectedId, facility])

  const pickAlert = async (a: AlertProps) => {
    let lat: number | undefined, lon: number | undefined
    const feat = alerts?.features.find((f: any) => f.properties.id === a.id)
    if (feat?.geometry) {
      const pts: number[][] = []; const walk = (c: any) => Array.isArray(c) && typeof c[0] === 'number' ? pts.push(c) : (c as any[]).forEach(walk); walk(feat.geometry.coordinates)
      lon = pts.reduce((s, p) => s + p[0], 0) / pts.length; lat = pts.reduce((s, p) => s + p[1], 0) / pts.length
    } else if (a.affected_zones?.length) {
      try { const c = await api.zoneCentroid(a.affected_zones[0]); lat = c.lat; lon = c.lon } catch { setErr('Could not locate that alert zone.'); return }
    }
    if (lat == null || lon == null) return
    const d = { lat, lon, label: `${a.event} - ${a.area.split(';')[0]}` }
    setDrill(d); setFocus([lat, lon]); setFocusZoom(8); runEvaluation(d)
  }

  const stopRun = () => { abortRef.current?.abort() }
  const runRef = useRef(runEvaluation)
  runRef.current = runEvaluation
  const onDrillFromMap = useCallback((lat: number, lon: number, label: string) => {
    const d = { lat, lon, label }; setDrill(d); runRef.current(d)
  }, [])

  const buildNotification = async (p?: Posture) => {
    if (!rec) return
    setErr(null)
    try { const n = await api.notify(rec, p ?? decided ?? rec.posture); setPkg(n) } catch (e: any) { setErr(e.message) }
  }
  const approve = async () => {
    if (!rec) return
    const p = decided ?? rec.posture
    const isOverride = p !== rec.posture
    if (isOverride && !overrideReason.trim()) { setErr('An override needs a reason; it goes in the record.'); return }
    setErr(null)
    try {
      const r = await api.decide({ recommendation: rec, decided_posture: p, decided_by: decidedBy, override_reason: isOverride ? overrideReason : null, notification: pkg })
      setRecord(r)
    } catch (e: any) { setErr(e.message) }
  }

  const step = record ? 4 : pkg ? 3 : rec ? 2 : 1

  return (
    <div className={`app pane-${pane}`}>
      <header className="topbar">
        <div className="brand">Closure Call</div>
        <nav className="nav">
          <button className={view === 'ops' ? 'active' : ''} onClick={() => setView('ops')}>Live</button>
          <button className={view === 'records' ? 'active' : ''} onClick={() => setView('records')}>Record</button>
          <button className={view === 'thresholds' ? 'active' : ''} onClick={() => setView('thresholds')}>Rules</button>
        </nav>
        <div className="right">
          <span className={`chip ${health?.llm_enabled ? 'ok' : 'warn'}`} title="National Weather Service data, Strands agent over MCP, Akamai hosted inference">
            {health?.llm_enabled ? 'Live data · agent on' : health ? 'Agent off' : 'Connecting'}
          </span>
        </div>
      </header>

      {view === 'records' && <Records />}
      {view === 'thresholds' && <Thresholds />}
      {view === 'ops' && (
        <div className="layout">
          <aside className={`col pane-site ${pane === 'site' ? 'on' : ''}`}>
            <FacilityList facilities={facilities} selectedId={selectedId} onSelect={selectFacility} />
            <AlertFeed alerts={alerts} onPick={pickAlert} busy={running} />
            {facility && <FacilityDetail f={facility} />}
          </aside>

          <main className={`mapcol pane-map ${pane === 'map' ? 'on' : ''}`}>
            <MapView facilities={facilities} selectedId={selectedId} onSelectFacility={selectFacility} alerts={alerts}
              onDrill={onDrillFromMap} drill={drill} focus={focus} focusZoom={focusZoom} showWms={showWms} visible={pane === 'map'} />
            <div className="map-overlay">
              {running ? (
                <button className="btn stop" onClick={stopRun}>Stop</button>
              ) : (
                <button className="btn primary" disabled={!selectedId} onClick={() => { setDrill(null); runEvaluation(null) }}>
                  Evaluate {facility ? placeName(facility.name) : 'site'}
                </button>
              )}
              {drill && !running && <button className="btn" onClick={() => runEvaluation(drill)}>Run again</button>}
              {drill && !running && <button className="btn ghost" onClick={() => { setDrill(null); resetRun() }}>Clear</button>}
              <button className="btn ghost sm" onClick={() => setShowWms(!showWms)}>{showWms ? 'Hide layer' : 'Show layer'}</button>
            </div>
            <ul className="map-legend" aria-label="Map colors">
              <li><i style={{ background: '#ff0000' }} />Tornado</li>
              <li><i style={{ background: '#ffff00' }} />Thunderstorm</li>
              <li><i style={{ background: '#397939' }} />Flash flood</li>
              <li><i style={{ background: '#0eeb0e' }} />Flood</li>
              <li><i style={{ background: '#eb69aa' }} />Winter</li>
              <li><i style={{ background: '#cb9d2a' }} />Wind</li>
              <li><i style={{ background: '#2c872c' }} />Coast</li>
              <li><i style={{ background: '#4cc2ff' }} />USDA facility</li>
            </ul>
          </main>

          <section className={`col pane-decision ${pane === 'decision' ? 'on' : ''}`}>
            <div className="section">
              <div className="steps" aria-label="Progress">
                <div className={step > 1 ? 'done' : step === 1 ? 'on' : ''}>Weather</div>
                <div className={step > 2 ? 'done' : step === 2 ? 'on' : ''}>Notice</div>
                <div className={step > 3 ? 'done' : step === 3 ? 'on' : ''}>Decision</div>
                <div className={step === 4 ? 'done' : ''}>Record</div>
              </div>
              {err && <div className="small" style={{ color: 'var(--danger)', marginBottom: 8 }}>{err}</div>}
              {!rec && !running && <p className="lead">Pick a building, then evaluate it. Or choose a storm on the left to test that warning against this staff.</p>}
              {(running || tools.length > 0 || status.length > 0) && (
                <>
                  <h3>Agent run{evidence && <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}> · {evidence.inputs.length} inputs gathered{running ? '' : <> · <PostureBadge p={evidence.engine_posture} /></>}</span>}</h3>
                  <AgentTrace tools={tools} text={text} status={status} running={running} />
                </>
              )}
            </div>

            {rec && <RecommendationView rec={rec} />}

            {rec && (
              <div className="section">
                <h3>Human decision</h3>
                <div className="row" style={{ marginBottom: 8 }}>
                  <select className="grow" value={decided ?? rec.posture} onChange={e => { const p = e.target.value as Posture; setDecided(p); if (pkg) buildNotification(p) }}>
                    {POSTURE_ORDER.map(p => <option key={p} value={p}>{POSTURE_LABEL[p]}{p === rec.posture ? ' (recommended)' : ''}</option>)}
                  </select>
                  <input className="grow" value={decidedBy} onChange={e => setDecidedBy(e.target.value)} placeholder="Decided by" />
                </div>
                {(decided ?? rec.posture) !== rec.posture && (
                  <textarea rows={2} placeholder="Override reason (required; goes in the record)" value={overrideReason} onChange={e => setOverrideReason(e.target.value)} style={{ marginBottom: 8 }} />
                )}
                <div className="row">
                  {!pkg && <button className="btn primary" onClick={() => buildNotification()}>Build notification</button>}
                  {pkg && !record && <button className="btn danger" onClick={approve}>Approve & send · record decision</button>}
                  {record && <span className="chip ok">Recorded #{record.seq} · {record.id} · hash {record.hash.slice(0, 12)}…</span>}
                  {record && <button className="btn sm" onClick={() => setView('records')}>Open record</button>}
                </div>
              </div>
            )}

            {pkg && <NotificationView pkg={pkg} />}
          </section>
        </div>
      )}
      {view === 'ops' && (
        <nav className="phone-nav">
          <button className={pane === 'map' ? 'on' : ''} onClick={() => setPane('map')}>Map</button>
          <button className={pane === 'site' ? 'on' : ''} onClick={() => setPane('site')}>Buildings</button>
          <button className={pane === 'decision' ? 'on' : ''} onClick={() => setPane('decision')}>{running ? 'Running…' : 'Result'}</button>
        </nav>
      )}
    </div>
  )
}
