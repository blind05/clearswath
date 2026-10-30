// The map: USGS imagery, the demo's drone image, the plan's layers, a plain-word key, and drawing.
import type { Feature, FeatureCollection, Geometry, Polygon } from "geojson";
import type { StyleSpecification } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapGL, { Layer, NavigationControl, Source, type MapRef } from "react-map-gl/maplibre";
import { TerraDraw, TerraDrawPolygonMode, TerraDrawRectangleMode, TerraDrawSelectMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import * as stylex from "@stylexjs/stylex";
import { color } from "@/tokens.stylex";
import type { Overlay, Plan } from "@/types";

// The map's own controls sit over imagery, so they are the one place with a shadow (DESIGN.md).
const s = stylex.create({
  wrap: { position: "relative", width: "100%", height: "100%" },
  card: { position: "absolute", borderRadius: 4, backgroundColor: color.panel, boxShadow: "0 1px 4px rgba(30,43,36,.25)" },
  tools: { left: 12, top: 12, display: "flex", flexDirection: "column", gap: 4, padding: 4 },
  tool: {
    borderRadius: 3, paddingInline: 10, paddingBlock: 6, textAlign: "left", fontSize: 13, fontWeight: 500,
    font: "inherit", border: 0, cursor: "pointer", color: color.ink, backgroundColor: { default: "transparent", ":hover": color.page },
  },
  toolOn: { color: "#FFFFFF", backgroundColor: { default: color.ink, ":hover": color.ink } },
  key: { bottom: 32, right: 12, minWidth: 200, paddingInline: 12, paddingBlock: 8, fontSize: 13 },
  keyToggle: {
    display: "flex", width: "100%", justifyContent: "space-between", gap: 12, fontWeight: 600,
    font: "inherit", border: 0, padding: 0, background: "none", cursor: "pointer", color: color.ink,
  },
  hint: { fontWeight: 400, color: color.muted },
  keyList: { marginTop: 6, display: "grid", gap: 4, listStyle: "none", padding: 0 },
  keyRow: { display: "flex", alignItems: "center", gap: 8, cursor: "pointer" },
  tick: { accentColor: color.ink },
  swatch: { display: "inline-block", width: 14, height: 10, flex: "none" },
});

// USGS The National Map imagery: public domain; native tiles stop at zoom 16, MapLibre enlarges them beyond.
const BASEMAP: StyleSpecification = {
  version: 8,
  sources: {
    usgs: {
      type: "raster", tileSize: 256, maxzoom: 16, attribution: "USDA, USGS The National Map: Orthoimagery",
      tiles: ["https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"],
    },
  },
  layers: [{ id: "usgs", type: "raster", source: "usgs" }],
};

interface LayerSpec {
  key: string; name: string; fill?: string; fillOpacity?: number; line?: string; lineWidth?: number; dash?: number[];
  delay: number;  // the reveal: field and zones first, then hazards and buffers, then the weed cells
}

const LAYERS: LayerSpec[] = [
  { key: "spray_zone", name: "Can be sprayed", fill: "#2E7D32", fillOpacity: 0.08, line: "#2E7D32", lineWidth: 2, delay: 0 },
  { key: "no_spray", name: "No spray", fill: "#B42318", fillOpacity: 0.25, line: "#B42318", lineWidth: 1, delay: 350 },
  { key: "restricted", name: "Bulletin area", fill: "#6A1B9A", fillOpacity: 0.2, line: "#6A1B9A", lineWidth: 2, dash: [2, 2], delay: 350 },
  { key: "buffered_cells", name: "Weeds held back by a buffer", fill: "#37474F", fillOpacity: 0.6, delay: 700 },
  { key: "spray_cells", name: "Spot spray: weeds found", fill: "#C4127A", fillOpacity: 0.45, delay: 900 },
  { key: "water", name: "Water", fill: "#2B83BA", fillOpacity: 0.45, line: "#2B83BA", lineWidth: 2, delay: 350 },
  { key: "possible_water", name: "Possible water: check", fill: "#2B83BA", fillOpacity: 0.12, line: "#2B83BA", lineWidth: 2, dash: [2, 2], delay: 350 },
  { key: "building", name: "Buildings", fill: "#5B6760", fillOpacity: 0.5, line: "#5B6760", lineWidth: 1, delay: 350 },
  { key: "habitat", name: "Tree lines and woods", fill: "#558B2F", fillOpacity: 0.3, line: "#558B2F", lineWidth: 1, delay: 350 },
  { key: "field", name: "Field edge", line: "#FFFFFF", lineWidth: 3, delay: 0 },
];

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function asFeatures(data: FeatureCollection | Geometry): FeatureCollection {
  if (data.type === "FeatureCollection") return data;
  return { type: "FeatureCollection", features: [{ type: "Feature", geometry: data, properties: {} }] };
}

function bbox(data: FeatureCollection | Geometry): [number, number, number, number] | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      w = Math.min(w, c[0] as number); e = Math.max(e, c[0] as number);
      s = Math.min(s, c[1] as number); n = Math.max(n, c[1] as number);
    } else if (Array.isArray(c)) c.forEach(visit);
  };
  asFeatures(data).features.forEach((f) => f.geometry && "coordinates" in f.geometry && visit(f.geometry.coordinates));
  return Number.isFinite(w) ? [w, s, e, n] : null;
}

