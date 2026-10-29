// The draft application record, filled from a voice note or typed notes. Missing fields are shown, not guessed.
import { useState } from "react";
import { post } from "@/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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

function RecordTable({ fields, rec, missing }: { fields: [string, string][]; rec: Record<string, unknown>; missing: string[] }) {
  return (
    <table className="mt-2.5 w-full border-collapse text-[13px]">
      <tbody>
        {fields.map(([k, name]) => (
          <tr key={k} className={missing.includes(k) ? "text-stop" : ""}>
            <th className="whitespace-nowrap py-1 pr-2.5 text-left align-top font-normal text-muted">{name}</th>
            <td className="border-b border-rule py-1">{rec[k] != null ? String(rec[k]) : missing.includes(k) ? "Missing" : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RecordForm({ runId }: { runId: string }) {
  const [text, setText] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rec, setRec] = useState<AppRecord | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = new FormData();
    body.append("run_id", runId);
    if (audio) body.append("audio", audio);
    body.append("text", text);
    setBusy(true); setError("");
    try { setRec(await post<AppRecord>("/api/record", body)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  const label = (k: string) => RECORD_FIELDS.find(([f]) => f === k)?.[1] ?? k;
  return (
    <div>
      <form id="record" onSubmit={submit} className="grid gap-2.5">
        <div className="grid gap-1"><Label htmlFor="audio">Voice note (WAV)</Label>
          <input id="audio" type="file" accept=".wav,audio/wav" className="text-[13px]" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} /></div>
        <div className="grid gap-1"><Label htmlFor="notes">Or type your notes</Label>
          <textarea id="notes" rows={3} value={text} onChange={(e) => setText(e.target.value)}
                    className="rounded-[4px] border border-rule px-2 py-1.5"
                    placeholder="Sam Ortiz, licence MT-12345, 12 gallons on rangeland, leafy spurge, wind 6 mph NW, 64 degrees" /></div>
        <Button type="submit" variant="outline" disabled={busy}>{busy ? "Filling the record…" : "Fill the record"}</Button>
      </form>
      {error && <p role="alert" className="mt-2.5 font-medium text-stop">{error}</p>}
      {rec && (
        <div>
          {rec.missing.length > 0 && <p role="alert" className="mt-2.5 text-stop">Still needed: {rec.missing.map(label).join(", ")}.</p>}
          <RecordTable fields={RECORD_FIELDS} rec={rec} missing={rec.missing} />
          {rec.part137 && (
            <>
              <h3 className="mt-4 text-[15px] font-semibold">FAA Part 137 record</h3>
              <p className="text-[13px] text-muted">14 CFR 137.71, for commercial agricultural aircraft operators: keep at your home base for at least 12 months.</p>
              <RecordTable fields={PART137_FIELDS} rec={rec.part137} missing={rec.part137.missing} />
            </>
          )}
          <p className="mt-2.5 text-[13px] text-muted">Heard: “{rec.transcript}”</p>
        </div>
      )}
    </div>
  );
}
