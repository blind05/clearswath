# Module contracts

Shapes are shapely geometries in EPSG:4326 (lon/lat) unless stated. Areas in acres.
Don't change a contract unless the human asks.

| Module | Function | Takes | Returns |
| --- | --- | --- | --- |
| `app/llm.py` | `client(provider)`, `chat()`, `chat_json()`, `sam_raw()`, `transcribe()`, `data_url()`, `load_prompt()`, `resolve_provider()` | messages, JSON schema (object root), optional `provider` (`meta` or `baseten`, default `LLM_PROVIDER`) | model reply; dict matching schema (on Baseten via one forced tool call). Logs every call to `data/logs/calls.jsonl` |
| `app/geo.py` | `load_field()`, `save_shapes()`, `load_shapes()`, `to_feature_collection()` | GeoJSON paths, shapes | shapely shapes in EPSG:4326; GeoJSON dicts |
| `app/imagery.py` | `fetch_tile(field_path, out_png)` | field GeoJSON | PNG plus `.json` sidecar: crs, transform (6 values, downscaled), date (newest), dates, empty_fraction, width, height. Gaps are filled from other NAIP images |
| `app/imagery.py` | `usgs_water(field_path)` | field GeoJSON, optional `failed` list | list of water shapes; names of layers that errored are appended to `failed` |
| `app/segment.py` | `find_hazards(field_path)` | field GeoJSON | `{water, building, habitat, imagery_date, water_source, water_warnings, imagery_warnings}`; cached per field and hazard |
| `app/label_reader.py` | `read_label(path, provider=None)` (= `verify(read_raw(path, provider))`) | PDF or image | `LabelRules`: product_name, epa_reg_no, rules (kind, target, applies_to, value, unit, summary, quote, page, condition), dropped, source |
| `app/bulletins.py` | `check_bulletin(field_path, month, reg_no)` | field, month, product | `{in_pula, prohibited, limitations, restricted, citation, checked}` |
| `app/buffers.py` | `plan(field, hazards, rules, restricted, method, prohibited, gaps=())` | shapes and rules | `{status, method, field_acres, spray_acres, excluded_acres, spray_zone, no_spray, reasons}` |
| `app/pipeline.py` | `run(field_path, label_path, month, method, excluded_rules=())`, `assemble(...)`, `to_json(result)`, `save_inputs()`/`load_inputs()` (demo cache) | paths and options; ids of rules the user unticked | full result; JSON with map layers, `confirm` and `excluded_rules` for the page |
| `app/agent.py` | `run(field_path, label_path, month, method, excluded_rules=(), provider=None)` | same | `{run_id, answer, decision, trace, mode, result}`; `result` is what `pipeline.run` returns |
| `app/records.py` | `transcribe(path)`, `fill_record(text, job)` | audio; transcript and job dict | text; `AppRecord` with `missing` list; drone/aerial jobs add `part137` (14 CFR 137.71 items, own `missing` list) |
| `app/api.py` | `/api/demo`, `/api/label`, `/api/plan`, `/api/agent`, `/api/kml/{id}`, `/api/record` | form uploads | JSON for `web/index.html` |

Every label rule is applied. Buffer rules with a `condition` (e.g. "ULV aerial only"), and every rule
read from a photo, are listed in `confirm`; the user can untick them (`excluded_rules`, ids = indexes into
`label.rules`). Unticking anything else is refused. A model's condition can only make the plan stricter.

Paid endpoints (`/api/plan`, `/api/agent`, `/api/label`, `/api/record`) need the `X-Access-Code` header when
`ACCESS_CODE` is set (refused on Render without one), plus a per-IP hourly limit and a daily cap.

`/api/demo?field=&method=&excluded_rules=` (`field` empty or `corrected`) serves `data/demo/cache/<field>/inputs.json`
(built by `scripts/build_demo.py`) offline, recomputing the plan each time; without a cache it runs live.

`status` is `go` (nothing removed), `adjust` (some acres removed; the green zone is sprayable)
or `no-go` (bulletin prohibits, no sprayable area, or `gaps`: data the plan needs is missing, such as a
failed USGS water layer or a buffer rule whose quote couldn't be verified; nothing is sprayable then). It always comes from `buffers.plan`.

Every reason in `plan.reasons` has `source` (`label`, `bulletin`, `rule:water` or `data`); label
reasons also carry `quote`, `page` and `distance_ft`.
