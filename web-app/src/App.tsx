import { useCallback, useRef, useState } from "react";
import * as stylex from "@stylexjs/stylex";
import { Button } from "@astryxdesign/core/Button";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { json, post } from "@/api";
import { AccessCode } from "@/components/AccessCode";
import { type Drawing, MapView } from "@/components/MapView";
import { PhotoPanel } from "@/components/PhotoPanel";
import { PlanView } from "@/components/PlanView";
import { type Setup, SetupForm } from "@/components/SetupForm";
import { text } from "@/styles";
import { color, media } from "@/tokens.stylex";
import type { Plan } from "@/types";

const s = stylex.create({
  shell: { display: "flex", flexDirection: "column", height: "100%" },
  header: {
    display: "flex", alignItems: "center", gap: { default: 28, [media.mobile]: 8 }, height: 52, flex: "none",
    paddingInline: { default: 20, [media.mobile]: 12 }, backgroundColor: color.panel,
    borderBottomWidth: 1, borderBottomStyle: "solid", borderBottomColor: color.rule,
  },
  brand: { display: "flex", alignItems: "center", gap: 10 },
  name: { fontSize: { default: 18, [media.mobile]: 16 }, fontWeight: 600, letterSpacing: "-0.01em" },
  tagline: { marginLeft: "auto", display: { default: "block", [media.mobile]: "none" } },
  main: {
    display: { default: "grid", [media.mobile]: "flex" }, gridTemplateColumns: "400px 1fr",
    flexDirection: "column", flex: 1, minHeight: 0, overflowY: { default: null, [media.mobile]: "auto" },
  },
  aside: {
    overflowY: { default: "auto", [media.mobile]: "visible" }, backgroundColor: color.panel,
    paddingInline: { default: 24, [media.mobile]: 16 }, paddingBottom: 40,
    borderRightWidth: { default: 1, [media.mobile]: 0 }, borderRightStyle: "solid", borderRightColor: color.rule,
  },
  welcome: { paddingTop: 28, paddingBottom: 22, borderBottomWidth: 1, borderBottomStyle: "solid", borderBottomColor: color.rule },
  welcomeTitle: { fontSize: { default: 28, [media.mobile]: 24 }, lineHeight: 1.15, fontWeight: 600, letterSpacing: "-0.01em" },
  welcomeBody: { color: color.muted, fontSize: 15, lineHeight: 1.5, marginTop: 10, maxWidth: 340 },
  welcomeAction: { marginTop: 16 },
  // phone: the map goes first by order, not column-reverse, which starts a scroller at its end (map scrolled away)
  map: { minHeight: 0, height: { default: null, [media.mobile]: "55vh" }, flex: { default: null, [media.mobile]: "none" },
         order: { default: null, [media.mobile]: -1 } },
});

type Rerun = (excluded: number[]) => Promise<Plan>;

export function App() {
  const [setup, setSetup] = useState<Setup>({
    fieldFile: null, labelFile: null, month: new Date().toISOString().slice(0, 7), method: "drone", windFrom: "", agent: false,
  });
  const [drawing, setDrawing] = useState<Drawing>({ field: null, managed: [] });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);  // the welcome leads; the form opens from its heading
  const [tab, setTab] = useState("plan");
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
    <div {...stylex.props(s.shell)}>
      <header {...stylex.props(s.header)}>
        <div {...stylex.props(s.brand)}>
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <rect x="1" y="1" width="20" height="20" fill="none" stroke="#1E2B24" strokeWidth="2" />
            <rect x="6" y="1" width="5" height="20" fill="#C4127A" />
          </svg>
          <h1 {...stylex.props(s.name)}>ClearSwath</h1>
        </div>
        <TabList role="tablist" value={tab} onChange={setTab} aria-label="Mode">
          <Tab value="plan" label="Plan a spray" panelId="panel-plan" />
          <Tab value="photo" label="Check a photo" panelId="panel-photo" />
        </TabList>
        <p {...stylex.props(text.small, s.tagline)}>Find the weeds. Read the label. Spray only where both say yes.</p>
      </header>
      <main {...stylex.props(s.main)}>
        <aside id={`panel-${tab}`} role="tabpanel" aria-label={tab === "plan" ? "Plan a spray" : "Check a photo"} {...stylex.props(s.aside)}>
          {tab === "plan" ? (
            <>
              {!plan && (
                <section {...stylex.props(s.welcome)} aria-labelledby="welcome-title">
                  <h2 id="welcome-title" {...stylex.props(s.welcomeTitle)}>Spray the weeds, not the creek.</h2>
                  <p {...stylex.props(s.welcomeBody)}>
                    A 24-acre Montana block: leafy spurge mapped from a drone, the Tordon 22K label read page by page,
                    and the spray cells that are left. A saved run, so it opens in seconds.
                  </p>
                  <div {...stylex.props(s.welcomeAction)}>
                    <Button id="explore" variant="primary" label="Explore the Montana example" isDisabled={busy}
                            onClick={() => { demoField.current = "mt"; run(demo); }} />
                  </div>
                </section>
              )}
              <SetupForm setup={setup} onChange={setSetup} open={formOpen} onOpenChange={setFormOpen}
                         fieldDrawn={!!drawing.field} managedCount={drawing.managed.length} busy={busy}
                         onPlan={planLive} onDemo={() => { demoField.current = "mt"; run(demo); }} />
              {busy && <p {...stylex.props(text.small)}>Reading the label, mapping hazards and checking the bulletin…</p>}
              {error && <p role="alert" {...stylex.props(text.error)}>{error}</p>}
              {plan && <PlanView plan={plan} agentAsked={setup.agent} onAskLive={askLive} onSwitchDemo={switchDemo}
                                 onUntick={(excluded) => rerun.current && run(rerun.current, excluded)} />}
            </>
          ) : <PhotoPanel />}
        </aside>
        <div {...stylex.props(s.map)}>
          <MapView plan={plan} onDrawing={setDrawing} clearDrawing={0} />
        </div>
      </main>
      <AccessCode />
    </div>
  );
}
