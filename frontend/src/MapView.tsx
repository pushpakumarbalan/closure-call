import { memo, useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, WMSTileLayer, GeoJSON, CircleMarker, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import type { Facility } from './api'

const SEV_COLOR: Record<string, string> = { Extreme: '#ff5c5c', Severe: '#ff8a3d', Moderate: '#f5b84a', Minor: '#4cc2ff', Unknown: '#8b9bb0' }
const WMS_PARAMS = { layers: '0,1', format: 'image/png', transparent: true }

function alertStyle(feature: any) {
  return { color: SEV_COLOR[feature?.properties?.severity] || '#8b9bb0', weight: 1.5, fillOpacity: 0.25 }
}

function FlyTo({ center, zoom }: { center: [number, number] | null; zoom: number }) {
  const map = useMap()
  useEffect(() => { if (center) map.flyTo(center, zoom, { duration: 0.9 }) }, [center?.[0], center?.[1], zoom])
  return null
}

function Refit({ visible }: { visible: boolean }) {
  const map = useMap()
  useEffect(() => {
    if (!visible) return
    const id = window.setTimeout(() => map.invalidateSize(), 60)
    return () => window.clearTimeout(id)
  }, [visible, map])
  return null
}

function MapView(props: {
  facilities: Facility[]; selectedId: string | null; onSelectFacility: (id: string) => void
  alerts: any | null; onDrill: (lat: number, lon: number, label: string) => void
  drill: { lat: number; lon: number; label: string } | null; focus: [number, number] | null; focusZoom: number
  showWms: boolean; visible?: boolean
}) {
  const polygons = useMemo(() => {
    if (!props.alerts) return null
    const feats = props.alerts.features.filter((f: any) => f.geometry && f.properties.severity_rank >= 2)
    return { type: 'FeatureCollection', features: feats } as any
  }, [props.alerts])

  return (
    <MapContainer center={[39.5, -96]} zoom={4} zoomControl={false} preferCanvas>
      <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}" attribution="Esri, HERE, Garmin, OpenStreetMap" maxZoom={16} />
      <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}" maxZoom={16} opacity={0.8} />
      <WMSTileLayer
        url="https://mapservices.weather.noaa.gov/eventdriven/services/WWA/watch_warn_adv/MapServer/WMSServer"
        params={WMS_PARAMS as any}
        opacity={props.showWms ? 0.55 : 0}
        attribution="NWS Watches/Warnings/Advisories"
      />
      {polygons && (
        <GeoJSON
          key={props.alerts?.fetched_at}
          data={polygons}
          style={alertStyle}
          onEachFeature={(f: any, layer: L.Layer) => {
            const p = f.properties
            layer.bindTooltip(`<b>${p.event}</b><br/>${p.area}<br/><span style="color:#8b9bb0">${p.severity} / ${p.certainty} / ${p.urgency}</span>`, { sticky: true })
            layer.on('click', () => {
              const b = (layer as any).getBounds?.() as L.LatLngBounds | undefined
              if (b) { const c = b.getCenter(); props.onDrill(c.lat, c.lng, `${p.event} - ${p.area}`) }
            })
          }}
        />
      )}
      {props.facilities.map(f => (
        <CircleMarker key={f.id} center={[f.lat, f.lon]} radius={props.selectedId === f.id ? 10 : 7}
          pathOptions={{ color: props.selectedId === f.id ? '#4cc2ff' : '#e6edf3', fillColor: '#4cc2ff', fillOpacity: 0.9, weight: 2 }}
          eventHandlers={{ click: () => props.onSelectFacility(f.id) }}>
          <Tooltip direction="top" offset={[0, -8]}>{f.name}</Tooltip>
        </CircleMarker>
      ))}
      {props.drill && (
        <CircleMarker center={[props.drill.lat, props.drill.lon]} radius={12} pathOptions={{ color: '#ff5c5c', fillColor: '#ff5c5c', fillOpacity: 0.35, weight: 2, dashArray: '4 4' }}>
          <Tooltip permanent direction="right" offset={[12, 0]}>Exercise: {props.drill.label}</Tooltip>
        </CircleMarker>
      )}
      <FlyTo center={props.focus} zoom={props.focusZoom} />
      <Refit visible={props.visible !== false} />
    </MapContainer>
  )
}

export default memo(MapView)
