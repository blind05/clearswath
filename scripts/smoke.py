"""Live check against api.meta.ai. Uses the network and your key: `uv run python scripts/smoke.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm  # noqa: E402

ids = {m.id for m in llm.client().models.list()}  # TODO(verify): models endpoint on api.meta.ai
print(f"{len(ids)} models available")
missing = [m for m in (llm.SPARK, llm.SAM, llm.VOICE) if m not in ids]
for m in (llm.SPARK, llm.SAM, llm.VOICE):
    print(f"  {m}: {'ok' if m not in missing else 'MISSING'}")

reply = llm.chat([{"role": "user", "content": 'Reply with exactly "OK".'}], purpose="smoke").content
print(f"chat: {reply!r}")

schema = {"type": "object", "properties": {"answer": {"type": "integer"}},
          "required": ["answer"], "additionalProperties": False}
out = llm.chat_json([{"role": "user", "content": "What is 2 + 2?"}], schema, "sum", purpose="smoke")
print(f"chat_json: {out}")

ok = not missing and "OK" in (reply or "") and out.get("answer") == 4
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
