import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("eval_labels", ROOT / "scripts" / "eval_labels.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def rule(**kw):
    return {"kind": "buffer", "target": "water", "applies_to": "aerial", "value": 150, "unit": "ft"} | kw


@pytest.mark.parametrize("pred, ok", [
    (rule(), True),
    (rule(unit="feet"), True),
    (rule(value=45.72, unit="m"), True),  # 150 ft in metres
    (rule(applies_to="all"), True),
    (rule(applies_to="ground"), False),
    (rule(value=450), False),
    (rule(target="building"), False),
    (rule(kind="wind", target=None, value=150, unit="mph"), False),
])
def test_matches(pred, ok):
    assert ev.matches(pred, rule()) is ok


def test_score_is_one_to_one():
    keys = [rule(), rule(value=450)]
    s = ev.score([rule(), rule(), rule(value=25)], keys)
    assert s["recall"] == 0.5 and s["missed"] == [rule(value=450)]
    assert s["precision"] == pytest.approx(1 / 3) and len(s["extra"]) == 2


def test_exact_applies_to_wins_over_all():
    # an 'all' prediction must not steal the key's 'ground' rule from the exact 'ground' prediction
    keys = [rule(applies_to="ground", value=25), rule(applies_to="all", value=25)]
    preds = [rule(applies_to="all", value=25), rule(applies_to="ground", value=25)]
    s = ev.score(preds, keys)
    assert s["recall"] == 1.0 and s["precision"] == 1.0


def test_also_valid_counts_for_precision_only():
    keys = [rule()]
    ny = rule(applies_to="all", value=25)
    s = ev.score([rule(), ny, rule(value=7, kind="rain", target=None, unit="days")], keys, [ny])
    assert s["recall"] == 1.0 and s["precision"] == pytest.approx(2 / 3)
    assert [p["kind"] for p in s["extra"]] == ["rain"]


def test_score_empty():
    assert ev.score([], [])["recall"] == 1.0 and ev.score([], [rule()])["recall"] == 0.0


def test_answer_keys_are_well_formed():
    """Every key rule fits the reader's schema and its quote is really in the label."""
    import pymupdf

    from app import label_reader

    keys = list((ROOT / "evals" / "labels").glob("*.json"))
    assert keys
    for path in keys:
        key = json.loads(path.read_text())
        with pymupdf.open(ROOT / key["pdf"]) as doc:
            pages = [p.get_text() for p in doc]
        for r in key["rules"] + key.get("also_valid", []):
            assert r["kind"] in label_reader.KINDS and r["applies_to"] in ("all", "aerial", "ground")
            assert r["kind"] in key["scored_kinds"] or r in key.get("also_valid", [])
            norm = label_reader._norm(r["quote"])
            assert norm in label_reader._norm(pages[r["page"] - 1]), (path.name, r["quote"][:60])
