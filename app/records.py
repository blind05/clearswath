"""Voice or typed notes + the planned job -> pesticide application record."""

from datetime import date
from pathlib import Path

from pydantic import BaseModel

from app import llm

# USDA restricted-use pesticide recordkeeping items. States may require more.
REQUIRED = ["applicator_name", "certification_number", "application_date", "product_name",
            "epa_reg_no", "amount_applied", "area_treated_acres", "crop_or_site", "location"]
# What the notes can supply; the rest comes from the job.
FROM_NOTES = {
    "applicator_name": "string", "certification_number": "string", "application_date": "string",
    "start_time": "string", "end_time": "string", "amount_applied": "string", "rate": "string",
    "crop_or_site": "string", "wind_speed_mph": "number", "wind_direction": "string",
    "temperature_f": "number", "notes": "string",
}
SCHEMA = {
    "type": "object",
    "properties": {k: {"type": [t, "null"]} for k, t in FROM_NOTES.items()},
    "required": list(FROM_NOTES),
    "additionalProperties": False,
}


class AppRecord(BaseModel):
    applicator_name: str | None = None
    certification_number: str | None = None
    application_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    product_name: str | None = None
    epa_reg_no: str | None = None
    amount_applied: str | None = None
    rate: str | None = None
    area_treated_acres: float | None = None
    crop_or_site: str | None = None
    location: str | None = None
    method: str | None = None
    wind_speed_mph: float | None = None
    wind_direction: str | None = None
    temperature_f: float | None = None
    notes: str | None = None
    transcript: str = ""
    missing: list[str] = []


def transcribe(path: str | Path) -> str:
    return llm.transcribe(path, purpose="record")


def fill_record(text: str, job: dict, today: date | None = None) -> AppRecord:
    """job: product_name, epa_reg_no, area_treated_acres, location, method from the plan. Job values win."""
    today = today or date.today()
    found = llm.chat_json([{"role": "system", "content": llm.load_prompt("record")},
                           {"role": "user", "content": f"Today is {today.isoformat()}.\n\nNotes:\n{text}"}],
                          SCHEMA, "app_record", purpose="record")
    fields = {k: v for k, v in found.items() if k in FROM_NOTES and v not in (None, "")}
    fields |= {k: v for k, v in job.items() if k in AppRecord.model_fields and v not in (None, "")}
    record = AppRecord(**fields, transcript=text)
    record.missing = [k for k in REQUIRED if getattr(record, k) in (None, "")]
    return record
