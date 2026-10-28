import json
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import box, mapping

from app import agent, bulletins, label_reader, llm, segment
from app.label_reader import LabelRule, LabelRules

X, Y = 500_000, 4_650_000
FIELD, POND = gpd.GeoSeries([box(X, Y, X + 400, Y + 400), box(X + 410, Y + 150, X + 460, Y + 250)],
                            crs=32615).to_crs(4326)
RULE = LabelRule(kind="buffer", target="water", applies_to="all", value=100, unit="ft",
                 summary="100 ft from water", quote="Do not apply within 100 feet of water.", page=2)
LABEL = LabelRules(product_name="Acme", epa_reg_no="123-45", rules=[RULE], dropped=[], source="pdf")
BULLETIN = {"in_pula": False, "prohibited": False, "limitations": [], "restricted": [],
            "citation": "EPA BLT: no PULA applies.", "checked": True}


@pytest.fixture
def field_path(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "RUNS", tmp_path / "runs")
    p = tmp_path / "field.geojson"
    p.write_text(json.dumps(mapping(FIELD)))
    return p


@pytest.fixture
def steps(monkeypatch):
    calls = []
    monkeypatch.setattr(label_reader, "read_label", lambda p, provider=None: calls.append("label") or LABEL)
    monkeypatch.setattr(segment, "find_hazards", lambda p: calls.append("hazards") or {
        "water": [POND], "building": [], "habitat": [], "imagery_date": "2023-07-09", "water_source": "usgs"})
    monkeypatch.setattr(bulletins, "check_bulletin", lambda fp, m, reg: calls.append(("bulletin", reg)) or BULLETIN)
    return calls


def call(name, i=0):
    return SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name=name, arguments="{}"))


def reply(*tool_calls, content=None):
    return SimpleNamespace(content=content, tool_calls=list(tool_calls) or None)


def script(monkeypatch, *replies):
    seen = []

    def chat(messages, tools=None, **kw):
        seen.append([dict(m) for m in messages])
        return replies[len(seen) - 1]

    monkeypatch.setattr(llm, "chat", chat)
    return seen


