import { useCallback, useEffect, useRef, useState } from 'react'
import { api, evaluateStream, POSTURE_LABEL, POSTURE_ORDER, type AlertProps, type DecisionRecord, type Facility, type NotificationPackage, type Posture, type Recommendation, type Signal } from './api'
import MapView from './MapView'
import { AgentTrace, AlertFeed, FacilityDetail, FacilityList, NotificationView, PostureBadge, RecommendationView } from './Panels'
import Records, { Thresholds } from './Records'

type View = 'ops' | 'records' | 'thresholds'
type Drill = { lat: number; lon: number; label: string } | null

export default function App() {
  const [view, setView] = useState<View>('ops')
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

  const selectFacility = (id: string) => {
    setSelectedId(id); setDrill(null); resetRun()
    const f = facilities.find(x => x.id === id); if (f) { setFocus([f.lat, f.lon]); setFocusZoom(9) }
  }

  const runEvaluation = useCallback(async (d: Drill) => {
    if (!selectedId) return
    resetRun(); setRunning(true)
    const ac = new AbortController(); abortRef.current = ac
    try {
      await evaluateStream(
        { facility_id: selectedId, lat: d?.lat, lon: d?.lon, drill_note: d ? `Tabletop exercise: ${facility?.name ?? 'facility'} profile and roster evaluated against live conditions at ${d.label}.` : undefined },
        e => {
          if (e.type === 'evidence') setEvidence({ inputs: e.inputs, engine_posture: e.engine_posture, phase: e.phase })
          else if (e.type === 'status') setStatus(s => [...s, e.message])
          else if (e.type === 'tool') setTools(t => [...t, e.name])
          else if (e.type === 'text') setText(t => t + e.delta)
          else if (e.type === 'result') setRec(e.recommendation)
        }, ac.signal)
    } catch (ex: any) { if (ex.name !== 'AbortError') setErr(String(ex.message || ex)) }
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

  const onDrillFromMap = (lat: number, lon: number, label: string) => { const d = { lat, lon, label }; setDrill(d); runEvaluation(d) }

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
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="dot" />Closure Call</div>
        <nav className="nav">
          <button className={view === 'ops' ? 'active' : ''} onClick={() => setView('ops')}>Operations</button>
          <button className={view === 'records' ? 'active' : ''} onClick={() => setView('records')}>Decision record</button>
          <button className={view === 'thresholds' ? 'active' : ''} onClick={() => setView('thresholds')}>Thresholds</button>
        </nav>
        <div className="right">
          <span className="chip">NWS api.weather.gov · live</span>
          <span className="chip">Strands Agents SDK</span>
          {health && <span className={`chip ${health.llm_enabled ? 'ok' : 'warn'}`}>{health.llm_enabled ? `Akamai Cloud inference · ${health.llm_model}` : 'LLM off · deterministic'}</span>}
        </div>
      </header>

      {view === 'records' && <Records />}
      {view === 'thresholds' && <Thresholds />}
      {view === 'ops' && (
        <div className="layout">
          <aside className="col">
            <FacilityList facilities={facilities} selectedId={selectedId} onSelect={selectFacility} />
            {facility && <FacilityDetail f={facility} />}
            <AlertFeed alerts={alerts} onPick={pickAlert} busy={running} />
          </aside>

          <main className="mapcol">
            <MapView facilities={facilities} selectedId={selectedId} onSelectFacility={selectFacility} alerts={alerts}
              onDrill={onDrillFromMap} drill={drill} focus={focus} focusZoom={focusZoom} showWms={showWms} />
            <div className="map-overlay">
              <button className="btn primary" disabled={!selectedId || running} onClick={() => { setDrill(null); runEvaluation(null) }}>
                {running && !drill ? 'Evaluating…' : 'Evaluate facility now'}
              </button>
              {drill && <button className="btn" disabled={running} onClick={() => runEvaluation(drill)}>Re-run exercise</button>}
              {drill && <button className="btn ghost" disabled={running} onClick={() => { setDrill(null); resetRun() }}>Clear exercise</button>}
              <button className="btn ghost sm" onClick={() => setShowWms(!showWms)}>{showWms ? 'Hide' : 'Show'} NWS WWA layer</button>
            </div>
            <div className="map-legend"><b>Map:</b> NWS watches/warnings/advisories (WMS) · outlined polygons = warning-tier alerts from api.weather.gov (click to exercise) · blue = facilities</div>
          </main>

          <section className="col">
            <div className="section">
              <div className="steps">
                <div className={step > 1 ? 'done' : step === 1 ? 'on' : ''}>1 Evaluate</div>
                <div className={step > 2 ? 'done' : step === 2 ? 'on' : ''}>2 Notify</div>
                <div className={step > 3 ? 'done' : step === 3 ? 'on' : ''}>3 Decide</div>
                <div className={step === 4 ? 'done' : ''}>4 Recorded</div>
              </div>
              {err && <div className="small" style={{ color: 'var(--danger)', marginBottom: 8 }}>{err}</div>}
              {!rec && !running && <div className="muted small">Pick a facility and press <b>Evaluate facility now</b>, or click a live warning on the map / in the feed to run a tabletop exercise against real conditions.</div>}
              {(running || tools.length > 0 || status.length > 0) && (
                <>
                  <h3>Agent run{evidence && <span className="muted" style={{ textTransform: 'none', letterSpacing: 0 }}> · {evidence.inputs.length} inputs gathered · engine says <PostureBadge p={evidence.engine_posture} /></span>}</h3>
                  <AgentTrace tools={tools} text={text} status={status} running={running} />
                </>
              )}
            </div>

            {rec && <RecommendationView rec={rec} />}

            {rec && (
              <div className="section">
                <h3>Human decision</h3>
                <div className="row" style={{ marginBottom: 8 }}>
                  <select value={decided ?? rec.posture} onChange={e => { const p = e.target.value as Posture; setDecided(p); if (pkg) buildNotification(p) }} style={{ width: 'auto' }}>
                    {POSTURE_ORDER.map(p => <option key={p} value={p}>{POSTURE_LABEL[p]}{p === rec.posture ? ' (recommended)' : ''}</option>)}
                  </select>
                  <input value={decidedBy} onChange={e => setDecidedBy(e.target.value)} style={{ width: 200 }} placeholder="Decided by" />
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
    </div>
  )
}