export type DrawTarget = "field" | "managed";
export interface Drawing { field: Feature<Polygon> | null; managed: Feature<Polygon>[] }

interface Props {
  plan: Plan | null;
  onDrawing: (d: Drawing) => void;
  clearDrawing: number;  // bump to clear everything drawn
}

export function MapView({ plan, onDrawing, clearDrawing }: Props) {
  const mapRef = useRef<MapRef>(null);
  const draw = useRef<TerraDraw | null>(null);
  const roles = useRef(new Map<string | number, DrawTarget>());
  const [target, setTarget] = useState<DrawTarget>("field");
  const [tool, setTool] = useState<"polygon" | "rectangle" | "select" | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [keyOpen, setKeyOpen] = useState(() => window.innerWidth >= 800);

  const present = useMemo(() => LAYERS.filter((l) => {
    const d = plan?.layers[l.key];
    return d && !(d.type === "FeatureCollection" && !d.features.length);
  }), [plan]);
  const overlay: Overlay | null | undefined = plan?.demo?.overlay;

  // A new plan: fit the field clear of the toolbar and the key, then run the one reveal.
  useEffect(() => {
    const map = mapRef.current;
    const field = plan?.layers.field;
    if (!map || !field) return;
    const b = bbox(field);
    const narrow = window.innerWidth < 800;
    if (b) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], {
      padding: narrow ? 20 : { top: 40, left: 150, bottom: 40, right: 260 }, duration: reducedMotion() ? 0 : 800,
    });
    setRevealed(false);
    const t = window.setTimeout(() => setRevealed(true), reducedMotion() ? 0 : 850);
    return () => window.clearTimeout(t);
  }, [plan]);

  const emit = useCallback(() => {
    const d = draw.current;
    if (!d) return;
    const polys = d.getSnapshot().filter((f) => f.geometry.type === "Polygon") as Feature<Polygon>[];
    const field = polys.filter((f) => roles.current.get(f.id as string) !== "managed").at(-1) ?? null;
    onDrawing({ field, managed: polys.filter((f) => roles.current.get(f.id as string) === "managed") });
  }, [onDrawing]);

  const onLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map || draw.current) return;
    (window as unknown as { __clearswathMap: unknown }).__clearswathMap = map;  // for the Playwright checks
    const td = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map }),
      modes: [
        new TerraDrawPolygonMode(), new TerraDrawRectangleMode(),
        new TerraDrawSelectMode({ flags: {
          polygon: { feature: { draggable: true, coordinates: { midpoints: true, draggable: true, deletable: true } } },
          rectangle: { feature: { draggable: true } },
        } }),
      ],
    });
    td.start();
    td.on("finish", (id) => {
      const role = targetRef.current;
      if (role === "field") {  // one field at a time: drawing again replaces it
        const old = td.getSnapshot().filter((f) => f.id !== id && roles.current.get(f.id as string) !== "managed");
        if (old.length) td.removeFeatures(old.map((f) => f.id as string));
      }
      roles.current.set(id, role);
      emit();
    });
    td.on("change", () => emit());
    draw.current = td;
  }, [emit]);

  const targetRef = useRef(target);
  useEffect(() => { targetRef.current = target; }, [target]);

  useEffect(() => {
    if (!draw.current) return;
    draw.current.setMode(tool ?? "static");
  }, [tool]);

  useEffect(() => {
    if (!clearDrawing || !draw.current) return;
    draw.current.clear();
    roles.current.clear();
    emit();
  }, [clearDrawing, emit]);

  const pick = (t: DrawTarget, mode: "polygon" | "rectangle") => {
    setTarget(t);
    setTool((cur) => (cur === mode && targetRef.current === t ? null : mode));
  };

  return (
    <div {...stylex.props(s.wrap)}>
      <MapGL ref={mapRef} onLoad={onLoad} mapStyle={BASEMAP} initialViewState={{ longitude: -101, latitude: 43, zoom: 3.6 }}
           maxZoom={21} style={{ width: "100%", height: "100%" }}
           attributionControl={{ compact: window.innerWidth < 800, customAttribution: overlay?.credit ?? undefined }}>
        {present.map((l) => {
          const data = asFeatures(plan!.layers[l.key]);
          const visibility = hidden[l.key] ? "none" : "visible";
          const t = { duration: reducedMotion() ? 0 : 500, delay: reducedMotion() ? 0 : l.delay };
          return (
            <Source key={`${plan!.run_id}-${l.key}`} id={l.key} type="geojson" data={data}>
              {l.fill && <Layer id={`${l.key}-fill`} type="fill" layout={{ visibility }}
                paint={{ "fill-color": l.fill, "fill-opacity": revealed ? l.fillOpacity! : 0, "fill-opacity-transition": t }} />}
              {l.line && <Layer id={`${l.key}-line`} type="line" layout={{ visibility }}
                paint={{ "line-color": l.line, "line-width": l.lineWidth!, "line-opacity": revealed || l.key === "field" ? 1 : 0,
                         "line-opacity-transition": t, ...(l.dash ? { "line-dasharray": l.dash } : {}) }} />}
            </Source>
          );
        })}
        {overlay && (
          <Source id="drone" type="image" url={overlay.url} coordinates={[
            [overlay.bounds[0], overlay.bounds[3]], [overlay.bounds[2], overlay.bounds[3]],
            [overlay.bounds[2], overlay.bounds[1]], [overlay.bounds[0], overlay.bounds[1]]]}>
            <Layer id="drone" type="raster" layout={{ visibility: hidden.drone ? "none" : "visible" }}
                   beforeId={present.length ? `${present[0].key}-${present[0].fill ? "fill" : "line"}` : undefined}
                   paint={{ "raster-opacity": 1, "raster-fade-duration": 0 }} />
          </Source>
        )}
        <NavigationControl position="top-right" showCompass={false} />
      </MapGL>

      <div {...stylex.props(s.card, s.tools)} role="toolbar" aria-label="Draw on the map">
        <ToolButton active={tool === "polygon" && target === "field"} onClick={() => pick("field", "polygon")}>Draw field</ToolButton>
        <ToolButton active={tool === "rectangle" && target === "field"} onClick={() => pick("field", "rectangle")}>Rectangle</ToolButton>
        <ToolButton active={tool !== null && target === "managed"} onClick={() => pick("managed", "polygon")}>Managed land</ToolButton>
        <ToolButton active={tool === "select"} onClick={() => setTool((c) => (c === "select" ? null : "select"))}>Edit</ToolButton>
      </div>

      {(present.length > 0 || overlay) && (
        <div {...stylex.props(s.card, s.key)}>
          <button type="button" {...stylex.props(s.keyToggle)} aria-expanded={keyOpen}
                  onClick={() => setKeyOpen((o) => !o)}>
            Key <span {...stylex.props(s.hint)}>{keyOpen ? "Hide" : "Show"}</span>
          </button>
          {keyOpen && (
            <ul {...stylex.props(s.keyList)}>
              {overlay && <KeyRow name="Drone imagery" swatch={{ background: "linear-gradient(135deg,#6b7d4f,#a89b74)" }}
                                  on={!hidden.drone} toggle={() => setHidden((h) => ({ ...h, drone: !h.drone }))} />}
              {present.map((l) => (
                <KeyRow key={l.key} name={l.name} on={!hidden[l.key]} toggle={() => setHidden((h) => ({ ...h, [l.key]: !h[l.key] }))}
                        swatch={l.fill ? { background: l.fill, opacity: Math.min(1, (l.fillOpacity ?? 0.4) + 0.4) }
                                       : { borderTop: `3px solid ${l.line}`, background: "#6b7d4f", height: 8 }} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function ToolButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
            {...stylex.props(s.tool, active && s.toolOn)}>
      {children}
    </button>
  );
}

function KeyRow({ name, swatch, on, toggle }: { name: string; swatch: React.CSSProperties; on: boolean; toggle: () => void }) {
  return (
    <li>
      <label {...stylex.props(s.keyRow)}>
        <input type="checkbox" checked={on} onChange={toggle} {...stylex.props(s.tick)} />
        <i {...stylex.props(s.swatch)} style={swatch} />
        {name}
      </label>
    </li>
  );
}
