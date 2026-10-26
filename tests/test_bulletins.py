import json

import httpx
import pytest
from shapely.geometry import box, mapping

from app import bulletins

FIELD = box(-87.513, 44.741, -87.511, 44.743)
SEPT_2014 = 1410134400000  # PULA 2's real effective_date


@pytest.fixture
def field_path(tmp_path):
    p = tmp_path / "field.geojson"
    p.write_text(json.dumps(mapping(FIELD)))
    return p


def pula(pid, geom, effective=SEPT_2014, event="Methoxyfenozide"):
    return {"type": "Feature", "geometry": mapping(geom),
            "properties": {"pula_id": pid, "event_name": event, "effective_date": effective}}


def limitation(pid, text, code="100"):
    return {"attributes": {"pula_id": pid, "code": code, "limitation": text}}


def fake_blt(monkeypatch, pulas, rows):
    calls = []

    def query(layer, **params):
        calls.append((layer, params))
        return {"features": pulas if layer == 0 else rows}

    monkeypatch.setattr(bulletins, "_query", query)
    return calls


def test_no_pula(monkeypatch, field_path):
    calls = fake_blt(monkeypatch, [], [])
    out = bulletins.check_bulletin(field_path, "2026-11", "62719-442")
    assert out["checked"] and not out["in_pula"] and not out["prohibited"]
    assert "no PULA applies" in out["citation"] and len(calls) == 1


def test_prohibition_covering_field(monkeypatch, field_path):
    county = box(-88, 44, -87, 45)
    calls = fake_blt(monkeypatch, [pula(2, county)],
                     [limitation(2, "Do not apply this product within this county")] * 2)
    out = bulletins.check_bulletin(field_path, "2026-11", "62719-442-1234")
    assert out["prohibited"] and out["in_pula"] and out["checked"]
    assert len(out["limitations"]) == 1 and out["limitations"][0]["event_name"] == "Methoxyfenozide"
    assert out["restricted"][0].equals(FIELD)
    assert calls[1][1]["where"] == "pula_id IN (2) AND product_registration_number='62719-442'"
    assert "PULA 2 applies" in out["citation"]


def test_prohibition_on_part_of_field(monkeypatch, field_path):
    west_half = box(-88, 44, -87.512, 45)
    fake_blt(monkeypatch, [pula(2, west_half)], [limitation(2, "Do not apply in this area.")])
    out = bulletins.check_bulletin(field_path, "2026-11", "62719-442")
    assert not out["prohibited"]
    assert out["restricted"][0].area == pytest.approx(FIELD.area / 2)


def test_limitation_without_ban_is_listed_only(monkeypatch, field_path):
    fake_blt(monkeypatch, [pula(15, box(-88, 44, -87, 45))],
             [limitation(15, "See http://www.epa.gov/... for mandatory limitations.", "T1")])
    out = bulletins.check_bulletin(field_path, "2026-11", "59639-112")
    assert out["in_pula"] and not out["prohibited"] and out["restricted"] == []
    assert out["limitations"][0]["code"] == "T1"


def test_product_not_listed(monkeypatch, field_path):
    fake_blt(monkeypatch, [pula(2, box(-88, 44, -87, 45))], [])
    out = bulletins.check_bulletin(field_path, "2026-11", "1-1")
    assert out["in_pula"] and out["limitations"] == [] and "no PULA applies" in out["citation"]


def test_pula_not_yet_effective(monkeypatch, field_path):
    dec_2026 = 1796083200000  # 2026-12-01
    calls = fake_blt(monkeypatch, [pula(9, box(-88, 44, -87, 45), effective=dec_2026)], [])
    assert not bulletins.check_bulletin(field_path, "2026-11", "1-1")["in_pula"]
    assert bulletins.check_bulletin(field_path, "2026-12", "1-1")["in_pula"]
    assert len(calls) == 3  # table only queried once a PULA is in effect


@pytest.mark.parametrize("reg_no", ["", None, "abc", "x-1"])
def test_bad_reg_no_is_unchecked(monkeypatch, field_path, reg_no):
    calls = fake_blt(monkeypatch, [], [])
    out = bulletins.check_bulletin(field_path, "2026-11", reg_no)
    assert not out["checked"] and calls == []


def test_reg_no_cannot_inject(monkeypatch, field_path):
    calls = fake_blt(monkeypatch, [pula(2, box(-88, 44, -87, 45))], [])
    bulletins.check_bulletin(field_path, "2026-11", "62719-442' OR '1'='1")
    assert calls[1][1]["where"].endswith("product_registration_number='62719-442'")


def test_blt_down_is_unchecked(monkeypatch, field_path):
    def boom(*a, **kw):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(bulletins, "_query", boom)
    out = bulletins.check_bulletin(field_path, "2026-11", "62719-442")
    assert not out["checked"] and bulletins.BLT_APP in out["citation"]


def test_bad_month_raises(field_path):
    with pytest.raises(ValueError):
        bulletins.check_bulletin(field_path, "November", "62719-442")


def test_month_end():
    assert bulletins._month_end_ms("2026-12") == 1798761600000  # 2027-01-01
