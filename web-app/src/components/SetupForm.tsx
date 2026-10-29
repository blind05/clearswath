// Field and label: what a live plan needs. It folds away once a plan is shown.
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface Setup {
  fieldFile: File | null; labelFile: File | null; month: string; method: "drone" | "ground"; windFrom: string; agent: boolean;
}

const WINDS: [string, string][] = [["none", "Not set: drift buffers in every direction"], ["0", "North"], ["45", "Northeast"],
  ["90", "East"], ["135", "Southeast"], ["180", "South"], ["225", "Southwest"], ["270", "West"], ["315", "Northwest"]];

interface Props {
  setup: Setup; onChange: (s: Setup) => void; open: boolean; onOpenChange: (o: boolean) => void;
  fieldDrawn: boolean; managedCount: number; busy: boolean; onPlan: () => void; onDemo: () => void;
}

export function SetupForm({ setup: s, onChange, open, onOpenChange, fieldDrawn, managedCount, busy, onPlan, onDemo }: Props) {
  const set = <K extends keyof Setup>(k: K, v: Setup[K]) => onChange({ ...s, [k]: v });
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className="py-[18px]">
      <CollapsibleTrigger className="flex w-full justify-between font-semibold">
        Field and label <span className="text-[13px] font-normal text-muted">{open ? "Hide" : "Show"}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <form id="form" className="mt-3 grid gap-3" onSubmit={(e) => { e.preventDefault(); onPlan(); }}>
          <p className="text-[13px] text-muted">
            {fieldDrawn ? "Field drawn on the map. It replaces any uploaded file."
              : "Draw the field with the tools on the map, or upload it."}
            {managedCount > 0 && ` ${managedCount} area${managedCount === 1 ? "" : "s"} of managed land marked: drift buffers skip ${managedCount === 1 ? "it" : "them"}.`}
          </p>
          <Field id="field" label="Field outline (GeoJSON, not needed if drawn)">
            <input id="field" type="file" accept=".geojson,.json" className="text-[13px]"
                   onChange={(e) => set("fieldFile", e.target.files?.[0] ?? null)} />
          </Field>
          <Field id="label" label="Pesticide label (PDF or photo)">
            <input id="label" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="text-[13px]"
                   onChange={(e) => set("labelFile", e.target.files?.[0] ?? null)} />
          </Field>
          <div className="grid grid-cols-2 gap-2.5">
            <Field id="month" label="Month"><Input id="month" type="month" value={s.month} onChange={(e) => set("month", e.target.value)} /></Field>
            <Field id="method" label="Method">
              <Select value={s.method} onValueChange={(v) => set("method", v as Setup["method"])}>
                <SelectTrigger id="method" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="drone">Drone</SelectItem><SelectItem value="ground">Ground</SelectItem></SelectContent>
              </Select>
            </Field>
          </div>
          <Field id="wind" label="Wind from">
            <Select value={s.windFrom || "none"} onValueChange={(v) => set("windFrom", v === "none" ? "" : v)}>
              <SelectTrigger id="wind" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{WINDS.map(([v, n]) => <SelectItem key={v} value={v}>{n}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <div className="flex items-start gap-2 text-[14px]">
            <Checkbox id="agent" checked={s.agent} onCheckedChange={(on) => set("agent", on === true)} className="mt-0.5" />
            <label htmlFor="agent">Ask Muse Spark to explain the plan</label>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <Button type="submit" disabled={busy}>Plan the spray</Button>
            <Button type="button" id="demo" variant="outline" disabled={busy} onClick={onDemo}>Try the demo</Button>
          </div>
        </form>
      </CollapsibleContent>
    </Collapsible>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return <div className="grid gap-1"><Label htmlFor={id}>{label}</Label>{children}</div>;
}
