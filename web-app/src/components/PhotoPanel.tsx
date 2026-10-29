// Check one photo: the weed model's overlay on top of it. A live GPU call, so it needs the access code.
import { useState } from "react";
import { post } from "@/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { PhotoResult } from "@/types";

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
      <section className="py-[18px]">
        <h2 className="mb-2 text-[15px] font-semibold">Check a photo for weeds</h2>
        <p className="text-[13px] text-muted">Take a photo looking straight down at the crop from 1 to 3 m. The weed model
          was trained on cotton and sugar beet, so other crops are a stretch. It marks what it takes for weeds in magenta:
          a guide for scouting, not a spray map.</p>
        <form onSubmit={submit} className="mt-3 grid gap-3">
          <div className="grid gap-1"><Label htmlFor="photo">Photo (JPEG, PNG or WebP)</Label>
            <input id="photo" type="file" accept=".jpg,.jpeg,.png,.webp" required className="text-[13px]"
                   onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
          <Button type="submit" disabled={busy || !file}>{busy ? "Looking for weeds…" : "Find weeds"}</Button>
        </form>
        {error && <p role="alert" className="mt-3 font-medium text-stop">{error}</p>}
      </section>
      {result && (
        <section className="border-t border-rule py-[18px]">
          <p className="flex items-center gap-3 text-[22px] font-semibold text-spray">
            <span aria-hidden className="h-3.5 w-3.5 bg-current" />{(100 * result.r.share_flagged).toFixed(1)}% flagged as weeds
          </p>
          <div className="relative my-2.5">
            <img src={result.url} alt="Your photo" className="block w-full" />
            <img src={`data:image/png;base64,${result.r.overlay_png}`} alt="Areas the weed model flagged, in magenta"
                 className="absolute inset-0 h-full w-full" />
          </div>
          <p className="text-[13px] text-muted">DINOv3 features with a head trained on {trained}. A guide for scouting, not a spray map.</p>
        </section>
      )}
    </div>
  );
}
