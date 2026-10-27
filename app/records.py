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
    # FAA Part 137 (14 CFR 137.71) items the plan can't know
    "customer_name": "string", "customer_address": "string", "pilot_name": "string", "pilot_address": "string",
    "pilot_certificate_number": "string", "pilot_knowledge_test_date": "string",
}
PART137_FROM_NOTES = ["customer_name", "customer_address", "pilot_name", "pilot_address",
                      "pilot_certificate_number", "pilot_knowledge_test_date"]
AIR_METHODS = {"drone", "aerial"}
SCHEMA = {
    "type": "object",
    "properties": {k: {"type": [t, "null"]} for k, t in FROM_NOTES.items()},
    "required": list(FROM_NOTES),
    "additionalProperties": False,
}


class Part137(BaseModel):
    """14 CFR 137.71: records a commercial agricultural aircraft operator keeps at its home base for 12 months."""
    customer_name: str | None = None  # person the service was provided for
    customer_address: str | None = None
    service_date: str | None = None
    material: str | None = None  # name of the material dispensed
    quantity: str | None = None
    pilot_name: str | None = None
    pilot_address: str | None = None
    pilot_certificate_number: str | None = None  # FAA certificate, not the state applicator certification
    pilot_knowledge_test_date: str | None = None  # date the pilot met 137.19(e)
    missing: list[str] = []


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
    part137: Part137 | None = None  # drone and aerial jobs only


def transcribe(path: str | Path) -> str:
    return llm.transcribe(path, purpose="record")


def fill_record(text: str, job: dict, today: date | None = None) -> AppRecord:
    """job: product_name, epa_reg_no, area_treated_acres, location, method from the plan. Job values win."""
    today = today or date.today()
    found = llm.chat_json([{"role": "system", "content": llm.load_prompt("record")},
                           {"role": "user", "content": f"Today is {today.isoformat()}.\n\nNotes:\n{text}"}],
                          SCHEMA, "app_record", purpose="record")
    found = {k: v for k, v in found.items() if k in FROM_NOTES and v not in (None, "")}
    fields = {k: v for k, v in found.items() if k in AppRecord.model_fields}
    fields |= {k: v for k, v in job.items() if k in AppRecord.model_fields and v not in (None, "")}
    record = AppRecord(**fields, transcript=text)
    record.missing = [k for k in REQUIRED if getattr(record, k) in (None, "")]
    if record.method in AIR_METHODS:
        material = record.product_name and (f"{record.product_name} (EPA Reg. No. {record.epa_reg_no})"
                                            if record.epa_reg_no else record.product_name)
        p137 = Part137(**{k: found.get(k) for k in PART137_FROM_NOTES}, service_date=record.application_date,
                       material=material, quantity=record.amount_applied)
        p137.missing = [k for k in Part137.model_fields if k != "missing" and getattr(p137, k) in (None, "")]
        record.part137 = p137
    return record
