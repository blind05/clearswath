from datetime import date

from app import llm, records

JOB = {"product_name": "INTREPID 2F", "epa_reg_no": "62719-442", "area_treated_acres": 35.5,
       "location": "42.0050, -92.9950", "method": "drone"}


def fake_model(monkeypatch, **found):
    seen = {}

    def chat_json(messages, schema, name, **kw):
        seen["user"] = messages[1]["content"]
        seen["schema"] = schema
        return {k: None for k in records.FROM_NOTES} | found

    monkeypatch.setattr(llm, "chat_json", chat_json)
    return seen


def test_full_record(monkeypatch):
    seen = fake_model(monkeypatch, applicator_name="Sam Ortiz", certification_number="IA-12345",
                      application_date="2026-10-26", start_time="09:10", end_time="09:40",
                      owner_name="Lund Ranch", owner_address="12 Ranch Rd, Florence MT", equipment="DJI Agras T50",
                      manufacturer="Corteva", rate="2 qt/acre", amount_applied="12 gal", pest="leafy spurge",
                      crop_or_site="soybeans", wind_speed_mph=6, wind_direction="NW", temperature_f=64)
    r = records.fill_record("Sam Ortiz, cert IA-12345, 12 gallons on soybeans", JOB, date(2026, 10, 26))
    assert r.missing == []
    assert r.product_name == "INTREPID 2F" and r.area_treated_acres == 35.5 and r.wind_speed_mph == 6
    assert "Today is 2026-10-26" in seen["user"] and r.transcript.startswith("Sam Ortiz")
    assert seen["schema"]["required"] == list(records.FROM_NOTES)


def test_job_beats_model(monkeypatch):
    fake_model(monkeypatch, crop_or_site="corn")
    r = records.fill_record("x", JOB | {"crop_or_site": "soybeans"})
    assert r.crop_or_site == "soybeans"


def test_model_cannot_set_job_fields(monkeypatch):
    # product and acres only come from the plan, never from what the model heard
    monkeypatch.setattr(llm, "chat_json", lambda *a, **kw: {"product_name": "Other", "area_treated_acres": 99})
    r = records.fill_record("x", {})
    assert r.product_name is None and r.area_treated_acres is None


def test_missing_lists_required_gaps(monkeypatch):
    fake_model(monkeypatch, applicator_name="Sam Ortiz", certification_number="")
    r = records.fill_record("Sam here", JOB)
    assert r.missing == ["certification_number", "application_date", "start_time", "end_time", "owner_name",
                         "owner_address", "equipment", "manufacturer", "rate", "amount_applied", "pest",
                         "crop_or_site", "wind_speed_mph", "wind_direction", "temperature_f"]


def test_general_pest_terms_are_not_a_record_entry(monkeypatch):
    # ARM 4.10.207: name the pest, "do not use general terms such as weeds and bugs"
    fake_model(monkeypatch, pest="Weeds")
    r = records.fill_record("sprayed the weeds", JOB)
    assert r.pest is None and "pest" in r.missing
    fake_model(monkeypatch, pest="leafy spurge")
    assert records.fill_record("spurge", JOB).pest == "leafy spurge"


def test_transcribe_uses_voice_model(monkeypatch, tmp_path):
    audio = tmp_path / "note.m4a"
    audio.write_bytes(b"audio")
    seen = {}
    monkeypatch.setattr(llm, "transcribe", lambda p, purpose: seen.update(p=p, purpose=purpose) or "hello")
    assert records.transcribe(audio) == "hello" and seen == {"p": audio, "purpose": "record"}


def test_drone_job_gets_a_part137_row(monkeypatch):
    fake_model(monkeypatch, applicator_name="Sam Ortiz", certification_number="IA-12345",
               application_date="2026-10-26", amount_applied="12 gal", customer_name="Lund Farms",
               pilot_name="Ana Diaz", pilot_certificate_number="FAA-4402")
    p = records.fill_record("...", JOB).part137
    assert p.material == "INTREPID 2F (EPA Reg. No. 62719-442)" and p.quantity == "12 gal"
    assert p.service_date == "2026-10-26" and p.customer_name == "Lund Farms"
    assert p.pilot_name == "Ana Diaz" and p.pilot_certificate_number == "FAA-4402"
    assert p.missing == ["customer_address", "pilot_address", "pilot_knowledge_test_date"]


def test_state_certification_never_becomes_the_pilot_certificate(monkeypatch):
    fake_model(monkeypatch, applicator_name="Sam Ortiz", certification_number="IA-12345")
    rec = records.fill_record("...", JOB)
    assert rec.certification_number == "IA-12345" and rec.part137.pilot_certificate_number is None
    assert rec.part137.pilot_name is None  # the applicator is not assumed to be the pilot
    assert "customer_name" not in rec.missing  # Part 137 gaps stay in their own list


def test_ground_job_has_no_part137_row(monkeypatch):
    fake_model(monkeypatch)
    assert records.fill_record("...", JOB | {"method": "ground"}).part137 is None
