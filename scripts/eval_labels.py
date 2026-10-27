"""Label reader recall and precision against answer keys. Live, costs credits (cached after the first run).

uv run python scripts/eval_labels.py [evals/labels/<key>.json ...]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# unit -> (base unit, factor)
UNITS = {"ft": ("ft", 1.0), "feet": ("ft", 1.0), "foot": ("ft", 1.0), "m": ("ft", 1 / 0.3048),
         "meters": ("ft", 1 / 0.3048), "mph": ("mph", 1.0), "miles per hour": ("mph", 1.0)}


def _base(rule: dict) -> tuple:
    unit, factor = UNITS.get((rule.get("unit") or "").lower(), (rule.get("unit"), 1.0))
    value = rule.get("value")
    return (None if value is None else value * factor), unit


def matches(pred: dict, key: dict, strict: bool = False) -> bool:
    """Same kind and target; same value within 1% after unit conversion (or, with no value, same page).

    applies_to must be equal; unless strict, 'all' on either side also matches.
    """
    if pred.get("kind") != key["kind"] or pred.get("target") != key.get("target"):
        return False
    same = pred.get("applies_to") == key["applies_to"]
    if not same and (strict or "all" not in (pred.get("applies_to"), key["applies_to"])):
        return False
    (pv, pu), (kv, ku) = _base(pred), _base(key)
    if pv is None or kv is None:  # no number to compare, so it must be the same line of the label
        return pv == kv and pred.get("page") == key.get("page")
    return pu == ku and abs(pv - kv) <= 0.01 * kv


def _pair(preds: list[dict], keys: list[dict]) -> tuple[list, list, list]:
    """One-to-one matching, exact applies_to first so an 'all' rule can't steal a specific one.

    Returns (keys left unmatched, indexes of preds left unmatched, matched (key, pred) pairs)."""
    unused, left, pairs = list(range(len(preds))), list(keys), []
    for strict in (True, False):
        for k in list(left):
            i = next((i for i in unused if matches(preds[i], k, strict)), None)
            if i is not None:
                unused.remove(i)
                left.remove(k)
                pairs.append((k, preds[i]))
    return left, unused, pairs


def score(preds: list[dict], keys: list[dict], also_valid: list[dict] = ()) -> dict:
    """Recall: key rules found. Precision: predictions that are real label rules (key or also_valid)."""
    missed, unused, pairs = _pair(preds, keys)
    _, wrong, valid_pairs = _pair([preds[i] for i in unused], list(also_valid))
    extra = [preds[unused[j]] for j in wrong]
    # a rule with a condition is held back from the plan, so getting this wrong changes the map
    bad_condition = [(k, p) for k, p in pairs + valid_pairs if bool(k.get("conditional")) != bool(p.get("condition"))]
    matched = len(pairs) + len(valid_pairs)
    return {"recall": (len(keys) - len(missed)) / len(keys) if keys else 1.0,
            "precision": (len(preds) - len(extra)) / len(preds) if preds else 1.0,
            "conditions": (matched - len(bad_condition)) / matched if matched else 1.0,
            "found": [k for k in keys if k not in missed], "missed": missed, "extra": extra,
            "bad_condition": bad_condition}


def main(paths: list[str]) -> None:
    from app import label_reader

    paths = paths or sorted(str(p) for p in (ROOT / "evals" / "labels").glob("*.json"))
    for path in paths:
        key = json.loads(Path(path).read_text())
        out = label_reader.read_label(ROOT / key["pdf"])
        preds = [r.model_dump() for r in out.rules if r.kind in key["scored_kinds"]]
        s = score(preds, key["rules"], key.get("also_valid", []))
        flag = "" if key.get("reviewed") else "  (answer key NOT reviewed; don't report)"
        print(f"{key['product_name']}: recall {s['recall']:.0%} ({len(s['found'])}/{len(key['rules'])}), "
              f"precision {s['precision']:.0%} ({len(preds) - len(s['extra'])}/{len(preds)}), "
              f"conditions {s['conditions']:.0%}, {len(out.dropped)} dropped by the quote check{flag}")
        for k in s["missed"]:
            print(f"  missed: {k['kind']} {k.get('target')} {k['applies_to']} {k['value']} {k['unit']} (p{k['page']})")
        for p in s["extra"]:
            print(f"  wrong:  {p['kind']} {p.get('target')} {p['applies_to']} {p['value']} {p['unit']} "
                  f"(p{p['page']}): {p['summary']}")
        for k, p in s["bad_condition"]:
            want = "conditional" if k.get("conditional") else "unconditional"
            print(f"  condition: {p['kind']} {p['value']} {p['unit']} (p{p['page']}) should be {want}, "
                  f"got {p.get('condition')!r}")
        for d in out.dropped:
            print(f"  dropped: {d.get('reason')}: {(d.get('quote') or '')[:90]!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
