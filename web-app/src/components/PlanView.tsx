// What the plan says, top to bottom in the order an applicator needs it: the decision, what to check first,
// why (in the label's own words), Muse Spark's explanation, the rules they may untick, the spray map, the files.
import { useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type { Plan, Reason } from "@/types";
import { RecordForm } from "./RecordForm";

const VERDICT = { go: "No conflicts in checked rules", adjust: "Adjust", "no-go": "Do not spray" } as const;
const MARK = { go: "text-clear", adjust: "text-adjust", "no-go": "text-stop" } as const;

export function Section({ title, children, className }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("border-t border-rule py-[18px] first:border-t-0", className)}>
      {title && <h2 className="mb-2 text-[15px] font-semibold">{title}</h2>}
      {children}
    </section>
  );
}

export function Excerpt({ quote, caption }: { quote: string; caption: string }) {
  return (
    <figure className="mt-3">
      <blockquote className="border-l border-ink pl-3 font-condensed text-[15px] leading-[1.4]">{quote}</blockquote>
      <figcaption className="mt-1 pl-[13px] text-[13px] text-muted">{caption}</figcaption>
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
  return (
    <p className="mt-2.5 flex gap-2">
      <span aria-hidden className="mt-[7px] h-2 w-2 flex-none bg-muted" />
      {r.summary}
    </p>
  );
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
  const [rate, setRate] = useState("");
  const rateOk = Number(rate) > 0 && Number(rate) <= 1000;
  const excluded = p.confirm.filter((c) => !c.applied).map((c) => c.id);

  return (
    <div aria-live="polite">
      <Section className="pt-[22px] motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200">
        {p.demo && (
          <p className="text-[13px] text-muted">
            Demo: {p.demo.field === "mt" ? "Montana rangeland, leafy spurge" : "South Dakota cropland"}
            {p.demo.cached && `, saved run, bulletin for ${p.demo.month}`}.{" "}
            <button type="button" id="demo-switch" className="underline" onClick={onSwitchDemo}>
              {p.demo.field === "mt" ? "Show the South Dakota cropland demo"
                : p.demo.field ? "Show the field drawn up to the creek" : "Show the corrected field"}
            </button>
          </p>
        )}
        <p id="status" className={cn("mt-3 flex items-start gap-3 text-[28px] font-semibold leading-tight tracking-[-0.01em]", MARK[p.status], p.status)}>
          <span aria-hidden className="mt-[9px] h-4 w-4 flex-none bg-current" />
          {VERDICT[p.status]}
        </p>
        <p className="mt-2.5 text-[18px]">{headline(p)}</p>
        <div className="num mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted">
          <Figure n={a.field_acres} label="ac field" />
          <Figure n={a.spray_acres} label="ac sprayable" />
          <Figure n={a.excluded_acres} label="ac held back" />
          {p.spot && <Figure n={p.spot.treated_acres} label={`ac spot sprayed (${pct}%)`} />}
        </div>
        <p className="mt-3 text-[13px] text-muted">Not checked: weather and inversions, runoff points, your licence, field conditions.</p>
      </Section>

      {p.warnings.length > 0 && (
        <Section>
          <div role="alert" className="border-l-[3px] border-adjust py-0.5 pl-3.5">
            <h2 className="mb-1.5 text-[15px] font-semibold">Check before spraying</h2>
            <ul className="list-disc space-y-1 pl-[18px]">{p.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        </Section>
      )}

      <Section title="Why">
        {p.reasons.length ? p.reasons.map((r, i) => <ReasonView key={i} r={r} product={product} />)
          : <p className="text-[13px] text-muted">No hazard, setback or bulletin limit affects this field.</p>}
      </Section>

      {p.answer && (
        <Section className="agent">
          <p className="mb-1.5 text-[13px] text-muted">
            {p.mode === "agent" ? "Explained by Muse Spark"
              : p.mode === "replay" ? `Saved Muse Spark answer (${p.replay!.model.split("/").pop()}, ${p.replay!.date})`
              : "Muse Spark was unavailable; this is the plan's own summary"}
          </p>
          <p className="whitespace-pre-line">{p.answer}</p>
          <details className="mt-2.5 text-[13px] text-muted">
            <summary className="cursor-pointer">How it decided</summary>
            <ol className="mt-1.5 list-decimal pl-5">
              {p.trace?.map((t, i) => (
                <li key={i}>{t.tool ? `${t.tool}${t.seconds != null ? ` (${t.seconds} s)` : ""}${t.note ? `: ${t.note}` : ""}` : t.note}</li>
              ))}
            </ol>
          </details>
        </Section>
      )}
      {p.demo && agentAsked && !p.answer && (
        <Section>
          <button type="button" id="agent-live" onClick={onAskLive}
                  className="rounded-[4px] border border-ink px-3 py-2 text-[14px] font-medium">
            Ask Muse Spark live (needs the access code)
          </button>
        </Section>
      )}

      {p.confirm.length > 0 && (
        <Section title={p.label.source === "image" ? "Confirm the rules read from the photo" : "Rules that may not apply to you"}>
          <p className="text-[13px] text-muted">Each is applied unless you untick it. Unticking is recorded in the result.</p>
          {p.confirm.map((c) => (
            <div key={c.id} className="mt-2 flex items-start gap-2 text-[13px]" data-rule-row={c.id}>
              <Checkbox id={`rule-${c.id}`} checked={c.applied} className="mt-0.5"
                        onCheckedChange={(on) => onUntick(on ? excluded.filter((x) => x !== c.id) : [...excluded, c.id])} />
              <label htmlFor={`rule-${c.id}`}>{c.summary} (p. {c.page}{c.condition ? `, only when ${c.condition}` : ""})</label>
            </div>
          ))}
        </Section>
      )}

      {p.spot && (
        <Section title="Spray map">
          <p className="num">The weed map sprays {p.spot.treated_acres.toFixed(2)} ac of {p.spot.field_acres.toFixed(1)} ac, in {p.spot.cell_size_m} m cells.</p>
          {p.weed_source && <p className="mt-1.5 text-[13px] text-muted">Weed map: {p.weed_source}.</p>}
        </Section>
      )}

      <Section title="Files for the sprayer">
        {p.spot && (
          <div className="grid gap-1.5">
            <Label htmlFor="dji-rate">Spray volume for the DJI prescription (L/ha)</Label>
            <Input id="dji-rate" type="number" inputMode="decimal" min={p.carrier_min?.l_ha ?? 0.1} max={1000} step={0.1}
                   value={rate} onChange={(e) => setRate(e.target.value)}
                   placeholder={p.carrier_min ? `At least ${p.carrier_min.l_ha}` : undefined} />
          </div>
        )}
        {p.spot && p.carrier_min && (
          <Excerpt quote={p.carrier_min.quote}
                   caption={`${product}, page ${p.carrier_min.page}. The largest minimum spray volume on the label: at least ${p.carrier_min.l_ha} L/ha.`} />
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {p.spot && (
            <FileLink id="dji-link" href={rateOk ? `/api/export/${p.run_id}/dji?rate=${Number(rate)}` : undefined}>
              DJI Agras prescription
            </FileLink>
          )}
          <FileLink href={`/api/kml/${p.run_id}`}>KML</FileLink>
          {p.spot && <FileLink href={`/api/export/${p.run_id}/geojson`}>GeoJSON</FileLink>}
        </div>
        <p className="mt-3 text-[13px] text-muted">{product}, EPA Reg. No. {p.label.epa_reg_no || "not found"}. {p.bulletin.citation}</p>
        <p className="mt-2 text-[13px] text-muted">
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

function Figure({ n, label }: { n: number; label: string }) {
  return <span><b className="mr-1 text-[15px] font-semibold text-ink">{n.toFixed(1)}</b>{label}</span>;
}

function FileLink({ href, id, children }: { href?: string; id?: string; children: React.ReactNode }) {
  return (
    <a id={id} href={href} download={href ? "" : undefined} aria-disabled={href ? undefined : true}
       className={cn("rounded-[4px] border border-ink px-3 py-2 text-[14px] font-medium no-underline",
                     !href && "cursor-not-allowed opacity-40")}>
      {children}
    </a>
  );
}
