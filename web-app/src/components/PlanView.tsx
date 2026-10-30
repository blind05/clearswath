// What the plan says, top to bottom in the order an applicator needs it: the decision, what to check first,
// why (in the label's own words), Muse Spark's explanation, the rules they may untick, the spray map, the files.
import { useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { text } from "@/styles";
import { color, font } from "@/tokens.stylex";
import type { FeatureCollection, Geometry } from "geojson";
import type { Plan, Reason } from "@/types";
import { RecordForm } from "./RecordForm";

const VERDICT = { go: "No conflicts in checked rules", adjust: "Adjust", "no-go": "Do not spray" } as const;

const fade = stylex.keyframes({ from: { opacity: 0 }, to: { opacity: 1 } });

const s = stylex.create({
  section: {
    borderTopWidth: { default: 1, ":first-child": 0 }, borderTopStyle: "solid", borderTopColor: color.rule,
    paddingBlock: 18,
  },
  lead: { paddingTop: 22, animationName: fade, animationDuration: "200ms" },
  link: { textDecoration: "underline", color: "inherit", background: "none", border: 0, padding: 0, font: "inherit", cursor: "pointer" },
  verdict: {
    display: "flex", alignItems: "flex-start", gap: 12, marginTop: 12,
    fontSize: 28, fontWeight: 600, lineHeight: 1.2, letterSpacing: "-0.01em",
  },
  go: { color: color.clear },
  adjust: { color: color.adjust },
  "no-go": { color: color.stop },
  square: { width: 16, height: 16, flex: "none", marginTop: 9, backgroundColor: "currentColor" },
  headline: { marginTop: 10, fontSize: 18 },
  figures: { display: "flex", flexWrap: "wrap", columnGap: 20, rowGap: 4, marginTop: 12 },
  figure: { marginRight: 4, fontSize: 15, fontWeight: 600, color: color.ink },
  gap: { marginTop: 12 },
  warn: { borderLeftWidth: 3, borderLeftStyle: "solid", borderLeftColor: color.adjust, paddingBlock: 2, paddingLeft: 14 },
  list: { listStyle: "disc", paddingLeft: 18, display: "grid", gap: 4 },
  quote: { borderLeftWidth: 1, borderLeftStyle: "solid", borderLeftColor: color.ink, paddingLeft: 12, fontFamily: font.condensed, fontSize: 15, lineHeight: 1.4 },
  caption: { marginTop: 4, paddingLeft: 13 },
  bullet: { display: "flex", gap: 8, marginTop: 10 },
  dot: { width: 8, height: 8, flex: "none", marginTop: 7, backgroundColor: color.muted },
  pre: { whiteSpace: "pre-line" },
  summary: { cursor: "pointer" },
  steps: { listStyle: "decimal", paddingLeft: 20, marginTop: 6 },
  rule: { marginTop: 8 },
  files: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 },
});

export function Section({ title, children, xstyle }: { title?: string; children: React.ReactNode; xstyle?: stylex.StyleXStyles }) {
  return (
    <section {...stylex.props(s.section, xstyle)}>
      {title && <h2 {...stylex.props(text.h2)}>{title}</h2>}
      {children}
    </section>
  );
}

export function Excerpt({ quote, caption }: { quote: string; caption: string }) {
  return (
    <figure {...stylex.props(s.gap)}>
      <blockquote {...stylex.props(s.quote)}>{quote}</blockquote>
      <figcaption {...stylex.props(text.small, s.caption)}>{caption}</figcaption>
    </figure>
  );
}

function headline(p: Plan): string {
  const a = p.acres;
  if (p.status === "no-go") return "Nothing on this field can be sprayed until the reasons below are resolved.";
  if (p.status === "adjust" && a.excluded_acres > 0)
    return `${a.spray_acres.toFixed(1)} of ${a.field_acres.toFixed(1)} acres can be sprayed. The rest is held back.`;
  if (p.status === "adjust") return `All ${a.field_acres.toFixed(1)} acres can be sprayed once the step below is done.`;
  return `All ${a.field_acres.toFixed(1)} acres can be sprayed.`;
}

