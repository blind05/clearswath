"""Estimated model spend per UTC day, for the live-run budget. Bookkeeping only: no network, no model.

llm.log_call reports every call here; api.paid_access refuses live runs once today's total reaches the budget.
An estimate, not a bill: it errs high, and a restart on a host without a persistent disk starts the day at 0.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "logs" / "spend.json"
# USD per million input / output tokens.
# TODO(verify): $1.25 / $4.25 is from price trackers citing Meta's docs and Fireworks, not the providers' own
# pages; Baseten's rate is unknown and assumed the same.
TOKEN_PRICES = {
    "muse-spark-1.3": (1.25, 4.25),
    "accounts/fireworks/models/muse-spark-open": (1.25, 4.25),
    "meta-models/muse-spark-open-1026": (1.25, 4.25),
}
# USD per call where no token price is published. TODO(verify): no public price found; set high on purpose.
CALL_PRICES = {"sam-3.1": 0.01, "muse-voice-transcribe-1.0": 0.02}
UNKNOWN = (5.0, 15.0)  # an unlisted model is costed high, so the budget stops early rather than late
NO_USAGE = 0.05  # USD for a token-priced call that reports no usage: never free, or the budget would leak
_lock = threading.Lock()
log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def cost(model: str, usage) -> float:
    """USD for one call. usage: the provider's usage object or dict (chat or Responses API field names)."""
    if model in CALL_PRICES:
        return CALL_PRICES[model]
    usage = usage.model_dump() if hasattr(usage, "model_dump") else (usage or {})
    tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    tokens_out = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    if not (tokens_in or tokens_out):
        log.warning("no token usage reported for %s; charging %.2f USD", model, NO_USAGE)
        return NO_USAGE
    price_in, price_out = TOKEN_PRICES.get(model, UNKNOWN)
    return (tokens_in * price_in + tokens_out * price_out) / 1e6


def _load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def record(model: str, usage) -> float:
    """Adds one call to today's total; returns the call's cost. Only today's total is kept."""
    usd = cost(model, usage)
    with _lock:
        day, totals = _today(), _load()
        total = (totals.get(day) or 0.0) + usd
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_text(json.dumps({day: round(total, 6)}))
    return usd


def today() -> float:
    """Estimated USD spent today (UTC)."""
    with _lock:
        return float(_load().get(_today()) or 0.0)
