// The draft application record, filled from a voice note or typed notes. Missing fields are shown, not guessed.
import { useEffect, useRef, useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { post } from "@/api";
import { toWav16k } from "@/wav";
import { Button } from "@astryxdesign/core/Button";
import { FileInput } from "@astryxdesign/core/FileInput";
import { TextArea } from "@astryxdesign/core/TextArea";
import { text } from "@/styles";
import { color } from "@/tokens.stylex";
import type { AppRecord, Plan } from "@/types";

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
  remove: {
    padding: 0, borderStyle: "none", backgroundColor: "transparent", cursor: "pointer",
    fontSize: 13, color: color.muted, textDecorationLine: "underline",
  },
});

// Seconds as m:ss for the record button and the ready line.
function fmt(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

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

export function RecordForm({ runId, saved }: { runId: string; saved?: Plan["saved_record"] }) {
  const [notes, setNotes] = useState("");
  const [audio, setAudio] = useState<Blob | null>(null);
  const [noteSecs, setNoteSecs] = useState<number | null>(null);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rec, setRec] = useState<AppRecord | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startRef = useRef(0);

  // Stop the mic if the form unmounts mid-recording.
  useEffect(() => () => {
    if (timerRef.current != null) window.clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
  }, []);

  function stopTracks() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  async function toggleRecord() {
    if (recording) { recRef.current?.stop(); return; }
    setError("");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("The microphone isn't available here. Upload an audio file or type the notes.");
      return;
    }
    streamRef.current = stream;
    chunksRef.current = [];
    const mr = new MediaRecorder(stream);
    recRef.current = mr;
    startRef.current = Date.now();
    setElapsed(0);
    setAudio(null);
    setNoteSecs(null);
    mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    mr.onstop = () => {
      if (timerRef.current != null) window.clearInterval(timerRef.current);
      stopTracks();
      setRecording(false);
      const blob = new Blob(chunksRef.current, { type: mr.mimeType });
      if (blob.size > 0) {
        setAudio(blob);
        setNoteSecs(Math.round((Date.now() - startRef.current) / 1000));
      }
    };
    mr.start();
    setRecording(true);
    timerRef.current = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
  }

  // An uploaded file replaces any recorded note.
  function pick(f: File | File[] | null) {
    setAudio(Array.isArray(f) ? f[0] ?? null : f);
    setNoteSecs(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = new FormData();
    body.append("run_id", runId);
    if (audio) {
      try {
        body.append("audio", await toWav16k(audio), "note.wav");
      } catch (err) { setError((err as Error).message); return; }
    }
    body.append("text", notes);
    setBusy(true); setError("");
    try { setRec(await post<AppRecord>("/api/record", body)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  const shown = rec ?? saved?.record;  // until you fill your own, the demo shows its saved voice note
  const label = (k: string) => RECORD_FIELDS.find(([f]) => f === k)?.[1] ?? k;
  return (
    <div>
      <form id="record" onSubmit={submit} {...stylex.props(text.stack)}>
        <Button type="button" variant="secondary" onClick={toggleRecord}
                label={recording ? `Stop recording (${fmt(elapsed)})` : "Record a note"} />
        <FileInput id="audio" mode="input" label="Or upload a voice note" accept="audio/*"
                   value={audio instanceof File ? audio : null} onChange={pick} />
        {audio && !recording && (
          <p {...stylex.props(text.small, s.gap)}>
            {noteSecs != null ? `Voice note ready (${fmt(noteSecs)}).` : "Voice note ready."}{" "}
            <button type="button" {...stylex.props(s.remove)}
                    onClick={() => { setAudio(null); setNoteSecs(null); }}>Remove</button>
          </p>
        )}
        <TextArea id="notes" label="Or type your notes" rows={3} value={notes} onChange={setNotes}
                  placeholder="Sam Ortiz, licence MT-12345, 12 gallons on rangeland, leafy spurge, wind 6 mph NW, 64 degrees" />
        <Button type="submit" variant="secondary" isLoading={busy} label={busy ? "Filling the record…" : "Fill the record"} />
      </form>
      {error && <p role="alert" {...stylex.props(text.error)}>{error}</p>}
      {shown && (
        <div>
          {!rec && saved && <p {...stylex.props(text.small, s.gap)}>Saved voice note ({saved.model}, {saved.date}): a real recording, transcribed and filled then.</p>}
          {shown.missing.length > 0 && <p role="alert" {...stylex.props(s.missing, s.gap)}>Still needed: {shown.missing.map(label).join(", ")}.</p>}
          <RecordTable fields={RECORD_FIELDS} rec={shown} missing={shown.missing} />
          {shown.part137 && (
            <>
              <h3 {...stylex.props(s.h3)}>FAA Part 137 record</h3>
              <p {...stylex.props(text.small)}>14 CFR 137.71, for commercial agricultural aircraft operators: keep at your home base for at least 12 months.</p>
              <RecordTable fields={PART137_FIELDS} rec={shown.part137} missing={shown.part137.missing} />
            </>
          )}
          <p {...stylex.props(text.small, s.gap)}>Heard: “{shown.transcript}”</p>
        </div>
      )}
    </div>
  );
}