function ReasonView({ r, product }: { r: Reason; product: string }) {
  if (r.source === "label" && r.quote) {
    const what = r.kind === "runoff" ? "runoff mitigation points required" : `${r.distance_ft} ft from ${r.target}`;
    return <Excerpt quote={r.quote} caption={`${product}, page ${r.page}. Applied as ${what}.`} />;
  }
  return <p {...stylex.props(s.bullet)}><span aria-hidden {...stylex.props(s.dot)} />{r.summary}</p>;
}

interface Props {
  plan: Plan;
  agentAsked: boolean;
  onUntick: (excluded: number[]) => void;
  onAskLive: () => void;
  onSwitchDemo: () => void;
}

export function PlanView({ plan: p, agentAsked, onUntick, onAskLive, onSwitchDemo }: Props) {
  const product = p.label.product_name || "The label";
  const a = p.acres;
  const pct = p.spot ? Math.round((100 * p.spot.treated_acres) / p.spot.field_acres) : null;
  const [rate, setRate] = useState<number | null>(null);
  const rateOk = rate != null && rate > 0 && rate <= 1000;
  const excluded = p.confirm.filter((c) => !c.applied).map((c) => c.id);

  return (
    <div aria-live="polite">
      <Section xstyle={s.lead}>
        {p.demo && (
          <p {...stylex.props(text.small)}>
            Demo: {p.demo.field === "mt" ? "Montana rangeland, leafy spurge" : "South Dakota cropland"}
            {p.demo.cached && `, saved run, bulletin for ${p.demo.month}`}.{" "}
            <button type="button" id="demo-switch" {...stylex.props(s.link)} onClick={onSwitchDemo}>
              {p.demo.field === "mt" ? "Show the South Dakota cropland demo"
                : p.demo.field ? "Show the field drawn up to the creek" : "Show the corrected field"}
            </button>
          </p>
        )}
        {/* the status class stays for the recorder's `#status.go` */}
        <p id="status" {...withClass(stylex.props(s.verdict, s[p.status]), p.status)}>
          <span aria-hidden {...stylex.props(s.square)} />
          {VERDICT[p.status]}
        </p>
        <p {...stylex.props(s.headline)}>{headline(p)}</p>
        <div {...stylex.props(text.small, text.num, s.figures)}>
          <Figure n={a.field_acres} label="ac field" />
          <Figure n={a.spray_acres} label="ac sprayable" />
          <Figure n={a.excluded_acres} label="ac held back" />
          {p.spot && <Figure n={p.spot.treated_acres} label={`ac spot sprayed (${pct}%)`} />}
        </div>
        <p {...stylex.props(text.small, s.gap)}>Not checked: weather and inversions, runoff points, your licence, field conditions.</p>
      </Section>

      {p.warnings.length > 0 && (
        <Section>
          <div role="alert" {...stylex.props(s.warn)}>
            <h2 {...stylex.props(text.h2)}>Check before spraying</h2>
            <ul {...stylex.props(s.list)}>{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        </Section>
      )}

      <Section title="Why">
        {p.reasons.length ? p.reasons.map((r, i) => <ReasonView key={i} r={r} product={product} />)
          : <p {...stylex.props(text.small)}>No hazard, setback or bulletin limit affects this field.</p>}
      </Section>

      {p.answer && (
        <section {...withClass(stylex.props(s.section), "agent")}>
          <p {...stylex.props(text.small)}>
            {p.mode === "agent" ? "Explained by Muse Spark"
              : p.mode === "replay" ? `Saved Muse Spark answer (${p.replay!.model.split("/").pop()}, ${p.replay!.date})`
              : "Muse Spark was unavailable; this is the plan's own summary"}
          </p>
          <p {...stylex.props(s.pre, s.rule)}>{p.answer}</p>
          <details {...stylex.props(text.small, s.gap)}>
            <summary {...stylex.props(s.summary)}>How it decided</summary>
            <ol {...stylex.props(s.steps)}>
              {p.trace?.map((t, i) => (
                <li key={i}>{t.tool ? `${t.tool}${t.seconds != null ? ` (${t.seconds} s)` : ""}${t.note ? `: ${t.note}` : ""}` : t.note}</li>
              ))}
            </ol>
          </details>
        </section>
      )}
      {p.demo && agentAsked && !p.answer && (
        <Section>
          <Button id="agent-live" variant="secondary" label="Ask Muse Spark live (needs the access code)" onClick={onAskLive} />
        </Section>
      )}

      {p.confirm.length > 0 && (
        <Section title={p.label.source === "image" ? "Confirm the rules read from the photo" : "Rules that may not apply to you"}>
          <p {...stylex.props(text.small)}>Each is applied unless you untick it. Unticking is recorded in the result.</p>
          {p.confirm.map((c) => (
            <div key={c.id} data-rule-row={c.id} {...stylex.props(s.rule)}>
              <CheckboxInput size="sm" value={c.applied}
                             label={`${c.summary} (p. ${c.page}${c.condition ? `, only when ${c.condition}` : ""})`}
                             onChange={(on) => onUntick(on ? excluded.filter((x) => x !== c.id) : [...excluded, c.id])} />
            </div>
          ))}
        </Section>
      )}

      {p.scout.length > 0 && (
        <Section title="Hazards on the aerial photo">
          <ul {...stylex.props(s.list)}>{p.scout.map((line) => <li key={line}>{line}.</li>)}</ul>
          <p {...stylex.props(text.small, s.rule)}>
            {count(p.layers.habitat, "tree line or wood", "tree lines and woods")}, {count(p.layers.building, "building", "buildings")} and{" "}
            {count(p.layers.possible_water, "possible water area", "possible water areas")} on the map. The models only outline
            them: water comes from the national water map, possible water is for you to check, and the buffers come from the label.
          </p>
        </Section>
      )}

      {p.spot && (
        <Section title="Spray map">
          <p {...stylex.props(text.num)}>The weed map sprays {p.spot.treated_acres.toFixed(2)} ac of {p.spot.field_acres.toFixed(1)} ac, in {p.spot.cell_size_m} m cells.</p>
          {p.weed_source && <p {...stylex.props(text.small, s.rule)}>Weed map: {p.weed_source}.</p>}
        </Section>
      )}

      <Section title="Files for the sprayer">
        {p.spot && (
          <NumberInput id="dji-rate" label="Spray volume for the DJI prescription (L/ha)" hasClear value={rate} onChange={setRate}
                       min={p.carrier_min?.l_ha ?? 0.1} max={1000} step={0.1}
                       placeholder={p.carrier_min ? `At least ${p.carrier_min.l_ha}` : undefined} />
        )}
        {p.spot && p.carrier_min && (
          <Excerpt quote={p.carrier_min.quote}
                   caption={`${product}, page ${p.carrier_min.page}. The largest minimum spray volume on the label: at least ${p.carrier_min.l_ha} L/ha.`} />
        )}
        <div {...stylex.props(s.files)}>
          {p.spot && (
            <Button id="dji-link" variant="secondary" label="DJI Agras prescription" isDisabled={!rateOk}
                    href={rateOk ? `/api/export/${p.run_id}/dji?rate=${rate}` : undefined} />
          )}
          <Button variant="secondary" label="KML" href={`/api/kml/${p.run_id}`} />
          {p.spot && <Button variant="secondary" label="GeoJSON" href={`/api/export/${p.run_id}/geojson`} />}
        </div>
        <p {...stylex.props(text.small, s.gap)}>{product}, EPA Reg. No. {p.label.epa_reg_no || "not found"}. {p.bulletin.citation}</p>
        <p {...stylex.props(text.small, s.rule)}>
          Imagery {p.imagery_date || "date unknown"}; water from {p.water_source}; {p.method}, {p.month}.
          Decision support only: you remain responsible for following the label and the official bulletin.
        </p>
      </Section>

      <Section title="Application record">
        <RecordForm runId={p.run_id} />
      </Section>
    </div>
  );
}

// StyleX owns className; this adds a plain class the recorder and tests look for.
function withClass(props: ReturnType<typeof stylex.props>, name: string) {
  return { ...props, className: `${props.className ?? ""} ${name}` };
}

function count(layer: FeatureCollection | Geometry | undefined, one: string, many: string) {
  const n = layer && "features" in layer ? layer.features.length : 0;
  return `${n} ${n === 1 ? one : many}`;
}

function Figure({ n, label }: { n: number; label: string }) {
  return <span><b {...stylex.props(s.figure)}>{n.toFixed(1)}</b>{label}</span>;
}
