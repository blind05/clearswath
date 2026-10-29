// Field and label: what a live plan needs. It folds away once a plan is shown.
import * as stylex from "@stylexjs/stylex";
import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { FileInput } from "@astryxdesign/core/FileInput";
import { Selector } from "@astryxdesign/core/Selector";
import { text } from "@/styles";
import { color } from "@/tokens.stylex";

export interface Setup {
  fieldFile: File | null; labelFile: File | null; month: string; method: "drone" | "ground"; windFrom: string; agent: boolean;
}

const WINDS = [["none", "Not set: drift buffers in every direction"], ["0", "North"], ["45", "Northeast"],
  ["90", "East"], ["135", "Southeast"], ["180", "South"], ["225", "Southwest"], ["270", "West"], ["315", "Northwest"]]
  .map(([value, label]) => ({ value, label }));
const METHODS = [{ value: "drone", label: "Drone" }, { value: "ground", label: "Ground" }];

const s = stylex.create({
  root: { paddingBlock: 18 },
  trigger: { fontWeight: 600 },
  form: { marginTop: 12 },
  pair: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, alignItems: "end" },
  month: { display: "grid", gap: 6, fontSize: 15, fontWeight: 500 },
  // Astryx has no month picker; the native one, dressed like its inputs
  monthInput: {
    height: 32, paddingInline: 8, borderWidth: 1, borderStyle: "solid", borderColor: color.rule, borderRadius: 4,
    font: "inherit", fontSize: 15, color: color.ink, backgroundColor: color.panel,
  },
});

interface Props {
  setup: Setup; onChange: (s: Setup) => void; open: boolean; onOpenChange: (o: boolean) => void;
  fieldDrawn: boolean; managedCount: number; busy: boolean; onPlan: () => void; onDemo: () => void;
}

export function SetupForm({ setup: v, onChange, open, onOpenChange, fieldDrawn, managedCount, busy, onPlan, onDemo }: Props) {
  const set = <K extends keyof Setup>(k: K, x: Setup[K]) => onChange({ ...v, [k]: x });
  const one = (f: File | File[] | null) => (Array.isArray(f) ? f[0] ?? null : f);
  return (
    <Collapsible isOpen={open} onOpenChange={onOpenChange} xstyle={s.root}
                 trigger={<span {...stylex.props(s.trigger)}>Field and label</span>}>
      <form id="form" {...stylex.props(text.stack, s.form)} onSubmit={(e) => { e.preventDefault(); onPlan(); }}>
        <p {...stylex.props(text.small)}>
          {fieldDrawn ? "Field drawn on the map. It replaces any uploaded file."
            : "Draw the field with the tools on the map, or upload it."}
          {managedCount > 0 && ` ${managedCount} area${managedCount === 1 ? "" : "s"} of managed land marked: drift buffers skip ${managedCount === 1 ? "it" : "them"}.`}
        </p>
        <FileInput id="field" mode="input" label="Field outline (GeoJSON, not needed if drawn)" accept=".geojson,.json"
                   value={v.fieldFile} onChange={(f) => set("fieldFile", one(f))} />
        <FileInput id="label" mode="input" label="Pesticide label (PDF or photo)" accept=".pdf,.png,.jpg,.jpeg,.webp"
                   value={v.labelFile} onChange={(f) => set("labelFile", one(f))} />
        <div {...stylex.props(s.pair)}>
          <label {...stylex.props(s.month)}>Month
            <input id="month" type="month" value={v.month} onChange={(e) => set("month", e.target.value)} {...stylex.props(s.monthInput)} />
          </label>
          <Selector id="method" label="Method" options={METHODS} value={v.method}
                    onChange={(m) => set("method", m as Setup["method"])} />
        </div>
        <Selector id="wind" label="Wind from" options={WINDS} value={v.windFrom || "none"}
                  onChange={(w) => set("windFrom", w === "none" ? "" : w)} />
        <CheckboxInput label="Ask Muse Spark to explain the plan" value={v.agent} onChange={(on) => set("agent", on)} />
        <div {...stylex.props(s.pair)}>
          <Button type="submit" variant="primary" label="Plan the spray" isDisabled={busy} />
          <Button id="demo" variant="secondary" label="Try the demo" isDisabled={busy} onClick={onDemo} />
        </div>
      </form>
    </Collapsible>
  );
}
