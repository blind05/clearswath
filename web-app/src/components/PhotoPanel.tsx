// Check one photo: the weed model's overlay on top of it. A live GPU call, so it needs the access code.
import { useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { post } from "@/api";
import { Button } from "@astryxdesign/core/Button";
import { FileInput } from "@astryxdesign/core/FileInput";
import { text } from "@/styles";
import { color } from "@/tokens.stylex";
import type { PhotoResult } from "@/types";

const s = stylex.create({
  section: { paddingBlock: 18 },
  result: { borderTopWidth: 1, borderTopStyle: "solid", borderTopColor: color.rule },
  form: { marginTop: 12 },
  share: { display: "flex", alignItems: "center", gap: 12, fontSize: 22, fontWeight: 600, color: color.spray },
  square: { width: 14, height: 14, backgroundColor: "currentColor" },
  frame: { position: "relative", marginBlock: 10 },
  photo: { display: "block", width: "100%" },
  overlay: { position: "absolute", inset: 0, width: "100%", height: "100%" },
});

export function PhotoPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ r: PhotoResult; url: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const body = new FormData();
    body.append("photo", file);
    setBusy(true); setError("");
    try { setResult({ r: await post<PhotoResult>("/api/photo", body), url: URL.createObjectURL(file) }); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  const trained = result ? Object.entries(result.r.trained_on ?? {}).map(([k, n]) => `${k} (${n} images)`).join(" and ") : "";
  return (
    <div>
      <section {...stylex.props(s.section)}>
        <h2 {...stylex.props(text.h2)}>Check a photo for weeds</h2>
        <p {...stylex.props(text.small)}>Take a photo looking straight down at the crop from 1 to 3 m. The weed model
          was trained on cotton and sugar beet, so other crops are a stretch. It marks what it takes for weeds in magenta:
          a guide for scouting, not a spray map.</p>
        <form onSubmit={submit} {...stylex.props(text.stack, s.form)}>
          <FileInput id="photo" mode="input" label="Photo (JPEG, PNG or WebP)" accept=".jpg,.jpeg,.png,.webp" isRequired
                     value={file} onChange={(f) => setFile(Array.isArray(f) ? f[0] ?? null : f)} />
          <Button type="submit" variant="primary" isDisabled={!file} isLoading={busy} label={busy ? "Looking for weeds…" : "Find weeds"} />
        </form>
        {error && <p role="alert" {...stylex.props(text.error)}>{error}</p>}
      </section>
      {result && (
        <section {...stylex.props(s.section, s.result)}>
          <p {...stylex.props(s.share)}>
            <span aria-hidden {...stylex.props(s.square)} />{(100 * result.r.share_flagged).toFixed(1)}% flagged as weeds
          </p>
          <div {...stylex.props(s.frame)}>
            <img src={result.url} alt="Your photo" {...stylex.props(s.photo)} />
            <img src={`data:image/png;base64,${result.r.overlay_png}`} alt="Areas the weed model flagged, in magenta" {...stylex.props(s.overlay)} />
          </div>
          <p {...stylex.props(text.small)}>DINOv3 features with a head trained on {trained}. A guide for scouting, not a spray map.</p>
        </section>
      )}
    </div>
  );
}
