export type Posture = 'normal' | 'delay' | 'early_dismissal' | 'telework' | 'closure'

export const POSTURE_LABEL: Record<Posture, string> = {
  normal: 'Open - Normal Operations',
  delay: 'Open - Delayed Arrival',
  early_dismissal: 'Open - Early Dismissal',
  telework: 'Closed to Public - Unscheduled Telework',
  closure: 'Facility Closed',
}
export const POSTURE_ORDER: Posture[] = ['normal', 'delay', 'early_dismissal', 'telework', 'closure']

export interface Signal {
  key: string; label: string; value: any; unit?: string | null; display: string
  source: string; source_url?: string | null; observed_at?: string | null; fetched_at: string; detail: Record<string, any>
}
export interface ThresholdHit {
  rule_id: string; hazard: string; signal_key: string; description: string; operator: string
  threshold: any; observed: any; margin_text: string; posture: Posture; anchor: string; anchor_url?: string | null
}
export interface Recommendation {
  facility_id: string; facility_name: string; evaluated_at: string; posture: Posture; posture_label: string
  hazards: string[]; inputs: Signal[]; triggered: ThresholdHit[]; near_misses: ThresholdHit[]
  confidence: number; confidence_reasons: string[]; what_would_change: string[]
  rationale: string; rationale_source: 'agent' | 'deterministic'; agent_trace: any[]; drill: boolean; drill_note?: string | null
}
export interface Recipient { employee_id: string; name: string; role: string; included: boolean; reason: string; channels: string[]; instruction: string }
export interface NotificationPackage {
  posture: Posture; subject: string; message: string; sms: string; recipients: Recipient[]
  included_count: number; excluded_count: number; channel_summary: Record<string, number>; generated_at: string
}
export interface Facility {
  id: string; name: string; agency: string; type: string; address: string; state: string; lat: number; lon: number
  timezone: string; hours: { open: string; close: string; days: string[] }; river_gauges: string[]
  hazard_profile: string[]; notes: string; primary: boolean
  roster: { total: number; essential: number; telework_eligible: number; onsite_today: number; telework_today: number; on_detail: number; leave: number; accessibility_needs: number }
  phase?: string; local_time?: string
}
export interface AlertProps {
  id: string; event: string; hazard_family: string; headline: string; severity: string; certainty: string; urgency: string
  severity_rank: number; area: string; sender: string; sent: string; onset: string; ends: string; expires: string; url: string; has_geometry: boolean
  affected_zones: string[]
}
export interface DecisionRecordSummary {
  seq: number; id: string; created_at: string; facility_id: string; facility_name: string; recommended_posture: Posture
  decided_posture: Posture; decided_by: string; override: number; override_reason?: string | null; prev_hash?: string | null; hash: string
}
export interface DecisionRecord extends Omit<DecisionRecordSummary, 'override'> {
  override: boolean; recommendation: Recommendation; notification?: NotificationPackage | null
}

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { headers: { 'content-type': 'application/json' }, ...init })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  health: () => j<any>('/api/health'),
  facilities: () => j<Facility[]>('/api/facilities'),
  facility: (id: string) => j<Facility>(`/api/facilities/${id}`),
  roster: (id: string) => j<any[]>(`/api/facilities/${id}/roster`),
  nationalAlerts: () => j<any>('/api/alerts/national'),
  thresholds: () => j<any>('/api/thresholds'),
  zoneCentroid: (url: string) => j<{ lat: number; lon: number; zone: string }>(`/api/zones/centroid?url=${encodeURIComponent(url)}`),
  notify: (recommendation: Recommendation, decided_posture?: Posture) =>
    j<NotificationPackage>('/api/notify', { method: 'POST', body: JSON.stringify({ recommendation, decided_posture }) }),
  decide: (body: { recommendation: Recommendation; decided_posture: Posture; decided_by: string; override_reason?: string | null; notification?: NotificationPackage | null }) =>
    j<DecisionRecord>('/api/decide', { method: 'POST', body: JSON.stringify(body) }),
  records: (facility_id?: string) => j<DecisionRecordSummary[]>(`/api/records${facility_id ? `?facility_id=${facility_id}` : ''}`),
  record: (id: string) => j<DecisionRecord>(`/api/records/${id}`),
  verify: () => j<{ ok: boolean; count: number; head?: string; first_break_seq?: number }>('/api/records/verify'),
}

export type StreamEvent =
  | { type: 'evidence'; phase: string; local_time: string; inputs: Signal[]; engine_posture: Posture; alerts: AlertProps[] }
  | { type: 'status'; message: string }
  | { type: 'tool'; name: string }
  | { type: 'text'; delta: string }
  | { type: 'result'; recommendation: Recommendation }

export async function evaluateStream(
  body: { facility_id: string; lat?: number; lon?: number; drill_note?: string },
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
) {
  const r = await fetch('/api/evaluate/stream', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal })
  if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`)
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2)
      const line = chunk.split('\n').find(l => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)))
    }
  }
}

export function fmtTime(iso?: string | null) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
