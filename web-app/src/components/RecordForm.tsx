// The draft application record, filled from a voice note or typed notes. Missing fields are shown, not guessed.
import { useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { post } from "@/api";
import { Button } from "@astryxdesign/core/Button";
import { FileInput } from "@astryxdesign/core/FileInput";
import { TextArea } from "@astryxdesign/core/TextArea";
import { text } from "@/styles";
import { color } from "@/tokens.stylex";
import type { AppRecord } from "@/types";

const RECORD_FIELDS: [string, string][] = [
  ["applicator_name", "Applicator"], ["certification_number", "Licence no."], ["operator_name", "Operator"],
  ["application_date", "Date"], ["start_time", "Start"], ["end_time", "End"],
  ["owner_name", "Owner or lessee"], ["owner_address", "Owner address"],
  ["product_name", "Product"], ["manufacturer", "Manufacturer"], ["epa_reg_no", "EPA Reg. No."],
  ["amount_applied", "Amount applied"], ["rate", "Rate"], ["area_treated_acres", "Area (ac)"],
  ["pest", "Pest"], ["crop_or_site", "Crop or site"], ["growth_stage", "Growth stage"],
  ["location", "Location"], ["method", "Method"], ["equipment", "Equipment"], ["wind_speed_mph", "Wind (mph)"],
  ["wind_direction", "Wind from"], ["temperature_f", "Temperature (°F)"], ["notes", "Notes"],
];
const PART137_FIELDS: [string, string][] = [
  ["customer_name", "Customer"], ["customer_address", "Customer address"], ["service_date", "Date of service"],
  ["material", "Material dispensed"], ["quantity", "Quantity"], ["pilot_name", "Pilot"],
  ["pilot_address", "Pilot address"], ["pilot_certificate_number", "Pilot FAA certificate no."],
  ["pilot_knowledge_test_date", "Pilot met 137.19(e) on"],
];

const s = stylex.create({
  table: { marginTop: 10, width: "100%", borderCollapse: "collapse", fontSize: 13 },
  missing: { color: color.stop },
  th: { whiteSpace: "nowrap", paddingBlock: 4, paddingRight: 10, textAlign: "left", verticalAlign: "top", fontWeight: 400, color: color.muted },
  td: { borderBottomWidth: 1, borderBottomStyle: "solid", borderBottomColor: color.rule, paddingBlock: 4 },
  gap: { marginTop: 10 },
  h3: { marginTop: 16, fontSize: 15, fontWeight: 600 },
});

function RecordTable({ fields, rec, missing }: { fields: [string, string][]; rec: Record<string, unknown>; missing: string[] }) {
  return (
    <table {...stylex.props(s.table)}>
      <tbody>
        {fields.map(([k, name]) => (
          <tr key={k} {...stylex.props(missing.includes(k) && s.missing)}>
            <th {...stylex.props(s.th)}>{name}</th>
            <td {...stylex.props(s.td)}>{rec[k] != null ? String(rec[k]) : missing.includes(k) ? "Missing" : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RecordForm({ runId }: { runId: string }) {
  const [notes, setNotes] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rec, setRec] = useState<AppRecord | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = new FormData();
    body.append("run_id", runId);
    if (audio) body.append("audio", audio);
    body.append("text", notes);
    setBusy(true); setError("");
    try { setRec(await post<AppRecord>("/api/record", body)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  const label = (k: string) => RECORD_FIELDS.find(([f]) => f === k)?.[1] ?? k;
  return (
    <div>
      <form id="record" onSubmit={submit} {...stylex.props(text.stack)}>
        <FileInput id="audio" mode="input" label="Voice note (WAV)" accept=".wav,audio/wav"
                   value={audio} onChange={(f) => setAudio(Array.isArray(f) ? f[0] ?? null : f)} />
        <TextArea id="notes" label="Or type your notes" rows={3} value={notes} onChange={setNotes}
                  placeholder="Sam Ortiz, licence MT-12345, 12 gallons on rangeland, leafy spurge, wind 6 mph NW, 64 degrees" />
        <Button type="submit" variant="secondary" isLoading={busy} label={busy ? "Filling the record…" : "Fill the record"} />
      </form>
      {error && <p role="alert" {...stylex.props(text.error)}>{error}</p>}
      {rec && (
        <div>
          {rec.missing.length > 0 && <p role="alert" {...stylex.props(s.missing, s.gap)}>Still needed: {rec.missing.map(label).join(", ")}.</p>}
          <RecordTable fields={RECORD_FIELDS} rec={rec} missing={rec.missing} />
          {rec.part137 && (
            <>
              <h3 {...stylex.props(s.h3)}>FAA Part 137 record</h3>
              <p {...stylex.props(text.small)}>14 CFR 137.71, for commercial agricultural aircraft operators: keep at your home base for at least 12 months.</p>
              <RecordTable fields={PART137_FIELDS} rec={rec.part137} missing={rec.part137.missing} />
            </>
          )}
          <p {...stylex.props(text.small, s.gap)}>Heard: “{rec.transcript}”</p>
        </div>
      )}
    </div>
  );
}
