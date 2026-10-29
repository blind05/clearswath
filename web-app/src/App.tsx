import { useCallback, useRef, useState } from "react";
import { json, post } from "@/api";
import { AccessCode } from "@/components/AccessCode";
import { type Drawing, MapView } from "@/components/MapView";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PlanView } from "@/components/PlanView";
import { type Setup, SetupForm } from "@/components/SetupForm";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Plan } from "@/types";

type Rerun = (excluded: number[]) => Promise<Plan>;

export function App() {
  const [setup, setSetup] = useState<Setup>({
    fieldFile: null, labelFile: null, month: new Date().toISOString().slice(0, 7), method: "drone", windFrom: "", agent: false,
  });
  const [drawing, setDrawing] = useState<Drawing>({ field: null, managed: [] });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(true);
  const rerun = useRef<Rerun | null>(null);
  const demoField = useRef("mt");

  const run = useCallback(async (r: Rerun, excluded: number[] = []) => {
    rerun.current = r;
    setBusy(true); setError("");
    try { setPlan(await r(excluded)); setFormOpen(false); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }, []);

  const demo: Rerun = (excluded) => json<Plan>(`/api/demo?${new URLSearchParams({
    field: demoField.current, method: setup.method, month: setup.month, wind_from: setup.windFrom,
    excluded_rules: excluded.join(","), ...(setup.agent ? { agent_answer: "1" } : {}),
  })}`);

  function planLive() {
    const field = drawing.field
      ? new File([JSON.stringify(drawing.field)], "drawn.geojson", { type: "application/geo+json" })
      : setup.fieldFile;
    if (!field) return setError("Draw the field on the map or choose a GeoJSON file, then plan again.");
    if (!setup.labelFile) return setError("Choose the pesticide label, as a PDF or a photo.");
    const label = setup.labelFile;
    run((excluded) => {
      const body = new FormData();
      body.append("field", field);
      body.append("label", label);
      body.append("month", setup.month);
      body.append("method", setup.method);
      body.append("wind_from", setup.windFrom);
      body.append("excluded_rules", excluded.join(","));
      if (drawing.managed.length) body.append("managed", JSON.stringify({ type: "FeatureCollection", features: drawing.managed }));
      return post<Plan>(setup.agent ? "/api/agent" : "/api/plan", body);
    });
  }

  function switchDemo() {
    const fromMontana = demoField.current === "mt";  // a different label, so its unticked rule ids don't carry over
    demoField.current = demoField.current === "" ? "corrected" : "";
    run(demo, fromMontana ? [] : (plan?.confirm.filter((c) => !c.applied).map((c) => c.id) ?? []));
  }

  function askLive() {
    const body = new FormData();
    body.append("field", demoField.current);
    body.append("method", setup.method);
    body.append("excluded_rules", (plan?.excluded_rules ?? []).join(","));
    run(() => post<Plan>("/api/demo/agent", body));
  }

  return (
    <Tabs defaultValue="plan" className="flex h-full flex-col gap-0">
      <header className="flex h-[52px] flex-none items-center gap-7 border-b border-rule bg-panel px-5 max-md:gap-2 max-md:px-3">
        <div className="flex items-center gap-2.5">
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <rect x="1" y="1" width="20" height="20" fill="none" stroke="#1E2B24" strokeWidth="2" />
            <rect x="6" y="1" width="5" height="20" fill="#C4127A" />
          </svg>
          <h1 className="text-[18px] font-semibold tracking-[-0.01em] max-md:text-[16px]">ClearSwath</h1>
        </div>
        <TabsList className="h-full gap-1 rounded-none bg-transparent p-0">
          <TabsTrigger value="plan" className="h-full rounded-none border-0 border-b-2 border-transparent px-3 font-medium text-muted shadow-none data-[state=active]:border-ink data-[state=active]:text-ink data-[state=active]:shadow-none max-md:px-2">Plan a spray</TabsTrigger>
          <TabsTrigger value="photo" className="h-full rounded-none border-0 border-b-2 border-transparent px-3 font-medium text-muted shadow-none data-[state=active]:border-ink data-[state=active]:text-ink data-[state=active]:shadow-none max-md:px-2">Check a photo</TabsTrigger>
        </TabsList>
        <p className="ml-auto text-[13px] text-muted max-md:hidden">Find the weeds. Read the label. Spray only where both say yes.</p>
      </header>
      <main className="grid min-h-0 flex-1 grid-cols-[400px_1fr] max-md:flex max-md:flex-col-reverse max-md:overflow-y-auto">
        <aside className="overflow-y-auto border-r border-rule bg-panel px-6 pb-10 max-md:overflow-visible max-md:border-r-0 max-md:px-4">
          <TabsContent value="plan">
            <SetupForm setup={setup} onChange={setSetup} open={formOpen} onOpenChange={setFormOpen}
                       fieldDrawn={!!drawing.field} managedCount={drawing.managed.length} busy={busy}
                       onPlan={planLive} onDemo={() => { demoField.current = "mt"; run(demo); }} />
            {busy && <p className="text-[13px] text-muted">Reading the label, mapping hazards and checking the bulletin…</p>}
            {error && <p role="alert" className="pt-3 font-medium text-stop">{error}</p>}
            {plan && <PlanView plan={plan} agentAsked={setup.agent} onAskLive={askLive} onSwitchDemo={switchDemo}
                               onUntick={(excluded) => rerun.current && run(rerun.current, excluded)} />}
          </TabsContent>
          <TabsContent value="photo"><PhotoPanel /></TabsContent>
        </aside>
        <div className="min-h-0 max-md:h-[55vh] max-md:flex-none">
          <MapView plan={plan} onDrawing={setDrawing} clearDrawing={0} />
        </div>
      </main>
      <AccessCode />
    </Tabs>
  );
}