def test_agent_path(field_path, steps, monkeypatch):
    seen = script(monkeypatch,
                  reply(call("read_label", 0), call("find_hazards", 1)),
                  reply(call("check_bulletin", 2)),
                  reply(call("plan_spray", 3)),
                  reply(content="ADJUST: about 39 acres can be sprayed; stay 100 ft from the pond."))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["mode"] == "agent" and out["decision"] == "adjust"
    assert out["answer"].startswith("ADJUST: about 39")
    assert [t["tool"] for t in out["trace"]] == ["read_label", "find_hazards", "check_bulletin", "plan_spray"]
    assert steps == ["label", "hazards", ("bulletin", "123-45")]  # each step ran once
    tool_msg = seen[3][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["decision"] == "ADJUST"
    assert (agent.RUNS / out["run_id"] / "job.json").exists()  # KML and records work for agent runs


def test_plan_runs_even_if_agent_skips_it(field_path, steps, monkeypatch):
    script(monkeypatch, reply(content="Looks fine to spray."))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["decision"] == "adjust" and out["answer"] == "Looks fine to spray."
    assert out["trace"][-1]["note"].startswith("run by ClearSwath")


def test_contradicting_answer_is_replaced(field_path, steps, monkeypatch):
    script(monkeypatch, reply(call("plan_spray")), reply(content="GO: spray the whole field."))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["decision"] == "adjust" and out["answer"].startswith("ADJUST:")
    assert "100 feet of water" in out["answer"]
    assert "replaced" in out["trace"][-1]["note"]


@pytest.mark.parametrize("text", ["ADJUST: the green zone is legal to spray.", "ADJUST: safe to spray 30 acres.",
                                  "ADJUST: this plan is fully compliant."])
def test_answer_claiming_legal_or_safe_is_replaced(field_path, steps, monkeypatch, text):
    script(monkeypatch, reply(call("plan_spray")), reply(content=text))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["answer"].startswith("ADJUST:") and out["answer"] != text
    assert "replaced with the plan's own summary" in out["trace"][-1]["note"]


def test_go_summary_says_no_conflicts_in_checked_rules():
    plan = {"status": "go", "spray_acres": 31.2, "field_acres": 31.2, "reasons": []}
    assert agent._template({"plan": plan, "warnings": []}).startswith("GO: No conflicts in checked rules. 31.2 of")


def test_model_failure_falls_back(field_path, steps, monkeypatch, caplog):
    def boom(*a, **kw):
        raise RuntimeError("upstream said: secret-ish details")

    monkeypatch.setattr(llm, "chat", boom)
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["mode"] == "pipeline" and out["decision"] == "adjust" and out["answer"].startswith("ADJUST:")
    assert "RuntimeError" in out["trace"][0]["note"]
    assert "secret-ish" not in json.dumps(out["trace"]) and "secret-ish" in caplog.text


def test_tool_errors_propagate(field_path, steps, monkeypatch):
    def no_imagery(p):
        raise LookupError("No NAIP imagery")

    monkeypatch.setattr(segment, "find_hazards", no_imagery)
    script(monkeypatch, reply(call("find_hazards")))
    with pytest.raises(LookupError):
        agent.run(field_path, "label.pdf", "2026-11")


def test_step_cap_and_unknown_tool(field_path, steps, monkeypatch):
    script(monkeypatch, *[reply(call("delete_field"))] * agent.MAX_STEPS)
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["trace"][0]["result"] == {"error": "unknown tool delete_field"}
    assert any("stopped after" in t.get("note", "") for t in out["trace"])
    assert out["answer"].startswith("ADJUST:")


def test_returns_full_result(field_path, steps, monkeypatch):
    script(monkeypatch, reply(content="ok"))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert out["result"]["plan"]["status"] == out["decision"] and out["result"]["label"] is LABEL


def test_user_exclusions_reach_the_plan(field_path, steps, monkeypatch):
    ulv = RULE.model_copy(update={"value": 2000.0, "condition": "ULV aerial only"})
    monkeypatch.setattr(label_reader, "read_label", lambda p, provider=None: LABEL.model_copy(update={"rules": [RULE, ulv]}))
    script(monkeypatch, reply(call("plan_spray")), reply(content="ok"))
    assert agent.run(field_path, "label.pdf", "2026-11")["decision"] == "no-go"
    script(monkeypatch, reply(call("plan_spray")), reply(content="ok"))
    assert agent.run(field_path, "label.pdf", "2026-11", excluded_rules=[1])["decision"] == "adjust"


def test_provider_reaches_reader_and_model(field_path, steps, monkeypatch):
    seen = {}
    monkeypatch.setattr(label_reader, "read_label", lambda p, provider=None: seen.update(reader=provider) or LABEL)

    def chat(messages, tools=None, provider=None, **kw):
        seen.setdefault("chat", []).append(provider)
        return reply(content="ok") if len(seen["chat"]) > 1 else reply(call("read_label"))

    monkeypatch.setattr(llm, "chat", chat)
    agent.run(field_path, "label.pdf", "2026-11", provider="baseten")
    assert seen == {"reader": "baseten", "chat": ["baseten", "baseten"]}


def test_agent_refuses_a_bad_field_before_any_tool(monkeypatch, tmp_path):
    from app import geo

    p = tmp_path / "huge.geojson"
    p.write_text(json.dumps(mapping(box(-103.0, 43.0, -96.5, 45.9))))
    monkeypatch.setattr(llm, "chat", lambda *a, **kw: pytest.fail("model called"))
    with pytest.raises(geo.FieldError):
        agent.run(p, "label.pdf", "2026-11")


@pytest.mark.parametrize("text, kept", [
    ('ADJUST: the label says "Do not apply within 100 feet of water."', True),
    ('ADJUST: the label says "apply within 100 feet" so keep back.', True),  # an exact part of the quote
    ('ADJUST: the label says "Never spray within 100 feet of a pond."', False),  # a paraphrase in quotes
    ('ADJUST: keep "100 ft" back.', True),  # too short to be passed off as label text
])
def test_quoted_text_must_be_on_the_label(field_path, steps, monkeypatch, text, kept):
    script(monkeypatch, reply(call("plan_spray")), reply(content=text))
    out = agent.run(field_path, "label.pdf", "2026-11")
    assert (out["answer"] == text) is kept
    if not kept:
        assert "not on the label" in out["trace"][-1]["note"]
