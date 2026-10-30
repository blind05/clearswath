"""Builds the demo cache: one real live run per demo field, saved as plan inputs in data/demo/cache/.

uv run python scripts/build_demo.py [--month 2026-11]

Needs the network and MODEL_API_KEY (SAM, label read, NAIP, USGS, BLT). Commit data/demo/cache afterwards;
/api/demo then works offline and recomputes the plan from these inputs on every request.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import bulletins, geo, label_reader, pipeline, segment  # noqa: E402

DEMO = ROOT / "data" / "demo"

ap = argparse.ArgumentParser()
ap.add_argument("--month", default="2026-11")
month = ap.parse_args().month

label_path = DEMO / "label.pdf"
# Muse Spark 1.3 reads the demo label. Spark Open on Baseten (live runs' default) read the 450 ft ULV-only buffer as
# applying always in 3 of 3 reads (evals/results_labels.md): stricter, never looser, but the rule can't be unticked.
raw = label_reader.read_raw(label_path, provider="meta")
label = label_reader.verify(raw)
print(f"label: {label.product_name} ({label.epa_reg_no}), {len(label.rules)} rules, {len(label.dropped)} dropped")
for name in ("field", "field_corrected"):
    path = DEMO / f"{name}.geojson"
    hazards = segment.find_hazards(path)
    bulletin = bulletins.check_bulletin(path, month, label.epa_reg_no)
    if not bulletin["checked"]:
        sys.exit(f"{name}: bulletin check failed ({bulletin['citation']}); not caching a failed check")
    pipeline.save_inputs(DEMO / "cache" / name, geo.load_field(path), raw, hazards, bulletin, month)
    plan = pipeline.assemble(geo.load_field(path), label, hazards, bulletin, month, "drone")["plan"]
    print(f"{name}: water {len(hazards['water'])} ({hazards['water_source']}), buildings {len(hazards['building'])}, "
          f"habitat {len(hazards['habitat'])}, imagery {hazards['imagery_date']}, BLT in_pula={bulletin['in_pula']} "
          f"-> drone {plan['status']} {plan['spray_acres']}/{plan['field_acres']} ac")
