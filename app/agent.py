"""Muse Spark agent over the pipeline steps. The model picks steps and explains; buffers.plan decides."""

import json
import logging
import re
import time
import uuid
from pathlib import Path

from app import bulletins, geo, label_reader, llm, pipeline, segment

log = logging.getLogger(__name__)
RUNS = Path(__file__).resolve().parent.parent / "data" / "runs"
MAX_STEPS = 8
STATUS_WORDS = re.compile(r"\b(NO-GO|GO|ADJUST)\b")
LABELS = {"go": "GO", "adjust": "ADJUST", "no-go": "NO-GO"}

# No arguments on purpose: the model chooses steps, never files, products or months.
TOOLS = [{"type": "function", "function": {"name": name, "description": desc,
                                           "parameters": {"type": "object", "properties": {}}}}
         for name, desc in [
             ("read_label", "Read the pesticide label and return its verified rules."),
             ("find_hazards", "Find water, buildings and habitat near the field."),
             ("check_bulletin", "Check EPA Bulletins Live! Two for this product, field and month."),
             ("plan_spray", "Compute the legal spray zone and the GO / ADJUST / NO-GO decision."),
         ]]


class _ModelError(Exception):
    """The model call failed (as opposed to a tool, whose errors propagate like pipeline.run's)."""


class _Job:
    """The run's state; each tool fills one part, and plan_spray fills in anything still missing."""

    def __init__(self, field_path, label_path, month, method):
        self.field_path, self.label_path, self.month, self.method = field_path, label_path, month, method
        self.label = self.hazards = self.bulletin = self.result = None

    def read_label(self):
        self.label = self.label or label_reader.read_label(self.label_path)
        return {"product": self.label.product_name, "epa_reg_no": self.label.epa_reg_no,
                "rules": [r.summary for r in self.label.rules], "unverified_rules": len(self.label.dropped)}

    def find_hazards(self):
        self.hazards = self.hazards or segment.find_hazards(self.field_path)
        return {k: len(self.hazards.get(k) or []) for k in ("water", "building", "habitat")} | {
            "imagery_date": self.hazards.get("imagery_date"), "water_source": self.hazards.get("water_source")}

    def check_bulletin(self):
        if self.bulletin is None:
            self.read_label()
            self.bulletin = bulletins.check_bulletin(self.field_path, self.month, self.label.epa_reg_no)
        return {k: v for k, v in self.bulletin.items() if k != "restricted"}

    def plan_spray(self):
        self.find_hazards()
        self.check_bulletin()  # reads the label too
        self.result = self.result or pipeline.assemble(geo.load_field(self.field_path), self.label,
                                                       self.hazards, self.bulletin, self.month, self.method)
        plan = self.result["plan"]
        return {"decision": LABELS[plan["status"]], "field_acres": plan["field_acres"],
                "spray_acres": plan["spray_acres"], "excluded_acres": plan["excluded_acres"],
                "reasons": plan["reasons"], "warnings": self.result["warnings"]}


def _template(result: dict) -> str:
    """Answer written without a model, from the plan alone."""
    plan = result["plan"]
    lines = [f"{LABELS[plan['status']]}: {plan['spray_acres']} of {plan['field_acres']} acres can be sprayed."]
    lines += [f"- {r.get('summary', '')}" + (f' (label p.{r["page"]}: "{r["quote"]}")' if r.get("quote") else "")
              for r in plan["reasons"]]
    lines += [f"Warning: {w}" for w in result["warnings"]]
    return "\n".join(lines)


def _agent_loop(job: _Job, trace: list) -> str | None:
    messages = [{"role": "system", "content": llm.load_prompt("agent")},
                {"role": "user", "content": f"Can I spray this field by {job.method} in {job.month}?"}]
    for _ in range(MAX_STEPS):
        try:
            msg = llm.chat(messages, tools=TOOLS, purpose="agent")
        except Exception as e:  # any model failure falls back to the pipeline
            raise _ModelError() from e
        if not msg.tool_calls:
            return msg.content
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name,
                                                          "arguments": c.function.arguments or "{}"}}
            for c in msg.tool_calls]})
        for call in msg.tool_calls:
            name, start = call.function.name, time.perf_counter()
            tool = getattr(job, name) if name in {t["function"]["name"] for t in TOOLS} else None
            out = tool() if tool else {"error": f"unknown tool {name}"}
            trace.append({"tool": name, "result": out, "seconds": round(time.perf_counter() - start, 2)})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out, default=str)})
    trace.append({"note": f"stopped after {MAX_STEPS} steps"})
    return None


def run(field_path, label_path, month: str, method: str = "drone") -> dict:
    """result is the full pipeline result (as pipeline.run returns), for pipeline.to_json."""
    run_id = uuid.uuid4().hex
    job, trace, mode = _Job(field_path, label_path, month, method), [], "agent"
    try:
        answer = _agent_loop(job, trace)
    except _ModelError as e:
        log.warning("agent model call failed; falling back to pipeline", exc_info=e.__cause__)
        # type name only: the error text can carry upstream response details
        trace.append({"note": f"agent unavailable ({type(e.__cause__).__name__}); ran the pipeline instead"})
        answer, mode = None, "pipeline"

    if job.result is None:
        job.plan_spray()
        trace.append({"tool": "plan_spray", "note": "run by ClearSwath; the agent did not call it"})
    decision = job.result["plan"]["status"]

    claimed = set(STATUS_WORDS.findall(answer or ""))
    if answer and claimed - {LABELS[decision]}:
        trace.append({"note": f"agent answer said {sorted(claimed)}; replaced, the plan says {LABELS[decision]}"})
        answer = None
    pipeline.save_run(job.result, RUNS / run_id)
    return {"run_id": run_id, "answer": answer or _template(job.result), "decision": decision,
            "trace": trace, "mode": mode, "result": job.result}
